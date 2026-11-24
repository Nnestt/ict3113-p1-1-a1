# Runs ON THE SUT. Loads and warms one model directly in Ollama with the same prompt template and the
# same generation options as the service (service/eval_config.json), so Ollama keeps the loaded copy for the
# service's calls (a different num_ctx would make it reload). Used by load_test/run_a2.ps1 to make sure the
# cascade's large model is resident before a speed run, and by a2/env/memory_check.ps1.
# Usage: powershell -NoProfile -File a2\warm_model.ps1 -Model qwen2.5:7b
param([Parameter(Mandatory)][string]$Model, [string]$Narrative = 'I was charged a monthly maintenance fee on my checking account that I was told would be waived.')
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$cfg = Get-Content (Join-Path $repo 'service\eval_config.json') -Raw | ConvertFrom-Json
if (-not ($cfg.models.PSObject.Properties.Name -contains $Model)) { throw "$Model is not a pinned model" }
$template = (Get-Content (Join-Path $repo "service\$($cfg.prompt_file)") -Raw).TrimEnd()
$body = @{ model = $Model; prompt = $template.Replace('{narrative}', $Narrative.Trim()); stream = $false
           options = $cfg.options; keep_alive = $cfg.keep_alive } | ConvertTo-Json -Depth 5 -Compress
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$r = Invoke-RestMethod 'http://127.0.0.1:11434/api/generate' -Method Post -ContentType 'application/json; charset=utf-8' `
    -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) -TimeoutSec 600
Write-Host ("WARM OK {0} in {1:N0} ms (load {2:N0} ms): {3}" -f $Model, $sw.Elapsed.TotalMilliseconds, ($r.load_duration / 1e6), $r.response.Trim())
