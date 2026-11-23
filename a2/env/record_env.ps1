# Runs ON THE SUT. Records the test environment before the first A2 run (brief Step 4: software versions,
# model digests and Ollama settings). Re-run before each configuration's runs and diff against the committed
# file to show nothing changed:  powershell -File a2\env\record_env.ps1 -Out $env:TEMP\env_now.md ; fc.exe ...
# Usage: powershell -NoProfile -File a2\env\record_env.ps1            (writes a2\env\environment.md)
param(
    [string]$Out,
    [string]$Docker = 'C:\Program Files\Docker\Docker\resources\bin\docker.exe',
    [string]$Ollama = 'C:\Users\admin\AppData\Local\Programs\Ollama\ollama.exe'
)
$ErrorActionPreference = 'Continue'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not $Out) { $Out = Join-Path $PSScriptRoot 'environment.md' }

$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$os = Get-CimInstance Win32_OperatingSystem
$cs = Get-CimInstance Win32_ComputerSystem
$pins = (Get-Content (Join-Path $repo 'service\eval_config.json') -Raw | ConvertFrom-Json)
$ollamaVersion = (Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 5).version
$tags = (Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 10).models
$startScript = Get-Content (Join-Path $repo 'load_test\start-ollama-cpu.ps1') | Where-Object { $_ -match '^\$env:' }
$dockerVersion = (& $Docker version --format '{{.Server.Version}}' 2>$null) -join ''
$wsl = if (Test-Path "$env:USERPROFILE\.wslconfig") { (Get-Content "$env:USERPROFILE\.wslconfig") -join '; ' } else { 'none (WSL 2 defaults)' }
$head = (& git -C $repo rev-parse --short HEAD 2>$null) -join ''

$lines = @(
    '# A2 test environment (SUT)', '',
    "Recorded $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz') by ``a2/env/record_env.ps1`` at commit ``$head``.", '',
    '| Item | Value |', '|---|---|',
    "| Machine | $($cs.Manufacturer) $($cs.Model) |",
    "| CPU | $($cpu.Name.Trim()) ($($cpu.NumberOfCores) cores, $($cpu.NumberOfLogicalProcessors) logical) |",
    "| RAM | $([math]::Round($cs.TotalPhysicalMemory / 1GB, 2)) GB |",
    "| OS | $($os.Caption) $($os.Version) |",
    "| Ollama | $ollamaVersion (native on Windows, not a container) |",
    "| Docker engine | $dockerVersion |",
    "| WSL config | $wsl |",
    "| Service options | $(($pins.options | ConvertTo-Json -Compress)), keep_alive $($pins.keep_alive), timeout $($pins.request_timeout_seconds) s |",
    '', '## Ollama settings (load_test/start-ollama-cpu.ps1, held constant for every configuration)', '', '```')
$lines += $startScript
$lines += @('```', '', '## Model digests (local vs pinned)', '', '| Model | Local digest | Pinned | Match | Size |', '|---|---|---|---|---|')
foreach ($m in $pins.models.PSObject.Properties) {
    $t = $tags | Where-Object { $_.name -eq $m.Name }
    $match = if ($t -and $t.digest -eq $m.Value) { 'yes' } else { '**NO**' }
    $lines += "| $($m.Name) | $($t.digest) | $($m.Value) | $match | $([math]::Round($t.size / 1e9, 2)) GB |"
}
$lines += @('', 'Load generator: unchanged from A1 (see results-record.md, Test Environment): JMeter 5.6.3 on the Ryzen 5 7600.', '')
[System.IO.File]::WriteAllText($Out, ($lines -join "`n"), (New-Object System.Text.UTF8Encoding $false))
Write-Host "wrote $Out"
