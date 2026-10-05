# Runs N consecutive load-test runs for ONE model, then prints a summary per run.
# Usage (from load_test/):
#   .\run_model.ps1 -Label qwen7b
#   .\run_model.ps1 -Label qwen7b -DurationSec 120 -TicketRate 60 -SearchRate 120   # smoke
# Before the first run, and between runs, reset the SUT (PC 1):
#   docker compose down -v ; docker compose up -d --build
# The script waits until /stats shows total=0 (i.e. you reset), then warms the model up.
param(
    [Parameter(Mandatory)][string]$Label,
    [int]$Runs = 3,
    [int]$DurationSec = 3600,
    [string]$Target = '192.168.68.69',
    [int]$Port = 8000,
    [int]$TicketRate = 23,
    [int]$SearchRate = 46,
    [int]$StatsRate = 1,
    [int]$StartRun = 1,
    [switch]$Smoke   # 1 run, 2 minutes, accelerated rates - checks the whole pipeline, not a result
)
$ErrorActionPreference = 'Stop'
if ($Smoke) {
    $Runs = 1; $DurationSec = 120; $TicketRate = 60; $SearchRate = 120; $StatsRate = 10
    if ($Label -notlike 'smoke*') { $Label = "smoke-$Label" }
}
Set-Location $PSScriptRoot
if (-not $env:JAVA_HOME) { $env:JAVA_HOME = 'C:\Program Files\Microsoft\jdk-21.0.12.101-hotspot' }   # fallback if the shell has none
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
$jmeter = 'C:\tools\apache-jmeter-5.6.3\bin\jmeter.bat'
$base = "http://${Target}:$Port"
New-Item -ItemType Directory -Force results, logs | Out-Null

function Get-Total {
    try { (Invoke-RestMethod "$base/stats" -TimeoutSec 10).total } catch { $null }
}
function Pct($sorted, $p) {
    if ($sorted.Count -eq 0) { return 0 }
    $sorted[[math]::Min($sorted.Count - 1, [math]::Ceiling($p / 100 * $sorted.Count) - 1)]
}
function Summarise($jtl) {
    Import-Csv $jtl | Group-Object label | ForEach-Object {
        $e = @($_.Group | ForEach-Object { [int]$_.elapsed } | Sort-Object)
        $bad = @($_.Group | Where-Object { $_.success -ne 'true' }).Count
        '{0,-14} n={1,-4} err={2,-3} ({3:P1})  p50={4}ms p95={5}ms p99={6}ms' -f $_.Name, $_.Count, $bad, ($bad / $_.Count), (Pct $e 50), (Pct $e 95), (Pct $e 99)
    }
}

for ($i = $StartRun; $i -lt $StartRun + $Runs; $i++) {
    $runId = "$Label-run$i"
    if (Test-Path "results\$($runId.Replace('-run','_run')).jtl") { throw "results for $runId already exist - never reuse a RUN_ID" }

    # Pre-flight: SUT reachable and freshly reset
    $waited = 0
    while ($true) {
        $t = Get-Total
        if ($null -eq $t) { Write-Host "[$runId] SUT unreachable at $base - waiting..." }
        elseif ($t -eq 0) { break }
        else { Write-Host "[$runId] SUT has $t stored tickets. Reset it on PC 1 (docker compose down -v; up -d --build). Waiting..." }
        Start-Sleep 15; $waited += 15
        if ($waited -ge 3600) { throw "Gave up waiting for a reset SUT" }
    }

    # Warm-up (loads the model; stored under a separate run id)
    Write-Host "[$runId] warming up model..."
    $body = '{"narrative":"My bank froze my account and kept my paycheck."}'
    Invoke-RestMethod "$base/tickets" -Method Post -ContentType 'application/json' -Body $body `
        -Headers @{ 'X-Run-ID' = "warmup-$runId" } -TimeoutSec 600 | Out-Null

    $file = $runId.Replace('-run', '_run')
    Write-Host "[$runId] starting $(Get-Date -Format s) for $DurationSec s"
    & $jmeter -n -t peak_mixed_load.jmx "-JHOST=$Target" "-JPORT=$Port" "-JRUN_ID=$runId" `
        "-JDURATION_SEC=$DurationSec" "-JTICKET_RATE=$TicketRate" "-JSEARCH_RATE=$SearchRate" "-JSTATS_RATE=$StatsRate" `
        -l "results\$file.jtl" -j "logs\${file}_jmeter.log" | Select-Object -Last 3
    Write-Host "[$runId] finished $(Get-Date -Format s)"
    Summarise "results\$file.jtl"
    Write-Host ''
}
Write-Host "Done: $Label x $Runs. Check results before switching model."
