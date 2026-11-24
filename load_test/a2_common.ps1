# Shared helpers for the Assignment 2 load-generator scripts (run_a2.ps1, ..\a2\measure_s.ps1).
# Dot-source it:  . "$PSScriptRoot\a2_common.ps1"   (expects $Target, $Port, $SutUser to be set by the caller)

$A2Repo = Split-Path $PSScriptRoot -Parent
$A2Configs = Get-Content (Join-Path $A2Repo 'a2\configs.json') -Raw | ConvertFrom-Json

# Models a config calls, from a2/configs.json
function Get-ConfigModels([string]$name) {
    $c = $A2Configs.$name
    if (-not $c) { throw "unknown config '$name' (see a2/configs.json)" }
    if ($c.mode -eq 'single') { return @($c.model) }
    return @($c.small, $c.large)
}

# Runs a command on the SUT over SSH; PS 5.1 turns native stderr into errors under 'Stop', so judge by exit code
function Invoke-Sut([string]$cmd) {
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    $out = & ssh -o BatchMode=yes "$SutUser@$Target" $cmd 2>&1 | ForEach-Object { "$_" }
    $code = $LASTEXITCODE
    $ErrorActionPreference = $old
    if ($code -ne 0) { $out | Out-Host; throw "SSH command failed (exit $code): $cmd" }
    $out
}

# POSTs one ticket; returns elapsed ms. UTF-8 body bytes so non-ASCII narratives are sent correctly.
function Send-Ticket([string]$narrative, [string]$runId, [string]$requestId, [int]$timeoutSec = 600) {
    $json = @{ narrative = $narrative } | ConvertTo-Json -Compress
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    Invoke-RestMethod "http://${Target}:$Port/tickets" -Method Post -ContentType 'application/json; charset=utf-8' `
        -Body $bytes -Headers @{ 'X-Run-ID' = $runId; 'X-Request-ID' = $requestId } -TimeoutSec $timeoutSec | Out-Null
    $sw.Stop()
    [math]::Round($sw.Elapsed.TotalMilliseconds, 1)
}

function Get-Stats { Invoke-RestMethod "http://${Target}:$Port/stats" -TimeoutSec 30 }

# Fails unless every model is listed by `ollama ps` on a 100% CPU line
function Assert-Resident([string[]]$models, [string]$psText, [string]$when) {
    foreach ($m in $models) {
        $line = ($psText -split "`n") | Where-Object { $_ -match "^$([regex]::Escape($m))\s" }
        if (-not $line -or $line -notmatch '100% CPU') {
            throw "[$when] ollama ps does not show $m loaded at 100% CPU:`n$psText"
        }
    }
}

# Finds a JDK if the shell has none (same as run_model.ps1)
function Use-Jdk {
    if (-not $env:JAVA_HOME -or -not (Test-Path "$env:JAVA_HOME\bin\java.exe")) {
        $jdk = Get-ChildItem 'C:\Program Files\Eclipse Adoptium', 'C:\Program Files\Microsoft', 'C:\Program Files\Java' -Directory -Filter 'jdk*' -ErrorAction SilentlyContinue |
            Where-Object { Test-Path "$($_.FullName)\bin\java.exe" } | Sort-Object Name -Descending | Select-Object -First 1
        if (-not $jdk) { throw 'No JDK found. Install one (see SECOND_PC_SETUP.md step 2) or set JAVA_HOME.' }
        $env:JAVA_HOME = $jdk.FullName
    }
    $env:Path = "$env:JAVA_HOME\bin;$env:Path"
}
