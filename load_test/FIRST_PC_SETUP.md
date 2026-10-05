# System-under-test machine setup (Docker + Ollama)

This is the first machine: it runs the triage service in Docker and the Ollama
models on CPU only. The load generator (JMeter) runs on a **separate** machine,
see `SECOND_PC_SETUP.md`.

IP addresses for this test setup:
- This machine (system under test): `192.168.68.64`
- Load generator (JMeter): `192.168.68.69`

Both machines are on the same Wi-Fi network (a wired LAN would be better; Wi-Fi
jitter can show up in the p95/p99 numbers, so note it in the test-environment
description).

## Instructions for the AI agent doing this setup

Do the steps below in order, verify each one, and report anything that fails
instead of working around it. Do not edit service code, the prompt, or
`eval_config.json` (they are frozen). Use PowerShell. Steps 5 and 6 need an
Administrator PowerShell; ask the user to run those commands if you do not
have admin rights.

## 1. Prerequisites

- Docker Desktop installed and running (`docker version` shows a Server).
- Ollama installed and running on the host (`curl http://localhost:11434`
  returns "Ollama is running").
- Python 3 (for the pre-flight self-test).

## 2. Ollama must be CPU only

No GPU inference is allowed. If the machine has a GPU, hide it before starting
Ollama, for example:

```powershell
$env:CUDA_VISIBLE_DEVICES = "-1"   # then restart Ollama from this shell
```

Confirm later with `ollama ps`: the PROCESSOR column must say `100% CPU`.

## 3. Pull the four pinned models

The tags and digests are pinned in `service/eval_config.json`:

| Tag | Role |
| --- | --- |
| `llama3.2:1b` | small |
| `qwen2.5:1.5b` | small |
| `phi3.5:3.8b` | medium |
| `qwen2.5:7b` | large |

```powershell
ollama pull llama3.2:1b
ollama pull qwen2.5:1.5b
ollama pull phi3.5:3.8b
ollama pull qwen2.5:7b
```

The service refuses to start if a model's local digest differs from the pin.

## 4. Pre-flight check (from the repo root)

```powershell
cd evaluation
python classifier.py --self-test
cd ..
```

All four models must pass. Fix this before going further.

## 5. Open port 8000 for the load generator (Administrator PowerShell)

```powershell
New-NetFirewallRule -DisplayName "Triage 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Any
```

Ping is blocked by default on Windows and is not needed; only TCP 8000 matters.

## 6. Confirm the address

```powershell
ipconfig
```

The Wi-Fi IPv4 address must be `192.168.68.64`. If it differs, tell the user:
the JMeter machine needs the new address (`-Target` in `run_model.ps1`). To
keep it stable, reserve the address for this machine in the router (DHCP
reservation).

## 7. Start the service with one model

```powershell
$env:MODEL = "qwen2.5:7b"
docker compose up -d --build
curl http://localhost:8000/stats
```

Expected: `{"total":0,"by_category":{...}}`. If the container exits, read the
last line before `Application startup failed` in `docker compose logs`
(Ollama not running, model not pulled, or digest mismatch).

Check it is reachable from the network side: the JMeter machine runs
`curl http://192.168.68.64:8000/stats` and must get the same JSON.

## 8. Reset between runs (and when switching model)

Each run must start from an empty service, and stored tickets belong to the
model that classified them. The JMeter script waits until `/stats` shows
`total = 0`, so just reset:

```powershell
# same model, next run
docker compose down -v
docker compose up -d --build

# switching model: set MODEL first
docker compose down -v
$env:MODEL = "phi3.5:3.8b"
docker compose up -d --build
```

Only stop or reset after the load generator has finished: a request in flight
when the container stops gets no reply and no log line.

`logs/requests.jsonl` is appended to and is **not** cleared by `down -v`. That
is intended. Runs are told apart by the `X-Run-ID` field. Do not delete it
between runs.

## 9. Order of work

1. Smoke test first: from the JMeter machine, run
   `.\run_model.ps1 -Label qwen7b -Smoke` (2 minutes, one run). Then reset
   (step 8) so the service is empty for the real runs.
2. Real runs: `.\run_model.ps1 -Label qwen7b` on the JMeter machine does
   three 60-minute runs and waits for a reset between each. Reset this
   machine when it prints that it is waiting.
3. Check the numbers, switch model (step 8), repeat.

## 10. During a run

- Do not use this machine for anything else (no builds, browsing, other
  models in Ollama). Anything competing for CPU skews the latency numbers.
- Do not restart Docker or Ollama.
- If the machine sleeps, the run is ruined: set sleep to Never and plug in
  power before starting (`powercfg /change standby-timeout-ac 0`).

## 11. After each model

Commit and push `logs/requests.jsonl` so the SUT log is kept alongside the
`.jtl` files from the JMeter machine. Every reported number must reconcile
with these two sources.
