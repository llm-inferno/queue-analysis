package analyzer

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

// Go test working directory is the package dir (pkg/analyzer); repo root is two
// levels up. Mirrors how the campaign fixtures are laid out at the repo root.
const parityRepoRoot = "../.."

type parityScenario struct {
	Name            string  `json:"name"`
	AvgInputTokens  float32 `json:"AvgInputTokens"`
	AvgOutputTokens float32 `json:"AvgOutputTokens"`
	TargetITL       float32 `json:"targetITL"`
	TargetTTFT      float32 `json:"targetTTFT"`
	MaxQueueSize    int     `json:"maxQueueSize"`
	Alpha           float32 `json:"alpha"`
	Beta            float32 `json:"beta"`
	Gamma           float32 `json:"gamma"`
}

type parityScenarioFile struct {
	Scenarios []parityScenario `json:"scenarios"`
}

type fCurvePoint struct {
	M          int     `json:"m"`
	Throughput float32 `json:"throughput"`
}

type truthCache struct {
	FCurve []fCurvePoint `json:"f_curve"`
}

type goldenRecord struct {
	Strategy string `json:"strategy"`
	Scenario string `json:"scenario"`
	Set      string `json:"set"`
	MChosen  int    `json:"M_chosen"`
	Calls    int    `json:"calls"`
	Feasible bool   `json:"feasible"`
}

type evalResults struct {
	Records []goldenRecord `json:"records"`
}

func readJSON(t *testing.T, parts ...string) []byte {
	t.Helper()
	p := filepath.Join(append([]string{parityRepoRoot}, parts...)...)
	b, err := os.ReadFile(p)
	if err != nil {
		t.Fatalf("read %s: %v", p, err)
	}
	return b
}

func cacheOracle(c *truthCache) ConcurrencyOracle {
	f := make(map[int]float32, len(c.FCurve))
	for _, pt := range c.FCurve {
		f[pt.M] = pt.Throughput
	}
	return func(m int) (float32, bool) {
		thr := f[m] // absent => 0
		return thr, thr > 0
	}
}

func optimizerFor(s parityScenario, oracle ConcurrencyOracle) *ConcurrencyOptimizer {
	return &ConcurrencyOptimizer{
		ServiceParms: &ServiceParms{Alpha: s.Alpha, Beta: s.Beta, Gamma: s.Gamma},
		RequestSize:  &RequestSize{AvgInputTokens: s.AvgInputTokens, AvgOutputTokens: s.AvgOutputTokens},
		Target:       &TargetPerf{TargetTTFT: s.TargetTTFT, TargetITL: s.TargetITL},
		MaxQueueSize: s.MaxQueueSize,
		MMin:         1,
		MMax:         256,
		Oracle:       oracle,
	}
}

// TestFormulaGuidedParity reproduces every formula_guided M_chosen and calls
// value in paper/data/eval_results.json from the Go onset search.
func TestFormulaGuidedParity(t *testing.T) {
	var golden evalResults
	if err := json.Unmarshal(readJSON(t, "paper", "data", "eval_results.json"), &golden); err != nil {
		t.Fatalf("parse eval_results.json: %v", err)
	}

	// Load scenario params for both sets, keyed by name.
	scen := map[string]parityScenario{} // name -> params (names are unique across sets)
	for _, f := range []string{"scenarios.json", "scenarios_benchmark.json"} {
		var sf parityScenarioFile
		if err := json.Unmarshal(readJSON(t, "nous", f), &sf); err != nil {
			t.Fatalf("parse %s: %v", f, err)
		}
		for _, s := range sf.Scenarios {
			scen[s.Name] = s
		}
	}

	// cache path differs by set.
	cachePath := func(set, name string) []string {
		if set == "benchmark" {
			return []string{"nous", "cache", "bench", name + ".json"}
		}
		return []string{"nous", "cache", "truth-" + name + ".json"}
	}

	checked := 0
	for _, g := range golden.Records {
		if g.Strategy != "formula_guided" {
			continue
		}
		s, ok := scen[g.Scenario]
		if !ok {
			t.Fatalf("scenario %q not found in scenario files", g.Scenario)
		}
		var cache truthCache
		if err := json.Unmarshal(readJSON(t, cachePath(g.Set, g.Scenario)...), &cache); err != nil {
			t.Fatalf("parse cache for %s/%s: %v", g.Set, g.Scenario, err)
		}

		res, err := optimizerFor(s, cacheOracle(&cache)).Find()
		if err != nil {
			t.Fatalf("Find %s/%s: %v", g.Set, g.Scenario, err)
		}
		if res.Concurrency != g.MChosen {
			t.Errorf("%s/%s: M_chosen got %d, want %d", g.Set, g.Scenario, res.Concurrency, g.MChosen)
		}
		if res.Calls != g.Calls {
			t.Errorf("%s/%s: calls got %d, want %d", g.Set, g.Scenario, res.Calls, g.Calls)
		}
		// Go's Feasible is f(M*)>0 (oracle at the chosen point); the golden's is
		// f_truth>0 (the scenario peak). These coincide for monotone-to-plateau f:
		// peak>0 iff the chosen point >0, and infeasible-everywhere drives both to 0.
		if res.Feasible != g.Feasible {
			t.Errorf("%s/%s: feasible got %v, want %v", g.Set, g.Scenario, res.Feasible, g.Feasible)
		}
		checked++
	}
	if checked != 36 {
		t.Errorf("checked %d formula_guided records, want 36", checked)
	}
}
