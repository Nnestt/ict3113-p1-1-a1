# Prediction Record

**Date recorded:** 30 September 2026  
**Benchmark status when recorded:** No benchmark results observed  
**Golden test set status:** Frozen before model testing  

## Purpose

This record states the team's predictions before accuracy, load, or stress testing. The values below are estimates rather than measured results. They must not be revised after benchmark results are observed. Differences between these predictions and the measurements will be analysed in the final presentation.

## Test Environment

- **Processor:** Intel(R) Core(TM) Ultra 7 155H
- **System memory:** 31.37 GB RAM
- **Operating system:** Microsoft Windows 11 Home 10.0.26200
- **Inference platform:** Ollama
- **Inference device:** CPU only
- **GPU inference:** Not permitted and not used
- **Classification design:** Synchronous; each `POST /tickets` request waits for Ollama to return a category

## Candidate Models

| Model     | Parameter class | Exact Ollama tag | Ollama digest or ID                                              | License                                    |
|-----------|-----------------|------------------|------------------------------------------------------------------|--------------------------------------------|
| Llama 3.2 | 1B              | `llama3.2:1b`    | baf6a787fdffd633537aa2eb51cfd54cb93ff08e28040095462bb63daf552878 | Llama 3.2 Community License Agreement      |
| Qwen 2.5  | 1.5B            | `qwen2.5:1.5b`   | 65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b | Apache License, Version 2.0                |
| Phi 3.5   | 3.8B            | `phi3.5:3.8b`    | 61819fb370a3c1a9be6694869331e5f85f867a079e9271d66cb223acb81d04ba | MIT License                                |
| Qwen 2.5  | 7B              | `qwen2.5:7b`     | 845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e | Apache License, Version 2.0                |


## Predicted Accuracy and Single-Request Latency

Single-request latency is defined as the end-to-end time for one warm `POST /tickets` request when no other requests are being processed. The prediction includes the service request, prompt processing, CPU inference, storage, and response, but excludes initial model download and cold model loading.

| Model | Predicted overall accuracy | Predicted single-request latency | Predicted accuracy result |
|---|---:|---:|---|
| `llama3.2:1b`  | 68% | 2.5 seconds | Fail 80% overall target      |
| `qwen2.5:1.5b` | 73% | 3.5 seconds | Fail 80% overall target      |
| `phi3.5:3.8b`  | 79% | 7 seconds   | Fail overall target narrowly |
| `qwen2.5:7b`   | 84% | 12 seconds  | Pass 80% overall target      |

These latency predictions are deliberately specific and may be incorrect. They are based on the expected increase in CPU computation as model parameter count grows, rather than on measurements from the test system.

## Predicted Throughput

The simple sequential upper-bound estimate is calculated as:

```text
Predicted classifications per hour = 3,600 seconds / predicted single-request latency
```

| Model | Calculation | Predicted sequential upper bound | Predicted result against 46 classifications/hour |
|---|---:|---:|---|
| `llama3.2:1b`  | 3,600 / 2.5 | 1,440/hour               | Pass |
| `qwen2.5:1.5b` | 3,600 / 3.5 | Approximately 1,029/hour | Pass |
| `phi3.5:3.8b`  | 3,600 / 7   | Approximately 514/hour   | Pass |
| `qwen2.5:7b`   | 3,600 / 12  | 300/hour                 | Pass |

These values are theoretical upper bounds, not measured throughput. Actual throughput is predicted to be lower because of prompt evaluation, storage, HTTP overhead, operating-system scheduling, concurrent search traffic, queuing, and occasional model-loading effects.

## Predicted Ordering

### Accuracy from highest to lowest

1. `qwen2.5:7b`
2. `phi3.5:3.8b`
3. `qwen2.5:1.5b`
4. `llama3.2:1b`

The larger models are predicted to follow category definitions and distinguish overlapping complaint narratives more reliably. The 7B Qwen model is therefore predicted to be the most accurate, while the 1B Llama model is predicted to make the most classification errors.

