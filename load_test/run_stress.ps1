# Stress test: one open-model linear ramp of POST /tickets against ONE model.
# Run ON THE LOAD GENERATOR from load_test/ (normally via run_phase.ps1 -Phase 6):
#   .\run_stress.ps1 -Label qwen7b-stress -Model qwen2.5:7b -EndPerMin 40
#
# Playbook (fixed before the run, see results-record.md "Stress Test"):
#  1. Reset the SUT over SSH (reset_sut.ps1: compose down -v, empty request log,
#     unload models, compose up with MODEL pinned); wait for /stats total = 0.
#  2. One warm-up POST tagged warmup-<RUN_ID>; save `ollama ps` (must be 100% CPU).
#  3. Start a CPU/memory sampler on the SUT over SSH (Get-Counter loop, about every 5 s).
#  4. JMeter stress_ramp.jmx: tickets arrive at random (Poisson) times with the rate
#     rising linearly from StartPerMin to EndPerMin over RampMin minutes, plus a
#     constant SearchPerMin of GET /search. Open model: JMeter starts a new thread per
#     arrival, so a slow server cannot throttle the offered load.
#  5. Then DrainMin minutes with no new tickets: queued requests finish (or hit the 300 s timeout).
#     Without this, JMeter interrupts requests still in flight when the ramp ends ("Socket closed").
#  6. Stop the sampler; copy the SUT request log and the CPU log back.
#  7. stress_summary.py bins the run per minute (offered vs completed, p50/p95,
#     queue wait, errors, CPU) and reports the limit.
param(
    [Parameter(Mandatory)][string]$Label,
    [Parameter(Mandatory)][string]$Model,
    [double]$StartPerMin = 0,
    [double]$EndPerMin = 40,
    [int]$RampMin = 15,
    [int]$DrainMin = 10,
    [double]$SearchPerMin = 4,
    [int]$Run = 1,
    [string]$Target = '192.168.68.69',
    [int]$Port = 8000,
    [string]$SutUser = 'admin',
    [string]$SutRepo = 'C:\Users\admin\Documents\GitHub\ict3113-p1-1-a1',
    [string]$SutOllama = 'C:\Users\admin\AppData\Local\Programs\Ollama\ollama.exe',
    [string]$SutCpuLog = 'C:\Users\admin\AppData\Local\Temp\stress_cpu.csv'
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not $env:JAVA_HOME -or -not (Test-Path "$env:JAVA_HOME\bin\java.exe")) {
    $jdk = Get-ChildItem 'C:\Program Files\Eclipse Adoptium', 'C:\Program Files\Microsoft', 'C:\Program Files\Java' -Directory -Filter 'jdk*' -ErrorAction SilentlyContinue |
        Where-Object { Test-Path "$($_.FullName)\bin\java.exe" } | Sort-Object Name -Descending | Select-Object -First 1
    if (-not $jdk) { throw 'No JDK found.' }
    $env:JAVA_HOME = $jdk.FullName
}
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
$jmeter = 'C:\tools\apache-jmeter-5.6.3\bin\jmeter.bat'
$base = "http://${Target}:$Port"
New-Item -ItemType Directory -Force results, logs | Out-Null

function Invoke-Sut([string]$cmd) {
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    $out = & ssh -o BatchMode=yes "$SutUser@$Target" $cmd 2>&1 | ForEach-Object { "$_" }
    $code = $LASTEXITCODE
    $ErrorActionPreference = $old
    if ($code -ne 0) { $out | Out-Host; throw "SSH command failed (exit $code): $cmd" }
    $out
}

$runId = "$Label-run$Run"
$file = "${Label}_run$Run"
if (Test-Path "results\$file.jtl") { throw "results for $runId already exist - never reuse a RUN_ID" }

Write-Host "[$runId] resetting SUT for $Model over SSH..."
Invoke-Sut "powershell -NoProfile -File $SutRepo\load_test\reset_sut.ps1 -Model $Model" | Out-Host
$waited = 0
while ($true) {
    try { $t = (Invoke-RestMethod "$base/stats" -TimeoutSec 10).total } catch { $t = $null }
    if ($t -eq 0) { break }
    Start-Sleep 5; $waited += 5
    if ($waited -ge 300) { throw "[$runId] SUT not reset (total=$t)" }
}

Write-Host "[$runId] warming up model..."
Invoke-RestMethod "$base/tickets" -Method Post -ContentType 'application/json' `
    -Body '{"narrative":"My bank froze my account and kept my paycheck."}' `
    -Headers @{ 'X-Run-ID' = "warmup-$runId" } -TimeoutSec 600 | Out-Null
