# Runs ON THE SUT (Intel PC). Called over SSH by run_model.ps1 before every run.
# Resets the triage service to an empty state with the requested model pinned.
# Usage: powershell -NoProfile -File load_test\reset_sut.ps1 -Model qwen2.5:7b
param(
    [Parameter(Mandatory)][string]$Model,
    [string]$Docker = 'C:\Program Files\Docker\Docker\resources\bin\docker.exe',
    [string]$Ollama = 'C:\Users\admin\AppData\Local\Programs\Ollama\ollama.exe'
)
# Native tools write progress to stderr; 'Stop' would turn that into a failure on PS 5.1.
$ErrorActionPreference = 'Continue'
$repo = Split-Path $PSScriptRoot -Parent
Set-Location $repo
New-Item -ItemType Directory -Force logs | Out-Null

function Fail($msg) { Write-Host "RESET FAILED: $msg"; exit 1 }

# Ollama server must already be up (started by the OllamaCpuOnly logon task).
try { Invoke-RestMethod 'http://127.0.0.1:11434' -TimeoutSec 5 | Out-Null } catch { Fail 'Ollama is not answering on 127.0.0.1:11434' }

# Tear down the service and its volume.
& $Docker compose down -v 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { Fail 'docker compose down -v' }

# Unload every model so the next run starts cold-then-warmed-up the same way each time.
$loaded = & $Ollama ps | Select-Object -Skip 1 | Where-Object { $_.Trim() } | ForEach-Object { ($_ -split '\s+')[0] }
foreach ($m in $loaded) { & $Ollama stop $m | Out-Null }
Start-Sleep 3
if (@(& $Ollama ps | Select-Object -Skip 1 | Where-Object { $_.Trim() }).Count -gt 0) { Fail 'a model is still loaded after ollama stop' }

# Bring the service up pinned to the requested model.
$env:MODEL = $Model
& $Docker compose up -d --build 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { Fail 'docker compose up -d --build' }

# Wait for the service to answer with an empty store.
$deadline = (Get-Date).AddSeconds(180)
while ((Get-Date) -lt $deadline) {
    try {
        $s = Invoke-RestMethod 'http://localhost:8000/stats' -TimeoutSec 5
        if ($s.total -eq 0) { Write-Host "RESET OK model=$Model total=0 $(Get-Date -Format s)"; exit 0 }
    } catch { }
    Start-Sleep 3
}
Fail 'service did not report total=0 within 180 s'