### Speed from fastest to slowest

1. `llama3.2:1b`
2. `qwen2.5:1.5b`
3. `phi3.5:3.8b`
4. `qwen2.5:7b`

CPU inference time is predicted to rise with model parameter count. The available 31.37 GB of RAM should be sufficient to hold each candidate model, so CPU computation is expected to have a greater effect on latency than memory capacity.

## Bottleneck Prediction

**Predicted bottleneck:** CPU-based Ollama model inference.

The service performs classification synchronously, so each `POST /tickets` request remains open until Ollama returns a category. As ticket arrival rate approaches a model's service rate, classification requests are predicted to queue. This is expected to cause p95 and p99 response times to increase before the database search and statistics endpoints reach their limits.

The effect is predicted to be strongest for `qwen2.5:7b` because it requires the most CPU computation per request. System memory is not predicted to be the first bottleneck because the machine has 31.37 GB of RAM and each candidate model should fit in memory individually. If Ollama unloads and reloads models between configurations, cold-start delay may temporarily dominate latency.

## Hardest Category Predictions

| Predicted difficult category | Expected confusion | Reason |
|---|---|---|
| Consumer loan | Debt collection | A narrative may describe both the original loan and later attempts to collect an overdue balance. The model may classify the complaint by the debt collector rather than the underlying loan product. |
| Debt collection | Consumer loan or credit reporting | Debt-collection narratives frequently mention loans, missed payments, disputed balances, and negative credit reports, creating overlap with two other categories. |
| Credit card | Bank account or service | Both categories can involve unauthorised transactions, fees, account access, fraud, and poor bank service. The product may only become clear from a small part of the narrative. |
| Money transfer or service | Bank account or service | Transfer failures, delayed funds, unauthorised payments, and account restrictions can be described as general bank-account problems rather than transfer-specific problems. |

Credit reporting is predicted to be among the easier categories because its narratives often contain distinctive references to credit reports, credit bureaus, inaccurate entries, disputes, and credit scores. Mortgage is also predicted to be relatively distinctive when narratives explicitly mention home loans, mortgage servicing, escrow, foreclosure, or property payments.

## Predicted Per-Category Requirement Outcomes

| Model | Prediction against minimum 65% accuracy in every category |
|---|---|
| `llama3.2:1b`  | Fail; predicted to fall below 65% in several overlapping categories |
| `qwen2.5:1.5b` | Fail; predicted to fall below 65% in at least one difficult category |
| `phi3.5:3.8b`  | Borderline; predicted to meet the threshold in most categories but fall below it in at least one difficult category |
| `qwen2.5:7b`   | Pass; predicted to meet or exceed 65% in every category |

## Falsifiable Predictions

1. `llama3.2:1b` will achieve 68% overall accuracy and 2.5-second warm single-request latency.
2. `qwen2.5:1.5b` will achieve 73% overall accuracy and 3.5-second warm single-request latency.
3. `phi3.5:3.8b` will achieve 79% overall accuracy and 7-second warm single-request latency.
4. `qwen2.5:7b` will achieve 84% overall accuracy and 12-second warm single-request latency.
5. `qwen2.5:7b` will be the most accurate and slowest candidate.
6. `llama3.2:1b` will be the fastest and least accurate candidate.
7. CPU-based Ollama inference will become the primary bottleneck under increasing ticket load.
8. Consumer loan, debt collection, credit card, bank account or service, and money transfer or service will produce the largest category confusions.
9. All four models will exceed the sustained-throughput requirement of 46 successful classifications per hour, although the larger models will show greater p95 and p99 latency growth under stress.

## Freeze Statement

This prediction record was prepared before the team examined candidate-model outputs on the golden test set and before the first formal benchmark run. After the model digests have been inserted and this file has been committed, the predictions above must not be modified. Incorrect predictions will be retained and compared with the measured results in the final presentation.
