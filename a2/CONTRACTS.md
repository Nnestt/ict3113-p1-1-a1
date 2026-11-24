# A2 contracts

All A2 code and every handoff between teammates follow this file. If something here has to change, change this file in the same commit.

## Configurations
`a2/configs.json` is the only list of configurations. Python (`evaluation/run_accuracy.py`) and PowerShell (`load_test/run_a2.ps1`, `load_test/reset_sut.ps1`) both read it.

| Config | Mode | Models |
|---|---|---|
| `single-7b` | single | qwen2.5:7b (top model, reference) |
| `single-phi` | single | phi3.5:3.8b |
| `single-1.5b` | single | qwen2.5:1.5b |
| `single-llama` | single | llama3.2:1b |
| `cascade-S1` | cascade | qwen2.5:1.5b → qwen2.5:7b, setting S1 |
| `cascade-S2` | cascade | qwen2.5:1.5b → qwen2.5:7b, setting S2 |

The accept lists for S1 and S2 live in `service/cascade_config.json`. The rule itself is in `a2/escalation_rule.md`.

## Service environment variables
| Variable | Single mode | Cascade mode |
|---|---|---|
| `TRIAGE_MODE` | `single` (default) | `cascade` |
| `MODEL` | the model tag | unused |
| `SMALL_MODEL` | unused | `qwen2.5:1.5b` |
| `LARGE_MODEL` | unused | `qwen2.5:7b` |
| `CASCADE_SETTING` | unused | `S1` or `S2` |
| `TRIAGE_CONFIG` | config name, e.g. `single-7b` (logged only) | e.g. `cascade-S1` (logged only) |

Startup fails with one clear `STARTUP ERROR` line if any model in the config isn't pinned or pulled, or its digest doesn't match the pin. It also fails if the setting is unknown or an accept label isn't one of the seven categories.

## Request log (`logs/requests.jsonl`, one JSON object per line)
Every line has the A1 fields: `ts, request_id, run_id, method, route, status, total_ms, model, model_digest`.

Each `POST /tickets` line also has:

| Field | Meaning |
|---|---|
| `config` | config name (`TRIAGE_CONFIG`) |
| `model`, `model_digest` | **the model that produced the returned category** (the final model) |
| `final_model` | same as `model`, kept explicit for analysis |
| `escalated` | `true` if the large model was called; always `false` in single mode |
| `escalation_reason` | `null`, `not_accepted` (valid label not in the accept list), `invalid` (unparseable small-model output) or `small_error` (small-model call failed) |
| `category` | the returned category (may be `INVALID`) |
| `small_label`, `small_raw_output`, `small_ms`, `small_load_ms`, `small_error` | small-model stage (`null` in single mode) |
| `large_label`, `large_raw_output`, `large_ms`, `large_load_ms` | large-model stage (`null` when not escalated, and in single mode) |
| `model_ms` | total time waiting on Ollama, all stages |
| `raw_output`, `load_ms`, `prompt_eval_ms`, `eval_ms`, `prompt_tokens`, `output_tokens`, `possibly_truncated` | **final stage** (A1 meaning) |
| `narrative_chars`, `ticket_id` | as in A1 |

A stage `*_load_ms` above a few hundred ms during a measured run means Ollama reloaded that model, which is evidence that both models weren't resident. In single mode the single model's call counts as the final stage.

**Escalation fraction** = lines with `escalated == true` / `POST /tickets` lines with status 200, counted per `run_id`.

## Run IDs and files
| What | Run ID | Files |
|---|---|---|
| Accuracy test | `acc_<config>` | `a2/results/accuracy_results/acc_<config>.csv`, `a2/results/accuracy_results/acc_<config>_summary.json`, `a2/results/accuracy_results/acc_<config>_requests.jsonl` |
| Speed run | `a2_<config>_run<N>` | in `load_test/results/`: `<runId>.jtl`, `<runId>_ollama_ps_pre.txt`, `<runId>_ollama_ps_post.txt`, `<runId>_stats_pre.json`, `<runId>_stats_post.json`; in `load_test/logs/`: `<runId>_requests.jsonl`, `<runId>_jmeter.log` |
| Pilot | `pilot_<config>` | same names, under `load_test/pilot/` |
| Warm-up | `warmup-<runId>` (X-Run-ID only) | lines in the same request log; excluded from every figure |

`X-Request-ID` is `<runId>_r<row>` for accuracy and speed runs. It is unique because the workload never recycles.

## Row files (all `row,narrative`, UTF-8, header, quoted)
| File | Rows | Use |
|---|---|---|
| `a2/split/tuning_rows.csv`, `a2/split/test_rows.csv` | 88 / 87 (`row,gold_label`) | design / accuracy test |
| `a2/workload_rows.csv` | 150 | speed-test workload, fixed order, outside the golden set |
| `a2/warmup_rows.csv` | 3 | the same 3 warm-up tickets before every run |
| `a2/s_rows.csv` | 3 | measuring S (different from the warm-up and workload rows) |
| `a2/pilot_rows.csv` | 20 | pilot runs only |

All row files come from `load_test/data/dev_tickets.csv` (rows outside the golden set) and are checked with `assert_not_golden()`. None of them share a row.

## Accuracy CSV (`a2/results/accuracy_results/acc_<config>.csv`)
A1 columns `run_id,row,gold_label,predicted,correct,http_status,request_id,ticket_id,model,model_digest,client_ms,error`, then `config,escalated,escalation_reason,final_model,small_label,large_label`, copied from the service log line with the same `request_id`.

## Speed parameters (`a2/speed_params.json`, written by `a2/measure_s.ps1`)
`{ "S_s", "s_rows", "s_timings_ms", "rate_per_hour", "load_min", "timeout_ms", "pause_min", "measured_utc" }`

- rate = round(3600 / (2·S)) tickets per hour;
- load = max(⌈S⌉, 5) min;
- timeout = max(10·S, 300) s;
- pause = ⌈timeout / 60⌉ + 1 min.

Every speed-tested config uses the same values.
