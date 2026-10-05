# Load-generator machine setup (JMeter)

This sets up the second machine that generates load against the triage
service. It must be a physically separate machine from the one running
Docker/Ollama (see `ICT3113_Assignment_1.pdf`, Step 5: "The load generator
and the system under test must run on separate machines").

IP addresses for this test setup:
- System under test (Docker + Ollama): `192.168.68.64`
- This machine (JMeter): `192.168.68.69`

Both machines must be on the same wired LAN (not Wi-Fi — avoids latency
jitter from interference/retries, which would otherwise show up as noise
in the p95/p99 numbers).

## 1. Confirm basic network reachability

```powershell
ping 192.168.68.64
```

If this fails, fix networking before doing anything else below.

## 2. Install Java (JMeter requires it)

```powershell
winget install -e --id EclipseAdoptium.Temurin.17.JDK --accept-package-agreements --accept-source-agreements
```

Find the actual install path (varies by machine):

```powershell
Get-ChildItem "C:\Program Files\Eclipse Adoptium"
```

## 3. Install JMeter 5.6.3

```powershell
New-Item -ItemType Directory -Path "C:\tools" -Force
Invoke-WebRequest -Uri "https://dlcdn.apache.org/jmeter/binaries/apache-jmeter-5.6.3.zip" -OutFile "C:\tools\jmeter.zip"
Expand-Archive -Path "C:\tools\jmeter.zip" -DestinationPath "C:\tools" -Force
Remove-Item "C:\tools\jmeter.zip"
```

## 4. Set JAVA_HOME and PATH for the session before running JMeter

Replace the path below with whatever step 2 printed.

```powershell
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot"
$env:Path = "$env:JAVA_HOME\bin;" + $env:Path
java -version
```

## 5. Get the repo (for the test plan and data files)

```powershell
git clone <repo-url>
cd ict3113-p1-1-a1\load_test
```

This gets you `peak_mixed_load.jmx`, `data/dev_tickets.csv` (825 team
ticket narratives), and `data/search_terms.csv`. You do **not** need
`golden_set/ict3113_tickets.csv` (the large gitignored source file) on
this machine — it's already baked into `data/dev_tickets.csv`.

## 6. Confirm the actual service is reachable (not just the host)

Once the service is running on `192.168.68.64` (see the main repo's
`service/README.md` for starting it):

```powershell
curl http://192.168.68.64:8000/stats
```

You should get back JSON like `{"total":0,"by_category":{...}}`. If this
fails but step 1's ping worked, the problem is the firewall on the SUT
machine (port 8000 inbound) or the service isn't actually running — not
this machine.

## 7. Run the tests

From `load_test/`, one model at a time. `run_model.ps1` runs the three
60-minute runs for a model, uses a new `RUN_ID`/`.jtl` per run (never reused,
so `.jtl` files and the SUT's `logs/requests.jsonl` stay matchable by
`X-Run-ID`), waits until the SUT has been reset (`/stats` total = 0), warms the
model up, and prints p50/p95/p99 and error rate after each run.

Smoke test first (2 minutes, one run, accelerated rates; a pipeline check, not
a result). Reset the SUT afterwards so the real runs start empty:

```powershell
.\run_model.ps1 -Label qwen7b -Smoke
```

Real runs:

```powershell
.\run_model.ps1 -Label qwen7b
```

If you run JMeter by hand instead, quote every `-J` argument. Windows
PowerShell 5.1 otherwise splits `-JHOST=192.168.68.64` at the dots:

```powershell
& "C:\tools\apache-jmeter-5.6.3\bin\jmeter.bat" -n -t peak_mixed_load.jmx `
  '-JHOST=192.168.68.64' '-JPORT=8000' '-JRUN_ID=qwen7b-run1' '-JDURATION_SEC=3600' `
  -l results\qwen7b_run1.jtl -j logs\qwen7b_run1_jmeter.log
```

`TICKET_RATE` / `SEARCH_RATE` / `STATS_RATE` default to 23 / 46 / 1 per
hour (the real peak-load numbers from `performance-requirements.md`) if
left unset — only override them for a short smoke test or the stress test.

Create `results\` and `logs\` folders first if they don't exist
(`New-Item -ItemType Directory -Force results, logs`).

## 8. During the run

- Don't use this machine for anything else — no browsing, no other apps,
  nothing that could compete for CPU and skew request timing.
- Don't touch the SUT machine either (see the main repo's testing notes).
- The run is unattended once started — check back when `DURATION_SEC`
  has elapsed.

## 9. After the run

Copy `results\*.jtl` back into the main repo (or straight into it if this
is a clone of the same repo) so they're kept alongside the SUT's log
snapshots, per the assignment's requirement to keep raw `.jtl` files in
the repository.
