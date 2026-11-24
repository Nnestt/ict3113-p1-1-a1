# Assignment 2 speed-test set-up (brief Step 4 "Set-up"). Runs ON THE LOAD GENERATOR; drives the SUT over SSH.
#  1. restart Ollama and do the normal warm-up (top model, single-7b)
#  2. send the 3 DIFFERENT typical tickets in a2/s_rows.csv to the top model, one at a time
#  3. S = the middle of the three times; then rate = one ticket every 2S, run length = S minutes (min 5),
#     HTTP timeout = 10S (min 5 minutes), pause = longer than the timeout by at least 1 minute
# Writes a2/speed_params.json (a2/CONTRACTS.md) and prints the git commands for commit 6 in plan.md.
# Usage (from load_test/ or a2/):  powershell -File ..\a2\measure_s.ps1
param(
    [string]$Target = '192.168.68.69',
    [int]$Port = 8000,
    [string]$SutUser = 'admin',
    [string]$SutRepo = 'C:\Users\admin\Documents\GitHub\ict3113-p1-1-a1',
    [switch]$Force
)
$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path $PSScriptRoot -Parent) 'load_test\a2_common.ps1')

$out = Join-Path $A2Repo 'a2\speed_params.json'
if ((Test-Path $out) -and -not $Force) { throw 'a2/speed_params.json already exists (use -Force only if no speed run has used it)' }
$warmups = @(Import-Csv (Join-Path $A2Repo 'a2\warmup_rows.csv'))
$sRows = @(Import-Csv (Join-Path $A2Repo 'a2\s_rows.csv'))
if ($sRows.Count -ne 3) { throw 'a2/s_rows.csv must hold exactly 3 rows' }

Invoke-Sut "powershell -NoProfile -File $SutRepo\load_test\reset_sut.ps1 -Config single-7b -RestartOllama" | Out-Host
foreach ($w in $warmups) { Send-Ticket $w.narrative 'measure-s-warmup' "measure-s-warmup_r$($w.row)" | Out-Null }

$times = @()
foreach ($r in $sRows) {
    $ms = Send-Ticket $r.narrative 'measure-s' "measure-s_r$($r.row)"
    Write-Host "row $($r.row): $ms ms"
    $times += $ms
}
$S = ($times | Sort-Object)[1] / 1000.0
$timeoutS = [math]::Max(10 * $S, 300)
$params = [ordered]@{
    S_s           = [math]::Round($S, 3)
    s_rows        = @($sRows | ForEach-Object { [int]$_.row })
    s_timings_ms  = $times
    rate_per_hour = [int][math]::Round(3600 / (2 * $S))
    load_min      = [int][math]::Max([math]::Ceiling($S), 5)
    timeout_ms    = [int]([math]::Ceiling($timeoutS) * 1000)
    pause_min     = [int]([math]::Ceiling($timeoutS / 60) + 1)
    measured_utc  = (Get-Date).ToUniversalTime().ToString('s') + 'Z'
}
[System.IO.File]::WriteAllText($out, ($params | ConvertTo-Json), (New-Object System.Text.UTF8Encoding $false))  # no BOM
Write-Host ("S = {0:N2} s -> {1} tickets/hour (one every {2:N1} s) for {3} min, timeout {4} s, pause {5} min" -f `
    $S, $params.rate_per_hour, (2 * $S), $params.load_min, ($params.timeout_ms / 1000), $params.pause_min)
Write-Host "Commit it (commit 6 in plan.md):"
Write-Host "  git add a2/speed_params.json"
Write-Host "  git commit -m `"A2 Step 4: speed-test set-up, S = $($params.S_s) s`""
Write-Host "  git push"
