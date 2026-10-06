# Load-generator machine setup and test playbook (JMeter)

This machine generates the load. It must be physically separate from the machine running
Docker and Ollama (the system under test, SUT; see `FIRST_PC_SETUP.md`). The assignment brief
requires this: a co-hosted load generator steals CPU from the service.

| | Address |
|---|---|
| SUT (Docker + Ollama) | `192.168.68.69` |
| This machine (JMeter) | `192.168.68.64` |

Both machines were on the same Wi-Fi network for every reported run. A wired LAN would be
better: Wi-Fi jitter shows up in p95/p99 (one 3 s TCP retransmit is recorded in
`results-record.md`).

Every test is automated by `run_phase.ps1`. A phase resets the SUT over SSH before every run,
so this machine needs key-based SSH access to the SUT (step 5).

## 1. Prerequisites

```powershell
# Java (JMeter needs it). Reported runs used Eclipse Temurin JDK 17.0.20.1.
winget install -e --id EclipseAdoptium.Temurin.17.JDK --accept-package-agreements --accept-source-agreements

# JMeter 5.6.3 in C:\tools (the scripts expect C:\tools\apache-jmeter-5.6.3\bin\jmeter.bat)
New-Item -ItemType Directory -Path "C:\tools" -Force
Invoke-WebRequest -Uri "https://dlcdn.apache.org/jmeter/binaries/apache-jmeter-5.6.3.zip" -OutFile "C:\tools\jmeter.zip"
Expand-Archive -Path "C:\tools\jmeter.zip" -DestinationPath "C:\tools" -Force
Remove-Item "C:\tools\jmeter.zip"
```

Python 3 is needed for the summary scripts (reported runs used 3.13; standard library only).
The scripts find the JDK themselves; set `JAVA_HOME` only if it is installed somewhere unusual.

## 2. Get the repository

```powershell
git clone <repo-url>
cd ict3113-p1-1-a1\load_test
```

This gives the test plans (`peak_mixed_load.jmx`, `stress_ramp.jmx`), the ticket data
(`data/dev_tickets.csv`: the team's 825 non-golden rows) and the search terms
(`data/search_terms.csv`). Golden-set tickets are never used for load tests.

## 3. Check the SUT is reachable

```powershell
curl http://192.168.68.69:8000/stats
```

Expect JSON like `{"total":0,"by_category":{...}}`. If it fails, check the SUT's firewall rule
for TCP 8000 and that the service is running (`FIRST_PC_SETUP.md`).

## 4. SUT paths the scripts assume

`run_model.ps1` and `run_stress.ps1` default to these values on the SUT. Pass the matching
parameters if the SUT differs:

| Parameter | Default |
|---|---|
| `-Target` | `192.168.68.69` |
| `-SutUser` | `admin` |
| `-SutRepo` | `C:\Users\admin\Documents\GitHub\ict3113-p1-1-a1` (a clone of this repository on the SUT) |
| `-SutOllama` | `C:\Users\admin\AppData\Local\Programs\Ollama\ollama.exe` |

## 5. Key-based SSH to the SUT

The SUT runs Windows OpenSSH Server (`FIRST_PC_SETUP.md` step 5). On this machine:

```powershell
ssh-keygen -t ed25519            # accept defaults, no passphrase
type $env:USERPROFILE\.ssh\id_ed25519.pub
```

Append that line to the SUT's `C:\ProgramData\ssh\administrators_authorized_keys` (the `admin`
account is an administrator). Then check that login needs no password:

```powershell
ssh -o BatchMode=yes admin@192.168.68.69 "echo ok"
```

The SUT's SSH shell is `cmd.exe`, so commands the scripts send there use cmd syntax.

## 6. Run the tests

From `load_test/`. Each phase runs unattended, prints results after every run, and writes the
summary tables into `../results-record.md` between `<!-- BEGIN label -->` / `<!-- END label -->`
markers.

