# System-under-test machine setup (Docker + Ollama)

This is the first machine: it runs the triage service in Docker and the Ollama
models on CPU only. The load generator (JMeter) runs on a **separate** machine,
see `SECOND_PC_SETUP.md`.

IP addresses for this test setup:
- This machine (system under test): `192.168.68.69`
- Load generator (JMeter): `192.168.68.64`

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

Versions used for every reported run are in `results-record.md` (Test Environment).

- Docker Desktop installed and running (`docker version` shows a Server; reported runs: Docker
  Engine 29.8.2 on WSL 2).
- Ollama installed (reported runs: 0.35.1), started as in step 2.
- Python 3 (for the pre-flight self-test).
- A clone of this repository at `C:\Users\admin\Documents\GitHub\ict3113-p1-1-a1` (the path the
  load generator's scripts assume; see `SECOND_PC_SETUP.md` step 4).
- Power plan: sleep set to Never, charger connected, and **no screensaver** (one was found
  running during the reported runs; see `results-record.md`).

## 2. Start Ollama CPU-only with the test settings

No GPU inference is allowed. Quit any running Ollama (tray icon → Quit), then start it with
`load_test/start-ollama-cpu.ps1`, which hides every GPU back end and sets
`OLLAMA_NUM_PARALLEL=1` (one generation at a time) and `OLLAMA_KEEP_ALIVE=5m`. To start it
automatically at logon, copy it to `C:\Users\admin\start-ollama-cpu.ps1` and create a
scheduled task (this is how the reported SUT was set up, task name `OllamaCpuOnly`):

```powershell
$a = New-ScheduledTaskAction -Execute powershell.exe -Argument '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\Users\admin\start-ollama-cpu.ps1"'
Register-ScheduledTask -TaskName OllamaCpuOnly -Action $a -Trigger (New-ScheduledTaskTrigger -AtLogOn)
```

`OLLAMA_NUM_PARALLEL=1` matters for the results: the stress test found that Ollama processing
one request at a time is the bottleneck. Confirm CPU-only later with `ollama ps`: the
PROCESSOR column must say `100% CPU` (the test scripts check this before every run and abort
otherwise).

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

## 5. Open port 8000 and SSH for the load generator (Administrator PowerShell)

```powershell
New-NetFirewallRule -DisplayName "Triage 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Any

# OpenSSH Server: the load generator resets this machine and copies its logs over SSH
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
```

Ping is blocked by default on Windows and is not needed; only TCP 8000 and 22 matter. Add the
load generator's public key to `C:\ProgramData\ssh\administrators_authorized_keys` (see
`SECOND_PC_SETUP.md` step 5). The default SSH shell stays `cmd.exe`; the scripts expect that.

## 6. Confirm the address

```powershell
ipconfig
```

The Wi-Fi IPv4 address must be `192.168.68.69`. If it differs, tell the user:
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
`curl http://192.168.68.69:8000/stats` and must get the same JSON.

## 8. Reset between runs (automatic)

Each run must start from an empty service, and stored tickets belong to the model that
classified them. The load generator does this itself before every run by calling
`load_test/reset_sut.ps1 -Model <tag>` on this machine over SSH: `docker compose down -v`,
empty `logs/requests.jsonl`, unload every Ollama model, `docker compose up -d --build` with
`MODEL` pinned, and wait for `/stats` total = 0. The load generator then copies
`logs/requests.jsonl` back as `load_test/logs/<label>_run<N>_requests.jsonl`, so each run's
SUT log is kept in the repository from that machine. Nothing needs to be done here between
runs.

To reset by hand (for example after an aborted run):

```powershell
powershell -NoProfile -File load_test\reset_sut.ps1 -Model qwen2.5:7b
```

## 9. Order of work

All tests are started from the load generator (`SECOND_PC_SETUP.md` step 6):
smoke test, then phases 1–4 (peak load, 3 × 15-minute runs per model), phase 5 (R3 at
46 tickets/hour) and phase 6 (stress ramp). This machine only needs Ollama and Docker running.

## 10. During a run

- Do not use this machine for anything else (no builds, browsing, other
  models in Ollama). Anything competing for CPU skews the latency numbers.
- Do not restart Docker or Ollama.
- If the machine sleeps, the run is ruined: set sleep to Never and plug in
  power before starting (`powercfg /change standby-timeout-ac 0`). Disable the screensaver.
