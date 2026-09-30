# Performance and Accuracy Requirements

## Workload

Normal load:
- 12 ticket submissions/hour
- 23 searches/hour

Peak mixed load:
- 23 ticket submissions/hour
- 46 searches/hour
- Approximately 1 statistics request/hour

## Requirements

| ID | Requirement                | Load condition                | Pass condition                      |
|----|----------------------------|-------------------------------|-------------------------------------|
| R1 | Ticket response time       | Peak mixed load               | POST /tickets p95 ≤ 60 seconds      |
| R2 | Search response time       | Peak mixed load               | GET /search p95 ≤ 2 seconds         |
| R3 | Classification throughput  | Sustained load for 60 minutes | ≥46 successful classifications/hour |
| R4 | Reliability                | Peak mixed load               | Error rate <1%                      |
| R5 | Overall accuracy           | Frozen golden set             | ≥80%                                |
| R6 | Per-category accuracy      | Frozen golden set             | Every category ≥65%                 |

## Justification

# Requirement Justifications

## R1 Ticket Classification Response Time

**Requirement:** Under the peak mixed workload, the p95 response time for `POST /tickets` must not exceed 60 seconds.

**Justification:** Ticket classification is synchronous, meaning the submitting system must wait until the model completes classification. A 60-second p95 limit ensures that at least 95% of submissions complete within one minute and prevents the complaint-intake process from being blocked for an excessive period. This target allows for the slower performance expected from CPU-only model inference while still providing a usable service.

The requirement is measured at p95 instead of using the average because an acceptable average could conceal a smaller number of extremely slow requests.

## R2 Search Response Time

**Requirement:** Under the peak mixed workload, the p95 response time for `GET /search` must not exceed two seconds.

**Justification:** Unlike ticket classification, search does not require LLM inference and should therefore respond much faster. A two-second p95 limit allows retrieval of stored complaints without significant interruption to their workflow.

## R3 Classification Throughput

**Requirement:** The service must sustain at least 46 successful ticket classifications per hour for 60 minutes.

**Justification:** The workload model estimates a peak arrival rate of 23 new complaints per hour. The throughput requirement provides 100% capacity headroom:

Required throughput = peak arrival rate × headroom
                    = 23 × 2
                    = 46 classifications/hour

The additional capacity accounts for temporary complaint surges, workload-estimation uncertainty, future growth and the need to clear short backlogs. Testing for 60 minutes demonstrates sustained performance rather than a short burst of processing.

## R4 Error Rate

**Requirement:** The service error rate must remain below 1% under the peak mixed workload.

**Justification:** Failed requests require retries or manual intervention and can cause complaints to be delayed or lost. An error rate below 1% means that at least 99% of requests complete successfully under the expected peak workload. This provides a clear reliability target while recognising that occasional failures may occur in the baseline system.

A request is considered unsuccessful if it produces a timeout, connection failure, invalid server response or HTTP error response.

## R5 Overall Classification Accuracy

**Requirement:** Each candidate model must achieve at least 80% overall classification accuracy on the golden test set.

**Justification:** An 80% requirement means that at least four out of five complaints are routed correctly. This represents a meaningful improvement over random selection between seven categories while limiting the operational cost of manually correcting misrouted complaints. The requirement also provides a practical starting point for a CPU-only baseline, where greater model accuracy may require a larger and slower model.

## R6 Per-Category Classification Accuracy

**Requirement:** Each candidate model must achieve at least 65% accuracy in every complaint category represented in the golden test set.

**Justification:** Overall accuracy alone can hide poor performance in categories with fewer test examples. A model could achieve high overall accuracy by performing well on common categories while repeatedly misclassifying less common categories. The per-category requirement ensures that every customer complaint type receives a minimum acceptable level of classification performance.

The 65% threshold is lower than the overall 80% target because individual categories contain fewer golden-set examples and may include complaints that overlap semantically with other categories. Nevertheless, a model that falls below 65% in any category would create an unacceptably high risk of systematically misrouting that type of complaint.

## Workload Condition

The peak mixed workload consists of approximately:

- 23 `POST /tickets` requests per hour
- 46 `GET /search` requests per hour
- 1 `GET /stats` request per hour

The ticket arrival rate is based on the annual complaint-volume benchmark and a two-times peak multiplier. The search rate assumes two searches per submitted complaint. The statistics rate assumes approximately one statistics request for every 20 submitted complaints.

The peak multiplier, search ratio and statistics ratio are modelling assumptions because no public hourly or endpoint-level usage data were available. These assumptions will be tested through sensitivity and stress testing.

## Interpretation

The throughput target is derived directly from the calculated peak workload and capacity headroom. The response-time, reliability and accuracy thresholds are team-defined service objectives based on usability and the operational impact of delays, failures and misrouted complaints. They should not be presented as figures published by AFCA.
