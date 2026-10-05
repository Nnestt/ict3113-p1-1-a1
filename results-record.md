# Results Record

**Status:** In progress. Fill each section from the `.jtl` files in `load_test/results/` and the service log `logs/requests.jsonl`. Every number here must be traceable to one of those two sources (match by `X-Run-ID`).
**Companion to:** [prediction-record.md](prediction-record.md), which is frozen and is not edited. Differences are analysed in the comparison section below.

## Test Environment (measured)

**Current roles (after the 2026-10-06 swap — see Deviations and Limitations):**

| | System under test | Load generator |
|---|---|---|
| Processor | Intel(R) Core(TM) Ultra 7 155H | AMD Ryzen 5 7600 (6-core) |
| System memory | 31.37 GB | 31.1 GB |
| Operating system | Microsoft Windows 11 Home 10.0.26200 | Microsoft Windows 11 |
| Role | Docker (triage service) + Ollama, CPU only | Apache JMeter 5.6.3 |
| Address | 192.168.68.69 | 192.168.68.64 |

- **Network:** Wi-Fi (not wired), same router. Latency jitter from Wi-Fi may appear in p95/p99; this is a factor that could make measurements unrepresentative.
- **Inference device:** CPU only, confirmed with `ollama ps` (PROCESSOR = `100% CPU`) before the real runs.
- **Load generator separate from the SUT:** yes, separate physical machines.
- **The AMD Ryzen 5 7600 machine (now the load generator) has a discrete GPU** (AMD Radeon RX 7800 XT, 16 GB VRAM). This no longer matters for CPU-only compliance since Ollama does not run on this machine anymore (it is not the SUT), but is noted for completeness. When it was briefly the SUT, the GPU was explicitly hidden (`ROCR_VISIBLE_DEVICES=-1`, `HIP_VISIBLE_DEVICES=-1`, `GGML_VK_VISIBLE_DEVICES=-1`) so inference ran on CPU only, confirmed via `ollama ps` (`100% CPU`) and the Ollama server log (`inference compute id=cpu library=cpu`).
- **Note on the prediction record:** its stated environment (Core Ultra 7 155H, 31.37 GB) now matches the system under test, since the swap put that machine in the SUT role. Confirm whether this machine also has a GPU that needs hiding before trusting further CPU-only runs on it (not yet checked as of this note).

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

**Note:** an earlier run 1 (and a partial, aborted run 2) were measured before
the hardware swap below, on the AMD Ryzen 5 7600 acting as the SUT. Run 1's
POST p50 (2044 ms) was far faster than predicted (12 s) for a 7B model on
CPU, raising concern that machine was not representative of the client's
"commodity CPU server" constraint. Testing was stopped and machine roles were
swapped (see Deviations and Limitations). Those runs' raw `.jtl`/log files
were removed; this table starts fresh on the new SUT (Intel Core Ultra 7 155H).

| Run | Run ID | POST n | POST err | POST p50 | POST p95 | POST p99 | Search n | Search p95 | Stats n | Overall error rate |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `qwen7b-run1` | TODO | | | | | | | | |
| 2 | `qwen7b-run2` | TODO | | | | | | | | |
| 3 | `qwen7b-run3` | TODO | | | | | | | | |
| Mean | | | | | | | | | | |
| Spread | | | | | | | | | | |

### `llama3.2:1b`

| Run | Run ID | POST n | POST err | POST p50 | POST p95 | POST p99 | Search n | Search p95 | Stats n | Overall error rate |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | `llama1b-run1` | 23 | 0 | 971 | 2274 | 2381 | 46 | 11 | 1 | 0% (0/70) |
| 2 | `llama1b-run2` | 23 | 0 | 1040 | 2000 | 2316 | 46 | 12 | 1 | 0% (0/70) |
| 3 | `llama1b-run3` | 23 | 0 | 991 | 1973 | 2345 | 46 | 12 | 1 | 0% (0/70) |
| Mean | | 23 | 0 | 1001 | 2082 | 2347 | 46 | 11.7 | 1 | 0% |
| Spread (min–max) | | 23–23 | 0–0 | 971–1040 | 1973–2274 | 2316–2381 | 46–46 | 11–12 | 1–1 | 0%–0% |

Sample standard deviation across the three runs: p50 35.5 ms, p95 166.5 ms, p99 32.6 ms, search p95 0.6 ms.

### `phi3.5:3.8b`, `qwen2.5:1.5b`

Same table, one per model. TODO.

## Requirement Outcomes (load)

| ID | Requirement | `qwen2.5:7b` | `phi3.5:3.8b` | `qwen2.5:1.5b` | `llama3.2:1b` |
|---|---|---|---|---|---|
| R1 | POST p95 ≤ 60 s at peak | TODO (old-SUT run 1 discarded, see note above) | TODO | TODO | TODO |
| R2 | Search p95 ≤ 2 s at peak | TODO (old-SUT run 1 discarded, see note above) | TODO | TODO | TODO |
| R3 | ≥ 46 successful classifications/hour for 60 min | TODO (needs a higher-rate run; see stress test) | TODO | TODO | TODO |
| R4 | Error rate < 1% at peak | TODO (old-SUT run 1 discarded, see note above) | TODO | TODO | TODO |

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
| 4 | `qwen2.5:7b`: 84% accuracy, 12 s warm latency | TODO (old-SUT run 1 showed POST p50 about 2.0 s, which drove the machine-role swap; being re-measured on the new SUT) | TODO |
| 5 | `qwen2.5:7b` most accurate and slowest | TODO | TODO |
| 6 | `llama3.2:1b` fastest and least accurate | TODO | TODO |
| 7 | CPU inference is the primary bottleneck as load rises | TODO | TODO |
| 8 | Hardest categories: consumer loan, debt collection, credit card, bank account or service, money transfer or service | TODO | TODO |
| 9 | All four models exceed 46 classifications/hour | TODO | TODO |

## Reconciliation Checklist

- [ ] Every `.jtl` is in `load_test/results/` and committed.
- [ ] `logs/requests.jsonl` committed after each model.
- [x] `qwen7b-run1`: JMeter request count (70: 23 POST + 46 GET /search + 1 GET /stats) equals the PC 1 log line count for that exact `X-Run-ID` (excluding the separate `warmup-qwen7b-run1` line) — confirmed. p50/p95/p99 independently recomputed from the raw `.jtl` and match the table above exactly (POST p50=2044, p95=4632, p99=5073; search p95=17).
- [ ] Repeat the above check for runs 2 and 3, and for every other model.
- [ ] Every number in the slides appears in this file.

## Deviations and Limitations

- Wi-Fi used between the two machines.
- **Mid-study SUT hardware change.** `qwen2.5:7b` run 1 (23 POST requests, 0 errors, p50 2044 ms, p95 4632 ms, p99 5073 ms) and a partial, aborted run 2 were measured with the AMD Ryzen 5 7600 (6-core) as the system under test. The p50 was far faster than predicted (12 s) for a 7B model on CPU, raising concern that this machine does not represent the client's "commodity CPU server" constraint. The team stopped testing and swapped machine roles: the system under test is now the Intel Core Ultra 7 155H machine (previously the load generator), and the AMD Ryzen 5 7600 machine is now the load generator. The raw `.jtl` and log files from the discarded runs were deleted from the repository rather than kept; this note is the only remaining record of that data and the reason it is not used. All three runs for every model are being measured fresh on the new SUT.
- TODO: anything else that could make the measurements unrepresentative (restarts, interruptions, runs repeated).
