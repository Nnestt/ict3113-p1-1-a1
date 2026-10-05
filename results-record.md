# Results Record

**Status:** In progress. Fill each section from the `.jtl` files in `load_test/results/` and the service log `logs/requests.jsonl`. Every number here must be traceable to one of those two sources (match by `X-Run-ID`).
**Companion to:** [prediction-record.md](prediction-record.md), which is frozen and is not edited. Differences are analysed in the comparison section below.

## Test Environment (measured)

| | System under test (PC 1) | Load generator (PC 2) |
|---|---|---|
| Processor | TODO | Intel(R) Core(TM) Ultra 7 155H |
| System memory | TODO | 31.37 GB |
| Operating system | TODO | Microsoft Windows 11 Home 10.0.26200 |
| Role | Docker (triage service) + Ollama, CPU only | Apache JMeter 5.6.3 (Java: Microsoft JDK 21) |
| Address | 192.168.68.64 | 192.168.68.69 |

- **Network:** Wi-Fi (not wired), same router. Latency jitter from Wi-Fi may appear in p95/p99; this is a factor that could make measurements unrepresentative.
- **Inference device:** CPU only, confirmed with `ollama ps` (PROCESSOR = `100% CPU`) before the real runs.
- **Load generator separate from the SUT:** yes, separate physical machines.
- **Note on the prediction record:** its stated environment (Core Ultra 7 155H, 31.37 GB) is a teammate's machine with the same specification as PC 2. Fill in PC 1's own specification above; if PC 1 is the same model, say so, since the predictions were made for that hardware.

## Load Test Protocol

- **Plan:** `load_test/peak_mixed_load.jmx`, open-loop (Precise Throughput Timer), peak mixed load: 23 `POST /tickets`, 46 `GET /search`, 1 `GET /stats` per hour.
- **Duration:** 3,600 s per run. **Runs:** three per model. Script: `load_test/run_model.ps1`.
- **Between runs:** service reset (`docker compose down -v; up -d --build`), `/stats` total = 0 checked by the script, one warm-up request tagged `warmup-<RUN_ID>`.
- **Narratives:** 825 team rows from `load_test/data/dev_tickets.csv`. **Search terms:** `load_test/data/search_terms.csv`.
- **Run IDs and files:** `<label>-run<N>` -> `load_test/results/<label>_run<N>.jtl`, `load_test/logs/<label>_run<N>_jmeter.log`.
- **Smoke tests** (`smoke1`, `smoke-qwen7b-run1`) were pipeline checks, not results, and are excluded below.

## Peak Mixed Load Results

p-values in milliseconds. Fill one row per run, then mean and spread (min–max or standard deviation) across the three runs.

### `qwen2.5:7b`

| Run | Run ID | POST n | POST err | POST p50 | POST p95 | POST p99 | Search n | Search p95 | Stats n | Overall error rate |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `qwen7b-run1` | 23 | 0 | 2044 | 4632 | 5073 | 46 | 17 | 1 | 0.0% |
| 2 | `qwen7b-run2` | TODO | | | | | | | | |
| 3 | `qwen7b-run3` | TODO | | | | | | | | |
| Mean | | | | | | | | | | |
| Spread | | | | | | | | | | |

### `phi3.5:3.8b`, `qwen2.5:1.5b`, `llama3.2:1b`

Same table, one per model. TODO.

## Requirement Outcomes (load)

| ID | Requirement | `qwen2.5:7b` | `phi3.5:3.8b` | `qwen2.5:1.5b` | `llama3.2:1b` |
|---|---|---|---|---|---|
| R1 | POST p95 ≤ 60 s at peak | run 1: 4.6 s, pass (TODO runs 2–3) | TODO | TODO | TODO |
| R2 | Search p95 ≤ 2 s at peak | run 1: 17 ms, pass (TODO runs 2–3) | TODO | TODO | TODO |
| R3 | ≥ 46 successful classifications/hour for 60 min | TODO (needs a higher-rate run; see stress test) | TODO | TODO | TODO |
| R4 | Error rate < 1% at peak | run 1: 0%, pass (TODO runs 2–3) | TODO | TODO | TODO |

R3 is not tested by the peak-load run (23 tickets/hour is below 46); it needs a sustained run at 46/hour or more.

## Stress Test

- **Limit under test:** TODO (for example the maximum ticket arrival rate sustained before latency grows without bound).
- **Model:** TODO. **Playbook:** TODO. **Raw files:** TODO.
- **Result and diagnosed bottleneck:** TODO.

## Accuracy Results

Every golden-set ticket through `POST /tickets` per model. Overall and per-category accuracy against `golden_set/gold_labels.csv`, with a confusion matrix.

| Model | Overall | Min category | Meets R5 (≥ 80%) | Meets R6 (every category ≥ 65%) |
|---|---:|---:|---|---|
| `llama3.2:1b` | TODO | TODO | TODO | TODO |
| `qwen2.5:1.5b` | TODO | TODO | TODO | TODO |
| `phi3.5:3.8b` | TODO | TODO | TODO | TODO |
| `qwen2.5:7b` | TODO | TODO | TODO | TODO |

Confusion matrices and where each model goes wrong: TODO.

## Predictions vs Measurements

Predictions are copied from [prediction-record.md](prediction-record.md) without change; only the measured column and the verdict are filled here. Incorrect predictions stay in the record.

| # | Prediction | Measured | Verdict |
|---|---|---|---|
| 1 | `llama3.2:1b`: 68% accuracy, 2.5 s warm latency | TODO | TODO |
| 2 | `qwen2.5:1.5b`: 73% accuracy, 3.5 s warm latency | TODO | TODO |
| 3 | `phi3.5:3.8b`: 79% accuracy, 7 s warm latency | TODO | TODO |
| 4 | `qwen2.5:7b`: 84% accuracy, 12 s warm latency | Load runs: POST p50 about 2.0 s at peak (run 1). Warm single-request latency and accuracy TODO | TODO. Latency looks much lower than predicted; confirm with a single-request test |
| 5 | `qwen2.5:7b` most accurate and slowest | TODO | TODO |
| 6 | `llama3.2:1b` fastest and least accurate | TODO | TODO |
| 7 | CPU inference is the primary bottleneck as load rises | TODO | TODO |
| 8 | Hardest categories: consumer loan, debt collection, credit card, bank account or service, money transfer or service | TODO | TODO |
| 9 | All four models exceed 46 classifications/hour | TODO | TODO |

## Reconciliation Checklist

- [ ] Every `.jtl` is in `load_test/results/` and committed.
- [ ] `logs/requests.jsonl` committed after each model.
- [ ] Per run: JMeter request count equals the log line count for that `X-Run-ID` (excluding `warmup-` lines).
- [ ] Every number in the slides appears in this file.

## Deviations and Limitations

- Wi-Fi used between the two machines.
- TODO: anything else that could make the measurements unrepresentative (restarts, interruptions, runs repeated).
