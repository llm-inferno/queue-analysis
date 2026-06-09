# NOUS Campaign — Max-Throughput MaxBatchSize Algorithm

**Status:** design — pending implementation plan
**Date:** 2026-06-09
**Target system:** `/Users/tantawi/Projects/llm-inferno/queue-analysis`
**NOUS install:** `~/Projects/nous/agentic-strategy-evolution`

## 1. Goal

Run a NOUS campaign on the queue-analysis project that produces, in order:

1. **Validated structural properties** of `f(M) = max-RPS-meeting-targets` as a function of `MaxBatchSize`, where the analyzer's `/target` endpoint is the oracle.
2. **A justified algorithm** that exploits those properties to find `argmax_M f(M)` with as few `/target` calls as possible.

Both deliverables come out of NOUS's principle store and the per-iteration `bundle.yaml` / `findings.json` artifacts.

## 2. Optimization problem (formal)

Given fixed inputs `Alpha`, `Beta`, `Gamma`, `AvgInputTokens`, `AvgOutputTokens`, `MaxQueueSize`, `TargetITL`, `TargetTTFT`, find:

```
M* = argmax_{M ∈ [M_min, M_max]} f(M)
where  f(M) = throughput returned by /target for that ProblemData
```

The analyzer's `/target` endpoint already finds the max RPS meeting ITL/TTFT targets *for a given* `MaxBatchSize`. So a single call to `/target` evaluates `f` at one `M`. The meta-algorithm searches over `M`.

Fixed for this campaign: `M_min = 1`, `M_max = 256`. `Alpha = 12`, `Beta = 0.05`, `Gamma = 0.0005` (from `examples/problem-data.json`).

## 3. Scenarios

Properties and the algorithm must hold across this fixed set of 4 named scenarios.

| name | AvgInputTokens | AvgOutputTokens | TargetITL (ms) | TargetTTFT (ms) | MaxQueueSize | tight axis |
|---|---|---|---|---|---|---|
| baseline          | 256 | 512  | 20 | 60  | 128 | balanced |
| short-tight-ttft  | 128 | 256  | 20 | 35  | 128 | TTFT-bound (35ms is tight; values below ~31ms are infeasible for this token profile) |
| long-loose-itl    | 256 | 1024 | 40 | 200 | 128 | ITL-bound, throughput-rich |
| small-queue       | 256 | 512  | 20 | 60  | 4   | queue-capacity bound (M* shifts by ~2 vs baseline; effect is real but small) |

Defined once in `nous/scenarios.json`; both the harness and the planner read from there.

## 4. Architecture

### 4.1 New files in queue-analysis

```
queue-analysis/nous/
  campaign.yaml                       # NOUS campaign config
  description.txt                     # full brief — load-bearing (see §8)
  scenarios.json                      # the 4 scenarios above
  harness/
    run.py                            # spawns Go server, runs a strategy, records
    baseline_truth.py                 # one-time brute-force scan
    strategies/                       # one Python file per candidate algorithm
      __init__.py
      example_linear_scan.py          # smoke-test strategy committed up front
  cache/
    truth-<scenario>.json             # M*, f(M*) per scenario (gitignored)
  results/                            # per-arm output files (gitignored)
```

### 4.2 Strategy contract

Every candidate algorithm is a Python module exposing:

```python
def search(target_eval, m_min: int, m_max: int) -> int:
    """Return chosen MaxBatchSize.

    target_eval(m: int) -> dict   # AnalysisData JSON for that M.
                                  # Each call is counted automatically.
                                  # The strategy cannot bypass this wrapper.
    """
```

Strategies are pure Python — no file I/O, no globals. The harness owns all bookkeeping.

### 4.3 Harness CLI

```bash
python nous/harness/run.py \
  --scenarios nous/scenarios.json \
  --strategy nous/harness/strategies/<name>.py \
  --m-min 1 --m-max 256 \
  --out <results-path>.json
```