$ps = (Invoke-Sut "$SutOllama ps") -join "`n"
$ps | Set-Content "results\${file}_ollama_ps.txt"
if ($ps -notmatch '100% CPU' -or $ps -notmatch [regex]::Escape($Model)) { throw "[$runId] ollama ps does not show $Model on 100% CPU:`n$ps" }

# CPU / memory sampler on the SUT: a PowerShell loop (sent base64-encoded, because the SUT's SSH
# shell is cmd.exe) writing one CSV row about every 5 s until a stop file appears or the time cap.
# Process CPU is divided by the logical core count, so every column is % of the whole machine.
$stopFile = "$SutCpuLog.stop"
$capSec = ($RampMin + $DrainMin) * 60 + 300
$sampler = @"
`$f='$SutCpuLog'; `$stop='$stopFile'; `$end=(Get-Date).AddSeconds($capSec)
Remove-Item `$f,`$stop -ErrorAction SilentlyContinue
`$cores=(Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors
'time,cpu_total_pct,avail_mb,ollama_cpu_pct,vmmem_cpu_pct' | Set-Content `$f
while ((Get-Date) -lt `$end -and -not (Test-Path `$stop)) {
  `$c = Get-Counter '\Processor(_Total)\% Processor Time','\Memory\Available MBytes','\Process(ollama*)\% Processor Time','\Process(llama-server*)\% Processor Time','\Process(vmmem*)\% Processor Time' -ErrorAction SilentlyContinue
  `$s = `$c.CounterSamples
  `$cpu = (`$s | Where-Object Path -like '*processor(_total)*').CookedValue
  `$mem = (`$s | Where-Object Path -like '*available mbytes').CookedValue
  `$oll = ((`$s | Where-Object { `$_.Path -like '*process(ollama*' -or `$_.Path -like '*process(llama-server*' }).CookedValue | Measure-Object -Sum).Sum / `$cores
  `$vm  = ((`$s | Where-Object Path -like '*process(vmmem*').CookedValue | Measure-Object -Sum).Sum / `$cores
  Add-Content `$f ('{0},{1:F1},{2:F0},{3:F1},{4:F1}' -f `$c.Timestamp.ToString('yyyy-MM-ddTHH:mm:ss'),`$cpu,`$mem,`$oll,`$vm)
  Start-Sleep 4
}
"@
$enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($sampler))
$job = Start-Job -ScriptBlock {
    param($u, $t, $cmd) & ssh -o BatchMode=yes "$u@$t" $cmd 2>&1 | Out-Null
} -ArgumentList $SutUser, $Target, "powershell -NoProfile -EncodedCommand $enc"
Start-Sleep 10   # let the sampler take baseline samples before load starts

Write-Host "[$runId] ramp $StartPerMin -> $EndPerMin tickets/min over $RampMin min + $DrainMin min drain, $SearchPerMin searches/min, started $(Get-Date -Format s)"
& $jmeter -n -t stress_ramp.jmx "-JHOST=$Target" "-JPORT=$Port" "-JRUN_ID=$runId" `
    "-JSTART_PER_MIN=$StartPerMin" "-JEND_PER_MIN=$EndPerMin" "-JRAMP_MIN=$RampMin" "-JDRAIN_MIN=$DrainMin" "-JSEARCH_PER_MIN=$SearchPerMin" `
    -l "results\$file.jtl" -j "logs\${file}_jmeter.log" | Select-Object -Last 3
Write-Host "[$runId] finished $(Get-Date -Format s)"

Start-Sleep 10   # one more idle CPU sample after the last request
try { Invoke-Sut "type nul > `"$stopFile`"" | Out-Null } catch { }   # sampler loop sees the stop file and exits
Wait-Job $job -Timeout 30 | Out-Null; Remove-Job $job -Force -ErrorAction SilentlyContinue

& scp -o BatchMode=yes "$SutUser@${Target}:$($SutRepo.Replace('\','/'))/logs/requests.jsonl" "logs\${file}_requests.jsonl"
if ($LASTEXITCODE -ne 0) { throw "[$runId] could not copy requests.jsonl from the SUT" }
& scp -o BatchMode=yes "$SutUser@${Target}:$($SutCpuLog.Replace('\','/'))" "results\${file}_cpu.csv"
if ($LASTEXITCODE -ne 0) { Write-Host "[$runId] WARNING: could not copy the CPU log from the SUT" }

$cnt = @(Select-String -Path "logs\${file}_requests.jsonl" -Pattern "`"$runId`"" -SimpleMatch).Count
$jtl = @(Import-Csv "results\$file.jtl")
Write-Host "[$runId] JMeter requests: $($jtl.Count)   SUT log lines for this run id: $cnt"
Write-Host "Done: $runId"
