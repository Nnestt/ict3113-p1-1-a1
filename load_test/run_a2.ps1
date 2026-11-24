# Assignment 2 speed test (brief Step 4). Runs ON THE LOAD GENERATOR (Ryzen); drives the SUT over SSH.
# All runs in one launch, INTERLEAVED: run 1 of every config, then run 2 of every config, then run 3,
# so slow drift on the SUT is spread across configurations. Same rate, length and workload for all.
#
# Usage (from load_test/, after a2/speed_params.json is committed by ..\a2\measure_s.ps1):
#   .\run_a2.ps1 -Configs single-7b,cascade-S1,cascade-S2            # 3 runs each, interleaved
#   .\run_a2.ps1 -Configs single-7b,single-phi,cascade-S1,cascade-S2
#   .\run_a2.ps1 -Configs cascade-S1 -OnlyRun 2                       # re-run one broken run
#   .\run_a2.ps1 -Configs single-1.5b -Pilot                          # 2-minute pipeline check, not a result
#
# Each run (brief Step 4 "Each run"):
#  1. reset the SUT and RESTART Ollama (clears its prompt cache; no model loaded)  [reset_sut.ps1 -RestartOllama]
#  2. send the 3 fixed warm-up tickets (a2/warmup_rows.csv), timings thrown away
#  3. cascade: also load + warm the large model directly in Ollama                  [a2/warm_model.ps1]
#     then `ollama ps` must list every model of the config at 100% CPU, or the run aborts
#  4. GET /stats (before)   5. JMeter open-loop run   6. JMeter waits out the pause so slow requests finish
#  7. GET /stats (after); `ollama ps` again (proves nothing was unloaded); copy the service log
# Output names follow a2/CONTRACTS.md. Ends by printing the git commands for commit 7 in plan.md.
param(
    [Parameter(Mandatory)][string[]]$Configs,
    [int]$Runs = 3,
    [int]$OnlyRun = 0,
    [switch]$Pilot,
    [string]$Target = '192.168.68.69',
    [int]$Port = 8000,
    [string]$SutUser = 'admin',
    [string]$SutRepo = 'C:\Users\admin\Documents\GitHub\ict3113-p1-1-a1',   # repo path ON THE SUT - check it
    [string]$SutOllama = 'C:\Users\admin\AppData\Local\Programs\Ollama\ollama.exe',
    [string]$JMeter = 'C:\tools\apache-jmeter-5.6.3\bin\jmeter.bat'
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
. "$PSScriptRoot\a2_common.ps1"
Use-Jdk
foreach ($c in $Configs) { Get-ConfigModels $c | Out-Null }   # fail fast on a typo

$warmups = @(Import-Csv (Join-Path $A2Repo 'a2\warmup_rows.csv'))
if ($warmups.Count -ne 3) { throw 'a2/warmup_rows.csv must hold exactly 3 rows' }

if ($Pilot) {
    # pipeline check only: short, own rows and folder, never reported
    $p = [pscustomobject]@{ rate_per_hour = 600; load_min = 2; timeout_ms = 120000; pause_min = 3 }
    $workload = Join-Path $A2Repo 'a2\pilot_rows.csv'
    $resDir = 'pilot'; $logDir = 'pilot'; $runNums = @(1)
} else {
    $paramsFile = Join-Path $A2Repo 'a2\speed_params.json'
    if (-not (Test-Path $paramsFile)) { throw 'a2/speed_params.json is missing: run ..\a2\measure_s.ps1 first' }
    $p = Get-Content $paramsFile -Raw | ConvertFrom-Json
    $workload = Join-Path $A2Repo 'a2\workload_rows.csv'
    $resDir = 'results'; $logDir = 'logs'
    $runNums = if ($OnlyRun) { @($OnlyRun) } else { 1..$Runs }
}
if ($p.pause_min * 60000 -lt $p.timeout_ms + 60000) { throw 'pause must outlast the response timeout by at least 1 minute' }
$workloadRows = @(Import-Csv $workload).Count
New-Item -ItemType Directory -Force $resDir, $logDir | Out-Null
Write-Host "rate $($p.rate_per_hour)/hour | load $($p.load_min) min | timeout $($p.timeout_ms) ms | pause $($p.pause_min) min | workload $workloadRows rows"

$done = @()
foreach ($k in $runNums) {
    foreach ($c in $Configs) {
        $runId = if ($Pilot) { "pilot_$c" } else { "a2_${c}_run$k" }
        $jtl = "$resDir\$runId.jtl"
        if (Test-Path $jtl) { throw "$jtl already exists - never reuse a run id (delete only a pilot file)" }
        $models = Get-ConfigModels $c
        $cfg = $A2Configs.$c
        Write-Host "`n[$runId] $(Get-Date -Format s) models: $($models -join ' -> ')"

        # 1. reset service + restart Ollama
        Invoke-Sut "powershell -NoProfile -File $SutRepo\load_test\reset_sut.ps1 -Config $c -RestartOllama" | Out-Host

        # 2-3. warm-up: the 3 fixed tickets (loads the first model), then the large model for a cascade
        $i = 0
        foreach ($w in $warmups) {
            $i++
            $ms = Send-Ticket $w.narrative "warmup-$runId" "warmup-${runId}_r$($w.row)"
            Write-Host "[$runId] warm-up $i (row $($w.row)): $ms ms (discarded)"
        }
        if ($cfg.mode -eq 'cascade') {
            Invoke-Sut "powershell -NoProfile -File $SutRepo\a2\warm_model.ps1 -Model $($cfg.large)" | Out-Host
        }
        $psPre = ((Invoke-Sut "$SutOllama ps") -join "`n")
        $psPre | Set-Content "$resDir\${runId}_ollama_ps_pre.txt"
        Assert-Resident $models $psPre "$runId pre"

        # 4. /stats before
        $pre = Get-Stats
        $pre | ConvertTo-Json -Depth 5 | Set-Content "$resDir\${runId}_stats_pre.json"

        # 5-6. open-loop run; seed = run number, so run k is identical in arrival times across configs
        Write-Host "[$runId] JMeter start $(Get-Date -Format s)"
        & $JMeter -n -t a2_open_loop.jmx "-JHOST=$Target" "-JPORT=$Port" "-JRUN_ID=$runId" "-JSEED=$k" `
            "-JRATE_PER_HOUR=$($p.rate_per_hour)" "-JLOAD_MIN=$($p.load_min)" "-JPAUSE_MIN=$($p.pause_min)" `
            "-JTIMEOUT_MS=$($p.timeout_ms)" "-JWORKLOAD=$workload" `
            '-Jjmeter.save.saveservice.output_format=csv' '-Jsampleresult.timestamp.start=true' `
            -l $jtl -j "$logDir\${runId}_jmeter.log" | Select-Object -Last 3
        Write-Host "[$runId] JMeter end $(Get-Date -Format s)"

        # 7. /stats after, ollama ps after, service log
        $post = Get-Stats
        $post | ConvertTo-Json -Depth 5 | Set-Content "$resDir\${runId}_stats_post.json"
        $psPost = ((Invoke-Sut "$SutOllama ps") -join "`n")
        $psPost | Set-Content "$resDir\${runId}_ollama_ps_post.txt"
        $logFile = "$logDir\${runId}_requests.jsonl"
        & scp -o BatchMode=yes "$SutUser@${Target}:$($SutRepo.Replace('\','/'))/logs/requests.jsonl" $logFile
        if ($LASTEXITCODE -ne 0) { throw "[$runId] could not copy requests.jsonl from the SUT" }

        # quick reconciliation (full figures come from a2/speed_summary.py)
        $samples = @(Import-Csv $jtl | Where-Object { $_.label -eq 'POST /tickets' })
        $ok = @($samples | Where-Object { $_.success -eq 'true' }).Count
        $logged = @(Get-Content $logFile | Where-Object { $_ -match "`"run_id`": `"$([regex]::Escape($runId))`"" -and $_ -match '"route": "/tickets"' }).Count
        $delta = $post.total - $pre.total
        Write-Host ("[$runId] sent {0} | ok {1} | errors {2} | service log lines {3} | /stats delta {4}" -f $samples.Count, $ok, ($samples.Count - $ok), $logged, $delta)
        if ($samples.Count -ne $logged -or $ok -ne $delta) { Write-Host "[$runId] WARNING: counts differ - check for unfinished requests" }
        if ($samples.Count -ge $workloadRows) { Write-Host "[$runId] WARNING: workload exhausted - arrivals may have been dropped" }
        try { Assert-Resident $models $psPost "$runId post" } catch { Write-Host "[$runId] WARNING: $_" }
        $done += $runId
    }
}

Write-Host "`nDone: $($done -join ', ')"
if (-not $Pilot) {
    Write-Host "Commit the raw files (commit 7 in plan.md):"
    Write-Host "  git add load_test/results/a2_* load_test/logs/a2_*"
    Write-Host "  git commit -m `"A2 Step 4: speed test runs ($($Configs -join ', '))`""
    Write-Host "  git push"
}