| Phase | Command | What it runs | Time |
|---|---|---|---|
| 1 | `.\run_phase.ps1 -Phase 1` | `llama3.2:1b`, peak load, 3 × 900 s | ~1 h |
| 2 | `.\run_phase.ps1 -Phase 2` | `qwen2.5:1.5b`, peak load, 3 × 900 s | ~1 h |
| 3 | `.\run_phase.ps1 -Phase 3` | `phi3.5:3.8b`, peak load, 3 × 900 s | ~1 h |
| 4 | `.\run_phase.ps1 -Phase 4` | `qwen2.5:7b`, peak load, 3 × 900 s | ~1 h |
| 5 | `.\run_phase.ps1 -Phase 5` | R3: `phi3.5:3.8b` then `qwen2.5:7b`, 46 tickets/h, 3 × 900 s each | ~2 h |
| 6 | `.\run_phase.ps1 -Phase 6 -EndPerMin 24` | Stress: `qwen2.5:7b`, ramp 0 → 24 tickets/min over 15 min, then 10 min drain | ~30 min |

Peak load = 23 `POST /tickets`, 46 `GET /search`, 1 `GET /stats` per hour (from
`performance-requirements.md`), open-loop (Precise Throughput Timer). Phase 5 uses 46 tickets,
46 searches and 1 stats request per hour.

Before every run of phases 1–5, `run_model.ps1`:
1. resets the SUT over SSH with `reset_sut.ps1` (`docker compose down -v`, empty
   `logs/requests.jsonl`, unload all Ollama models, `docker compose up -d --build` with
   `MODEL` pinned) and waits until `/stats` reports `total = 0`;
2. sends one warm-up `POST /tickets` tagged `X-Run-ID: warmup-<RUN_ID>` (loads the model);
3. saves `ollama ps` and aborts unless it shows the pinned model at `100% CPU`;
4. runs JMeter with a new run ID `<label>-run<N>` (never reused) sent as `X-Run-ID` on every
   request;
5. copies the SUT's `logs/requests.jsonl` back and compares its line count for that run ID with
   the `.jtl`;
6. waits 300 s before the next run (laptop SUT thermals).

Phase 6 (`run_stress.ps1`) does steps 1–3, then starts a CPU/memory sampler on the SUT over
SSH, runs `stress_ramp.jmx` (Open Model Thread Group: random arrivals, linear ramp, a new thread
per arrival; constant 4 searches/min; 300 s HTTP timeout), stops the sampler, copies the logs
back, and `stress_summary.py` writes a per-minute table and the limit findings. Stopping
criteria are fixed in `results-record.md` (Stress Test) before the run.

**Smoke test first** (one short run at accelerated rates; a pipeline check, not a result):

```powershell
.\run_phase.ps1 -Phase 1 -Smoke
.\run_phase.ps1 -Phase 6 -Smoke
```

**Resume after a failure:** rerun with `-StartRun N` (for example
`.\run_phase.ps1 -Phase 4 -StartRun 3 -Runs 1`). Never delete a failed run's files; start at the
next run number. For phase 5, `-Only phi3_8b-r3` or `-Only qwen7b-r3` runs one model.

## 7. Output files

| File | Content |
|---|---|
| `results/<label>_run<N>.jtl` | JMeter samples (CSV; `timeStamp` is the request start) |
| `results/<label>_run<N>_ollama_ps.txt` | CPU-only evidence for that run |
| `results/<label>_summary.md` | Per-run p50/p95/p99, mean, spread, SD, reconciliation |
| `results/<label>_run<N>_cpu.csv` | Stress only: SUT CPU/RAM every ~5 s |
| `logs/<label>_run<N>_requests.jsonl` | SUT request log copied after the run |
| `logs/<label>_run<N>_jmeter.log` | JMeter log |
| `logs/<label>_phase.log` | Full transcript of the phase |

## 8. During a run

- Do not use either machine for anything else.
- Do not switch git branches on this machine: GitHub Desktop stashes untracked files, which can
  remove the test plan or data before the next run reads them.
- Keep this machine awake and the Claude Code / PowerShell session open until the phase prints
  `Phase N complete`.

## 9. After a phase

Commit the new files in `load_test/results/` and `load_test/logs/` together with
`results-record.md`. Every reported number must reconcile with these files.
