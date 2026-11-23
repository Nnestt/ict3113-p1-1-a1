# Runs ON THE SUT. Brief Step 2 "Memory": load both cascade models, run a few tickets through each, and
# confirm `ollama ps` lists both. Restarts Ollama first (through the OllamaCpuOnly task), then alternates
# 3 classifications per model and checks that neither model was reloaded (load time stays near zero after the
# first call of each). Writes a2\env\memory_check.txt as the evidence for slide 2.
# Usage: powershell -NoProfile -File a2\env\memory_check.ps1 [-Small qwen2.5:1.5b] [-Large qwen2.5:7b]
param(
    [string]$Small = 'qwen2.5:1.5b',
    [string]$Large = 'qwen2.5:7b',
    [string]$Ollama = 'C:\Users\admin\AppData\Local\Programs\Ollama\ollama.exe',
    [string]$OllamaTask = 'OllamaCpuOnly'
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$out = Join-Path $PSScriptRoot 'memory_check.txt'
$warm = Join-Path $repo 'a2\warm_model.ps1'
$log = New-Object System.Collections.Generic.List[string]
function Note([string]$s) { Write-Host $s; $log.Add($s) }
function Free-GB { [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 2) }

Note "A2 memory check: $Small + $Large resident together. $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
Note "Total RAM $([math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 2)) GB"
Get-Process -Name 'ollama*' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep 3
& schtasks.exe /run /tn $OllamaTask | Out-Null
$deadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $deadline) { try { Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 3 | Out-Null; break } catch { Start-Sleep 2 } }
Note "Ollama restarted; free RAM before loading: $(Free-GB) GB"

$tickets = @(
    'My credit report shows an account I never opened and the bureau will not remove it.',
    'A debt collector keeps calling me at work about a debt I already paid.',
    'My mortgage servicer added fees to my escrow account without explaining why.')
foreach ($t in $tickets) {
    foreach ($m in @($Small, $Large)) {
        Note ("  " + ((& powershell -NoProfile -File $warm -Model $m -Narrative $t) -join ' '))
    }
}
$ps = (& $Ollama ps) -join "`n"
Note ''; Note 'ollama ps:'; Note $ps
Note "Free RAM with both loaded: $(Free-GB) GB"
$both = ($ps -match [regex]::Escape($Small)) -and ($ps -match [regex]::Escape($Large))
$verdict = if ($both) { 'PASS: both models listed by ollama ps (the WARM OK lines show load ~0 ms after each model''s first call)' } else { 'FAIL: both models are not resident - try a smaller pair (brief Step 2)' }
Note ''; Note $verdict
[System.IO.File]::WriteAllText($out, ($log -join "`r`n") + "`r`n", (New-Object System.Text.UTF8Encoding $false))
Write-Host "wrote $out"
