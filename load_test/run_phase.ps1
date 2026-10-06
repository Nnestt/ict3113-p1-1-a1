# Runs one phase of the test plan, fully automated.
# Run ON THE LOAD GENERATOR (JMeter PC), from load_test/:
#   .\run_phase.ps1 -Phase 1
#
# Phases 1-4: peak mixed load (R1, R2, R4), one model each, three 900 s open-loop
#   runs at 23 POST /tickets, 46 GET /search, 1 GET /stats per hour.
# Phase 5: R3 throughput, phi3.5:3.8b then qwen2.5:7b, three 900 s runs each at
#   46 POST /tickets per hour (searches -R3SearchRate, default 46; stats 1).
# Phase 6: stress test, qwen2.5:7b, one open-model ramp (run_stress.ps1).
#
# Phases 1-5 use run_model.ps1: before every run it resets the SUT over SSH
# (reset_sut.ps1: compose down -v, empty the request log, unload models, compose up
# with MODEL pinned), waits for /stats total = 0, warms the model up, checks
# `ollama ps` shows 100% CPU, runs JMeter, then copies the SUT request log back.
# 300 s cooldown between runs. Afterwards summarise_runs.py writes
# results\<label>_summary.md and fills results-record.md between the
# <!-- BEGIN label --> / <!-- END label --> markers.
#
# Resume after a failure: rerun with -StartRun N (run IDs are never reused;
# delete nothing - a failed run's files stay as evidence, start at the next N).
# For phase 5 also pass -Only <label> to resume just one model.
param(
    [Parameter(Mandatory)][ValidateRange(1, 6)][int]$Phase,
    [int]$StartRun = 1,
    [int]$Runs = 3,
    [int]$DurationSec = 900,
    [int]$R3SearchRate = 46,
    [string]$Only,
    # Phase 6 ramp settings (tickets per minute; see run_stress.ps1)
    [double]$EndPerMin = 40,
    [int]$RampMin = 15,
    [int]$DrainMin = 10,
    [double]$SearchPerMin = 4,
    # Pipeline check only: short run, label prefixed with smoke-, results record NOT touched.
    [switch]$Smoke
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$phases = @{
    1 = @(@{ Model = 'llama3.2:1b';  Label = 'llama1b-15m';  Ticket = 23; Search = 46 })
    2 = @(@{ Model = 'qwen2.5:1.5b'; Label = 'qwen1_5b-15m'; Ticket = 23; Search = 46 })
    3 = @(@{ Model = 'phi3.5:3.8b';  Label = 'phi3_8b-15m';  Ticket = 23; Search = 46 })
    4 = @(@{ Model = 'qwen2.5:7b';   Label = 'qwen7b-15m';   Ticket = 23; Search = 46 })
    5 = @(@{ Model = 'phi3.5:3.8b';  Label = 'phi3_8b-r3';   Ticket = 46; Search = $R3SearchRate },
          @{ Model = 'qwen2.5:7b';   Label = 'qwen7b-r3';    Ticket = 46; Search = $R3SearchRate })
    6 = @(@{ Model = 'qwen2.5:7b';   Label = 'qwen7b-stress' })
}
$items = @($phases[$Phase] | ForEach-Object { $_.Clone() })
if ($Only) { $items = @($items | Where-Object { $_.Label -eq $Only }) }
if ($items.Count -eq 0) { throw "nothing to run (check -Only)" }
New-Item -ItemType Directory -Force results, logs | Out-Null

foreach ($p in $items) {
    if ($Smoke) { $p.Label = "smoke-$($p.Label)" }
    $transcript = "logs\$($p.Label)_phase.log"
    Start-Transcript -Path $transcript -Append | Out-Null
    try {
        if ($Phase -eq 6) {
            $end = $EndPerMin; $ramp = $RampMin; $drain = $DrainMin
            if ($Smoke) { $end = 20; $ramp = 2; $drain = 2 }
            Write-Host "=== Phase 6 : stress $($p.Model) as $($p.Label), ramp 0 -> $end tickets/min over $ramp min + $drain min drain, started $(Get-Date -Format s) ==="
            & .\run_stress.ps1 -Label $p.Label -Model $p.Model -StartPerMin 0 -EndPerMin $end -RampMin $ramp -DrainMin $drain -SearchPerMin $SearchPerMin -Run $StartRun
            Write-Host "=== Phase 6 run finished $(Get-Date -Format s) ==="
            $recordArgs = if ($Smoke) { @() } else { @('--record', '..\results-record.md') }
            & python stress_summary.py $p.Label --run $StartRun @recordArgs
            if ($LASTEXITCODE -ne 0) { throw "stress_summary.py failed (exit $LASTEXITCODE)" }
            Write-Host "=== Phase 6 complete. Summary: results\$($p.Label)_run$($StartRun)_summary.md ==="
            continue
        }

        $dur = $DurationSec; $n = $Runs
        if ($Smoke) { $dur = 120; $n = 1 }
        Write-Host "=== Phase $Phase : $($p.Model) as $($p.Label), $($p.Ticket) tickets/hr, $($p.Search) searches/hr, runs $StartRun..$($StartRun + $n - 1), $dur s each, started $(Get-Date -Format s) ==="
        if ($Smoke) {
            & .\run_model.ps1 -Label $p.Label -Model $p.Model -Smoke -StartRun $StartRun
        } else {
            & .\run_model.ps1 -Label $p.Label -Model $p.Model -DurationSec $dur -Runs $n -StartRun $StartRun `
                -TicketRate $p.Ticket -SearchRate $p.Search -StatsRate 1
        }
        Write-Host "=== Phase $Phase $($p.Label) runs finished $(Get-Date -Format s) ==="

        $summary = "results\$($p.Label)_summary.md"
        $recordArgs = if ($Smoke) { @() } else { @('--record', '..\results-record.md') }
        & python summarise_runs.py $p.Label --duration $dur --out $summary @recordArgs
        if ($LASTEXITCODE -ne 0) { throw "summarise_runs.py failed (exit $LASTEXITCODE)" }
        if (Select-String -Path $summary -Pattern '\| NO \|' -Quiet) {
            Write-Host "WARNING: at least one run does not reconcile with the SUT log - see $summary"
        }
        Write-Host "=== Phase $Phase $($p.Label) complete. Summary: $summary ==="
    }
    finally {
        Stop-Transcript | Out-Null
    }
}
Write-Host "=== Phase $Phase complete $(Get-Date -Format s) ==="