Responsibilities:

- Start the Go analyzer (`go run main.go` on `:8080`), wait until it answers a probe call, kill on exit (including on error / signal).
- For each scenario in `scenarios.json`: build the `ProblemData`, hand the strategy a `target_eval` closure, time the search, count `/target` calls.
- Read the cached truth (`cache/truth-<scenario>.json`) and compute `gap_throughput_rel` and `gap_M`.
- Emit one record per scenario to the output JSON.

Output JSON structure (one record per scenario):

```json
{
  "scenario": "baseline",
  "strategy": "example_linear_scan",
  "M_chosen": 38,
  "calls": 7,
  "throughput_chosen": 3.78,
  "M_truth": 40,
  "throughput_truth": 3.81,
  "gap_throughput_rel": 0.008,
  "gap_M": 2,
  "wall_clock_seconds": 1.42,
  "internal_solve_calls": 56
}
```

`internal_solve_calls` is logged for audit (it is *not* part of the score).

### 4.4 Truth baseline

`baseline_truth.py` brute-force scans `M ∈ [M_min, M_max]` for each scenario, calling `/target` once per `M`. Cost: 256 × 4 = 1,024 `/target` calls. Cache file per scenario stores `M*`, `f(M*)`, and the full `f(M)` curve (the curve is not used at scoring time but is invaluable for the planner during property discovery).

This is **not** a NOUS iteration — it's a one-time setup step run before iter 1. Re-run only if `scenarios.json` changes.

## 5. Pareto axes

For each (strategy, scenario):

- **`calls`** — number of HTTP `/target` calls the strategy made. Counted by the harness's `target_eval` wrapper. Internal `/solve` calls inside `/target` are **not** part of the score (logged separately as `internal_solve_calls`).
- **`gap_throughput_rel`** — `(throughput_truth − throughput_chosen) / throughput_truth`. Always ≥ 0; lower is better. If `throughput_truth = 0` (no feasible solution), gap is reported as 0.
- **`gap_M`** — `|M_chosen − M_truth|`. Reported but not the primary axis (a plateau makes a large `gap_M` benign).

Aggregated across the 4 scenarios for a strategy: report both **worst-case** `(max calls, max gap_throughput_rel)` and **mean** `(mean calls, mean gap_throughput_rel)`. Worst-case is the primary comparison.

A strategy A **Pareto-dominates** B iff worst-case A is no worse on both axes and strictly better on at least one.

## 6. Iteration plan (Approach A — discover-then-design)

`max_iterations: 5`, split into two stages.

### Stage 1 — Property discovery (iter 1–3)

| iter | Research focus | Expected H-main shape | Key arms |
|---|---|---|---|
| 1 | Shape of `f` on a single scenario (`baseline`). | "`f` is unimodal with a single interior maximum on `M ∈ [1, M_max]`." | h-main; h-control-negative ("a regime where the peak vanishes — e.g., extreme-loose targets — should produce a monotone curve"). Observe-mode (no code changes); the harness scans `f` over `M`. |
| 2 | Local shape near the peak. | "`f` is concave near `M*`" or "`f` exhibits a plateau of width ≥ k around `M*`". | h-main; h-ablation (which of {ITL-target, TTFT-target} drives the descent past `M*`); h-robustness across all 4 scenarios. |
| 3 | Predicting `M*` from inputs. | "`M*` is well-approximated by a closed form in {`AvgOutputTokens`, `TargetITL`, `TargetTTFT`, `Beta`, `Gamma`}." | h-main; h-robustness across all 4 scenarios; h-ablation removing one variable from the predictor at a time. |

Iter-1 Stage-1 hypotheses are **suggestions**, not prescriptions — the planner may pick different shapes if its exploration suggests them. The user steers via the design gate.

### Stage 2 — Justified algorithm (iter 4–5)

