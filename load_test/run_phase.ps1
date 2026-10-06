# Runs one phase of the 15-minute peak-load test plan, fully automated.
# Run ON THE LOAD GENERATOR (JMeter PC), from load_test/:
#   .\run_phase.ps1 -Phase 1
#
# Each phase = one model, three 900 s open-loop runs at the peak mixed load
# (23 POST /tickets, 46 GET /search, 1 GET /stats per hour). Before every run,
# run_model.ps1 resets the SUT over SSH (reset_sut.ps1: compose down -v, empty
# the request log, unload models, compose up with MODEL pinned), waits for
# /stats total = 0, warms the model up, checks `ollama ps` shows 100% CPU, runs
# JMeter, then copies the SUT request log back. 300 s cooldown between runs.
#
# Afterwards it writes results\<label>_summary.md (per-run p50/p95/p99, mean,
# spread, SD, and the JMeter-vs-SUT-log reconciliation) for results-record.md.
#
# Resume after a failure: rerun with -StartRun N (run IDs are never reused;
# delete nothing - a failed run's files stay as evidence, start at the next N).
param(
    [Parameter(Mandatory)][ValidateRange(1, 4)][int]$Phase,
    [int]$StartRun = 1,
    [int]$Runs = 3,
    [int]$DurationSec = 900,
    # Pipeline check only: 1 run, 120 s, accelerated rates (run_model.ps1 -Smoke),
    # label prefixed with smoke-, results record NOT touched.
    [switch]$Smoke
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$phases = @{
    1 = @{ Model = 'llama3.2:1b';  Label = 'llama1b-15m' }
    2 = @{ Model = 'qwen2.5:1.5b'; Label = 'qwen1_5b-15m' }
    3 = @{ Model = 'phi3.5:3.8b';  Label = 'phi3_8b-15m' }
    4 = @{ Model = 'qwen2.5:7b';   Label = 'qwen7b-15m' }
}
$p = $phases[$Phase].Clone()
if ($Smoke) { $p.Label = "smoke-$($p.Label)"; $DurationSec = 120; $Runs = 1 }
New-Item -ItemType Directory -Force results, logs | Out-Null
$transcript = "logs\$($p.Label)_phase.log"
Start-Transcript -Path $transcript -Append | Out-Null
try {
    Write-Host "=== Phase $Phase : $($p.Model) as $($p.Label), runs $StartRun..$($StartRun + $Runs - 1), $DurationSec s each, started $(Get-Date -Format s) ==="
    if ($Smoke) {
        & .\run_model.ps1 -Label $p.Label -Model $p.Model -Smoke -StartRun $StartRun
    } else {
        & .\run_model.ps1 -Label $p.Label -Model $p.Model -DurationSec $DurationSec -Runs $Runs -StartRun $StartRun
    }
    Write-Host "=== Phase $Phase runs finished $(Get-Date -Format s) ==="

    $summary = "results\$($p.Label)_summary.md"
    $recordArgs = if ($Smoke) { @() } else { @('--record', '..\results-record.md') }
    & python summarise_runs.py $p.Label --duration $DurationSec --out $summary @recordArgs
    if ($LASTEXITCODE -ne 0) { throw "summarise_runs.py failed (exit $LASTEXITCODE)" }
    if (Select-String -Path $summary -Pattern '\| NO \|' -Quiet) {
        Write-Host "WARNING: at least one run does not reconcile with the SUT log - see $summary"
    }
    Write-Host "=== Phase $Phase complete. Summary: $summary ==="
}
finally {
    Stop-Transcript | Out-Null
}
