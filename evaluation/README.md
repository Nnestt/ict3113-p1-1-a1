# Evaluation setup

The classifier every candidate model uses: **one prompt, one set of settings, one parser**, identical for all four models so the comparison is fair.

## Files

| File | What it is |
| --- | --- |
| `prompt_template.md` | The classification prompt. `{narrative}` is replaced with the ticket text. |
| `eval_config.json` | Model tags and digests, the 7 labels, and the generation settings |
| `classifier.py` | Builds the prompt, calls Ollama and turns the reply into a label (or `INVALID`) |
| `data.py` | Loads our team rows (1000–1999) and blocks golden-set rows from being used for testing |
| `measure_num_ctx.py` | Checks the longest ticket fits in the model's context window |
| `smoke_test.py` | Checks every model runs on CPU only and gives a valid label on non-golden rows |
| `setup_and_smoke_test.ipynb` | Runs all the checks above in one notebook |
| `smoke_results/` | Smoke-test output, one CSV per model |
| `run_accuracy.py` | The accuracy experiment: posts all 175 golden tickets to the service, once per model |
| `accuracy.py` | Accuracy maths: overall, per category, confusion matrix, R5/R6 checks |
| `accuracy_analysis.ipynb` | Shows the accuracy results and exports CSVs for the slides |
| `accuracy_results/` | One CSV and one summary JSON per run, plus the exported result tables |

## Accuracy experiment

With Docker Desktop and Ollama running, from the repo root:

```bash
python evaluation/run_accuracy.py
```

For each model it resets storage (`docker compose down -v`), starts the service with that model, checks storage is empty, warms the model up, posts the 175 golden tickets one at a time (each with its own `X-Request-ID` and the run's `X-Run-ID`), then checks `/stats` and `logs/requests.jsonl` agree with the results. About an hour for all four models. Then open `accuracy_analysis.ipynb` and run it top to bottom.

`--dev-check 3` runs the same pipeline on 3 non-golden rows, to test the setup without touching the golden set.

## Rule

**Golden-set tickets are only for the accuracy test.** They never go through a model before this folder is committed. Smoke tests use the other 825 team rows.

**Don't change the prompt, settings or parser after the freeze commit.** Every accuracy and load result depends on them.

## Setup

1. Install [Ollama](https://ollama.com) and pull the four models listed in `eval_config.json`.
2. Put the course CSV at `golden_set/ict3113_tickets.csv` (it is git-ignored).
3. Check everything:

   ```bash
   cd evaluation
   python classifier.py --self-test
   ```

   This tests the parser and confirms every model matches its pinned digest. If a digest doesn't match, you have a different version of that model, so don't use it for testing.

No extra packages are needed; it uses Python's standard library only.

## Try it

```bash
python classifier.py --model qwen2.5:1.5b "My bank froze my account and kept my paycheck."
python smoke_test.py
```