| iter | Research focus | Expected H-main shape | Key arms |
|---|---|---|---|
| 4 | First algorithm justified by Stage 1. | "Algorithm-1 reaches `gap_throughput_rel ≤ 1%` in `≤ k(M_max)` calls on all 4 scenarios" — concrete `k` set by the planner based on Stage-1 findings. `code_changes`: add `nous/harness/strategies/alg1.py`. | h-main; h-control-negative (in a regime where Stage-1 properties fail, expect more calls); h-robustness. |
| 5 | Algorithm-2 vs Algorithm-1 (Pareto). | "Algorithm-2 Pareto-dominates Algorithm-1 on (worst-case calls, worst-case gap)." `code_changes`: add `nous/harness/strategies/alg2.py`. | h-main; h-robustness across all 4 scenarios. |

If a Stage-1 property is refuted, the algorithm in Stage-2 must be revised — that is the campaign earning its keep, not failing.

### Human gates

- **Design gate (post-DESIGN)** — read `bundle.yaml`. Reject if the planner is off-stage (e.g., proposing algorithms in iter 1) or if predictions aren't quantitative enough.
- **Findings gate (post-EXECUTE_ANALYZE)** — read `findings.json`. Reject if analysis is sloppy or principles drift from evidence.

### Stopping early

The campaign may stop before iter 5:

- After iter 3 if Stage 1 is solid and you'd rather hand-design the algorithm.
- After iter 4 if Algorithm-1 already meets your needs.
- `nous resume` continues a paused campaign later.

## 7. Campaign configuration

### 7.1 `nous/campaign.yaml`

```yaml
research_question: >
  Find structural properties of f(M) = max-RPS-meeting-targets as a function of
  MaxBatchSize M, then design an algorithm that finds argmax_M f with few /target
  calls. Treat /target as the black-box oracle. Score on two axes: (a) number of
  /target calls, (b) gap_throughput_rel = (truth - chosen) / truth. Pareto compare.

  Stage plan: iter 1-3 discover properties (unimodality, local concavity / plateau,
  closed-form predictor for M* from inputs); iter 4-5 propose and compare algorithms
  in nous/harness/strategies/. Use the harness in nous/harness/run.py — strategies
  must implement search(target_eval, m_min, m_max) -> int; the harness counts calls.

  For the full brief — scenarios, harness contract, Pareto axes, scoring rules —
  read nous/description.txt in this repository.

run_id: queue-throughput

max_iterations: 5

target_system:
  name: "queue-analysis"
  description: >
    Go REST server (main.go) that solves a state-dependent Markovian queueing model
    of a vLLM inference server. Two endpoints:
      - /solve  : analyze the queue at a given (RPS, MaxBatchSize, ...) and return
                  Throughput, AvgITL, AvgTTFT, etc.
      - /target : find the maximum RPS that satisfies AvgITL <= TargetITL and
                  AvgTTFT <= TargetTTFT for a given MaxBatchSize, returning that
                  RPS as Throughput.
    See examples/problem-data.json for the input schema and examples/solution-target.json
    for the output schema.
  observable_metrics:
    - throughput
    - avgITL
    - avgTTFT
    - calls_to_target_per_search
    - gap_throughput_rel
  controllable_knobs:
    - MaxBatchSize
    - search_strategy_in_nous_harness_strategies
  repo_path: /Users/tantawi/Projects/llm-inferno/queue-analysis

prompts:
  methodology_layer: "prompts/methodology"
  domain_adapter_layer: null
```

### 7.2 `nous/description.txt`

A self-contained brief sitting **inside** the target repo so the planner's worktree can `cat nous/description.txt` directly. Sections:

