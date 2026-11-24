# Runs ON THE SUT (Intel PC). Called over SSH by run_model.ps1 (A1) and run_a2.ps1 / a2\measure_s.ps1 (A2).
# Resets the triage service to an empty state with the requested model or A2 configuration.
# Usage: powershell -NoProfile -File load_test\reset_sut.ps1 -Model qwen2.5:7b                       (A1)
#        powershell -NoProfile -File load_test\reset_sut.ps1 -Config cascade-S1 -RestartOllama      (A2)
# -Config takes a name from a2\configs.json and sets the service env vars (a2\CONTRACTS.md).
# -RestartOllama stops every Ollama process and starts it again through the OllamaCpuOnly scheduled task
#  (start-ollama-cpu.ps1, so the CPU-only settings apply). This clears Ollama's prompt cache (brief Step 4).
#  The task is used because a process started from an SSH session can be killed when the session closes.
param(
    [string]$Model,
    [string]$Config,
    [switch]$RestartOllama,
    [string]$Docker = 'C:\Program Files\Docker\Docker\resources\bin\docker.exe',
    [string]$Ollama = 'C:\Users\admin\AppData\Local\Programs\Ollama\ollama.exe',
    [string]$OllamaTask = 'OllamaCpuOnly'
)
# Native tools write progress to stderr; 'Stop' would turn that into a failure on PS 5.1.
$ErrorActionPreference = 'Continue'
$repo = Split-Path $PSScriptRoot -Parent
Set-Location $repo
New-Item -ItemType Directory -Force logs | Out-Null

function Fail($msg) { Write-Host "RESET FAILED: $msg"; exit 1 }

# Over SSH there is no interactive logon session, so Docker Desktop's credential helper
# ("credsStore": "desktop") fails with "A specified logon session does not exist".
# Use a private Docker config with no credential store (public base image, anonymous pull),
# the Docker Desktop engine pipe, and the Compose plugin directory. The user's own config is untouched.
$cfg = Join-Path $env:USERPROFILE '.docker-ssh'
New-Item -ItemType Directory -Force $cfg | Out-Null
$plugins = Join-Path (Split-Path $Docker -Parent) '..\cli-plugins'
$plugins = (Resolve-Path $plugins).Path.Replace('\', '\\')
'{"cliPluginsExtraDirs":["' + $plugins + '"]}' | Set-Content (Join-Path $cfg 'config.json') -Encoding ascii
$env:DOCKER_CONFIG = $cfg
# With no credsStore, Docker auto-detects docker-credential-wincred on PATH (same folder as docker.exe),
# which needs a logon session. Hide that folder; $Docker is called by full path so it still runs.
$env:Path = ($env:Path -split ';' | Where-Object { $_ -and $_ -notmatch 'Docker\\Docker\\resources\\bin' }) -join ';'
$env:DOCKER_HOST = 'npipe:////./pipe/dockerDesktopLinuxEngine'

# Service environment: an A1 model, or an A2 configuration from a2\configs.json
if ($Config) {
    $all = Get-Content (Join-Path $repo 'a2\configs.json') -Raw | ConvertFrom-Json
    $c = $all.$Config
    if (-not $c) { Fail "unknown config '$Config' (see a2\configs.json)" }
    $env:TRIAGE_CONFIG = $Config
    $env:TRIAGE_MODE = $c.mode
    if ($c.mode -eq 'single') { $env:MODEL = $c.model }
    else { $env:SMALL_MODEL = $c.small; $env:LARGE_MODEL = $c.large; $env:CASCADE_SETTING = $c.setting }
    $label = $Config
} elseif ($Model) {
    $env:TRIAGE_MODE = 'single'; $env:MODEL = $Model; $label = $Model
} else { Fail 'give -Model or -Config' }

if ($RestartOllama) {
    Get-Process -Name 'ollama*' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep 3
    if (Get-Process -Name 'ollama*' -ErrorAction SilentlyContinue) { Fail 'an Ollama process is still running after Stop-Process' }
    & schtasks.exe /run /tn $OllamaTask | Out-Host
    if ($LASTEXITCODE -ne 0) { Fail "could not start scheduled task $OllamaTask" }
    $up = $false
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
        try { $v = Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 3; $up = $true; break } catch { Start-Sleep 2 }
    }
    if (-not $up) { Fail "Ollama did not come back within 60 s after restarting task $OllamaTask" }
    Write-Host "OLLAMA RESTARTED version=$($v.version) $(Get-Date -Format s)"
}

# Ollama server must be up (started by the OllamaCpuOnly logon task).
try { Invoke-RestMethod 'http://127.0.0.1:11434' -TimeoutSec 5 | Out-Null } catch { Fail 'Ollama is not answering on 127.0.0.1:11434' }

# Tear down the service and its volume.
& $Docker compose down -v 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { Fail 'docker compose down -v' }

# The service appends to logs/requests.jsonl through a bind mount, so 'down -v' does not clear it.
# Empty it (the container is gone, so nothing holds it open) so each run's log starts clean.
Set-Content -Path (Join-Path $repo 'logs\requests.jsonl') -Value $null -NoNewline
if ((Get-Item (Join-Path $repo 'logs\requests.jsonl')).Length -ne 0) { Fail 'could not empty logs\requests.jsonl' }

# Unload every model so the next run starts cold-then-warmed-up the same way each time.
$loaded = & $Ollama ps | Select-Object -Skip 1 | Where-Object { $_.Trim() } | ForEach-Object { ($_ -split '\s+')[0] }
foreach ($m in $loaded) { & $Ollama stop $m | Out-Null }
Start-Sleep 3
if (@(& $Ollama ps | Select-Object -Skip 1 | Where-Object { $_.Trim() }).Count -gt 0) { Fail 'a model is still loaded after ollama stop' }

# Bring the service up pinned to the requested model or configuration.
& $Docker compose up -d --build 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { Fail 'docker compose up -d --build' }

# Wait for the service to answer with an empty store.
$deadline = (Get-Date).AddSeconds(180)
while ((Get-Date) -lt $deadline) {
    try {
        $s = Invoke-RestMethod 'http://localhost:8000/stats' -TimeoutSec 5
        if ($s.total -eq 0) { Write-Host "RESET OK config=$label total=0 $(Get-Date -Format s)"; exit 0 }
    } catch { }
    Start-Sleep 3
}
Fail 'service did not report total=0 within 180 s'
