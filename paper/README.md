# Paper: Scaling with Optimal Concurrency

## Build

```bash
cd paper
latexmk -pdf main.tex
```

## Regenerate figures and tables

```bash
cd paper/scripts
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python sweep_baseline.py        # one-shot; writes paper/data/baseline_lambda_sweep.json
python make_figures.py          # produces paper/figs/*.pdf and paper/tabs/*.tex
```

The sweep requires the queue-analysis Go server running on :8080.

```bash
go build -o /tmp/queue-analysis . && /tmp/queue-analysis &
```
