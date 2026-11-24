# A2 test environment (SUT)

Recorded 2026-11-24 01:05:06 +08:00 by `a2/env/record_env.ps1` at commit `d27aeab`.

| Item | Value |
|---|---|
| Machine | ASUSTeK COMPUTER INC. ASUS Zenbook 14 UX3405MA_UX3405MA |
| CPU | Intel(R) Core(TM) Ultra 7 155H (16 cores, 22 logical) |
| RAM | 31.37 GB |
| OS | Microsoft Windows 11 Home 10.0.26300 |
| Ollama | 0.35.1 (native on Windows, not a container) |
| Docker engine | 29.8.2 |
| WSL config | none (WSL 2 defaults) |
| Service options | {"temperature":0,"seed":42,"num_predict":16,"num_ctx":4096}, keep_alive 30m, timeout 300 s |

## Ollama settings (load_test/start-ollama-cpu.ps1, held constant for every configuration)

```
$env:CUDA_VISIBLE_DEVICES = "-1"
$env:ROCR_VISIBLE_DEVICES = "-1"
$env:HIP_VISIBLE_DEVICES = "-1"
$env:GGML_VK_VISIBLE_DEVICES = "-1"
$env:OLLAMA_VULKAN = "0"
$env:OLLAMA_IGPU_ENABLE = "0"
$env:OLLAMA_NUM_PARALLEL = "1"
$env:OLLAMA_KEEP_ALIVE = "5m"
$env:OLLAMA_MAX_LOADED_MODELS = "2"
```

## Model digests (local vs pinned)

| Model | Local digest | Pinned | Match | Size |
|---|---|---|---|---|
| llama3.2:1b | baf6a787fdffd633537aa2eb51cfd54cb93ff08e28040095462bb63daf552878 | baf6a787fdffd633537aa2eb51cfd54cb93ff08e28040095462bb63daf552878 | yes | 1.32 GB |
| qwen2.5:1.5b | 65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b | 65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b | yes | 0.99 GB |
| phi3.5:3.8b | 61819fb370a3c1a9be6694869331e5f85f867a079e9271d66cb223acb81d04ba | 61819fb370a3c1a9be6694869331e5f85f867a079e9271d66cb223acb81d04ba | yes | 2.18 GB |
| qwen2.5:7b | 845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e | 845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e | yes | 4.68 GB |

Load generator: unchanged from A1 (see results-record.md, Test Environment): JMeter 5.6.3 on the Ryzen 5 7600.
