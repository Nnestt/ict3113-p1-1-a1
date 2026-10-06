# Launches Ollama CPU-only for the load and stress tests. Runs ON THE SUT.
# Copy of C:\Users\admin\start-ollama-cpu.ps1 on the SUT (Intel Core Ultra 7 155H), which a
# Windows scheduled task "OllamaCpuOnly" runs at logon:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\Users\admin\start-ollama-cpu.ps1"
# Quit any Ollama already running (tray icon -> Quit) before starting it this way, so these
# settings apply. reset_sut.ps1 expects Ollama to be answering on 127.0.0.1:11434.
#
# Settings that affect the results:
#  - All GPU back ends hidden/disabled: inference is CPU only (`ollama ps` shows 100% CPU).
#  - OLLAMA_NUM_PARALLEL=1: one generation at a time; other requests queue inside Ollama.
#    This is the bottleneck found by the stress test (results-record.md, Stress Test).
#  - OLLAMA_KEEP_ALIVE=5m: a model stays loaded 5 minutes after its last request
#    (each run's warm-up request loads it; reset_sut.ps1 unloads models between runs).
$env:CUDA_VISIBLE_DEVICES = "-1"
$env:ROCR_VISIBLE_DEVICES = "-1"
$env:HIP_VISIBLE_DEVICES = "-1"
$env:GGML_VK_VISIBLE_DEVICES = "-1"
$env:OLLAMA_VULKAN = "0"
$env:OLLAMA_IGPU_ENABLE = "0"
$env:OLLAMA_NUM_PARALLEL = "1"
$env:OLLAMA_KEEP_ALIVE = "5m"
Remove-Item Env:OLLAMA_HOST -ErrorAction SilentlyContinue
$log = "$env:USERPROFILE\ollama_serve.log"
Start-Process "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" -ArgumentList "serve" -WindowStyle Hidden -RedirectStandardError $log -RedirectStandardOutput "$env:USERPROFILE\ollama_serve.out"