- **Background** — what queue-analysis is (REST server, the queueing model, /solve vs /target). Reference `examples/problem-data.json`.
- **Problem definition** — the optimization problem in §2 above, restated. Define `f(M)`, `M*`, the inputs that are fixed vs. varying.
- **Scenarios** — the table from §3, with a pointer to `nous/scenarios.json` as canonical.
- **Harness contract** — strategy signature from §4.2, CLI from §4.3.
- **Pareto axes & scoring** — definitions from §5.
- **Stage plan** — the 5-iteration plan from §6 (so the planner self-orients to the current iteration's expected scope).
- **What's already validated** — the truth cache exists; the harness has been smoke-tested with `example_linear_scan.py`; the Go server starts via `go run main.go` from repo root.

The full text is drafted by the implementation plan from the sections above. It must be self-contained: the planner reads it without further references, and it must not contradict §2–§6 of this spec.

## 8. Why `description.txt` lives inside the target repo

The DESIGN-phase prompt (`prompts/methodology/design.md:24-26`) interpolates `research_question` verbatim and runs `claude -p` in a git worktree of `target_system.repo_path`. There is no auto-expansion of `description.txt` references. So:

- The `research_question` field carries enough self-contained context that the planner can design coherently even if a file read fails.
- `description.txt` lives at `queue-analysis/nous/description.txt` — reachable from the planner's worktree via `cat nous/description.txt`.
- The `research_question` explicitly directs the planner to read it.

This is a deliberate departure from the autoscaling example, where `description.txt` sits in the campaign config dir (not the target repo) and the planner cannot reach it from its worktree.

## 9. Pre-flight checks (before iter 1)

These run before any LLM call. The implementation plan codifies them as a script.

1. `go run main.go` listens on `:8080`; `curl -X POST localhost:8080/target -d @examples/problem-data.json` returns valid JSON.
2. `python nous/harness/run.py --strategy nous/harness/strategies/example_linear_scan.py --scenarios nous/scenarios.json --m-min 1 --m-max 16 --out /tmp/smoke.json` exits 0 and produces a record per scenario.
3. `python nous/harness/baseline_truth.py` populates `nous/cache/truth-<scenario>.json` for all 4 scenarios.
4. `git worktree add /tmp/qa-preflight HEAD && cat /tmp/qa-preflight/nous/description.txt | head -10` succeeds — confirms `nous/description.txt` is committed to the branch NOUS will worktree from, and the planner will be able to read it from its own worktree. Clean up the worktree after.
5. `nous --version` succeeds; `nous validate design --help` is reachable.

## 10. How to launch

```bash
cd /Users/tantawi/Projects/llm-inferno/queue-analysis

# one-time
python -m venv .venv && source .venv/bin/activate
pip install requests

# pre-flight (script TBD in implementation plan)
python nous/harness/baseline_truth.py

# optional but recommended (for gate summaries / report)
export OPENAI_API_KEY=...
export OPENAI_BASE_URL=...

# run
nous run nous/campaign.yaml --max-iterations 5 -v
```

Artifacts land at `queue-analysis/.nous/queue-throughput/runs/iter-N/`. Each iteration pauses at two human gates — `approve`, `reject`, or `abort`.

## 11. Scope notes

- **Out of scope:** changes to the Go analyzer code, additional /-style endpoints, sweeping over `Alpha`/`Beta`/`Gamma`, or more than the 4 scenarios. Robustness arms operate only across the named set.
- **Note on infeasibility:** The Go analyzer's `/target` endpoint returns HTTP 400 when the (M, target-set) pair is infeasible (e.g., the latency target is outside the achievable range for that token profile, or M=1 fails the ITL check at low load). The harness oracle (`nous/harness/oracle.py`) maps 400 → `{"throughput": 0.0}` and does NOT count it against the call budget; strategies see infeasible Ms as 0-throughput points and continue.
- **Out of scope:** on-line / streaming variants of the algorithm. The strategy is invoked once per scenario from cold start.
- **Open question for iter 1:** if the planner finds `f` is *not* unimodal in some scenario, the rest of the staging may need rebalancing. The user steers via the design gate at iter 2.
- **Open question for iter 5:** whether to hold-out a 5th "validation" scenario for Algorithm-2 (currently no — all 4 scenarios are used everywhere).
