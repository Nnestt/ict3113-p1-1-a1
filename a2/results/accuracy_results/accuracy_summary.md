# A2 accuracy results: test set

All 6 configurations on the 87 test tickets (`a2/split/test_rows.csv`), each ticket posted once through `POST /tickets`. An `INVALID` reply or an error counts as wrong.

## 1. Result

| Configuration | Correct | Accuracy | 95% CI (Wilson) | Overall limit | Category limits | Verdict |
|---|---|---|---|---|---|---|
| qwen2.5:7b | 70/87 | 80.5% | 70.9-87.4% | reference | reference | reference |
| phi3.5:3.8b | 69/87 | 79.3% | 69.6-86.5% | PASS | FAIL: CredRep | **FAIL** |
| qwen2.5:1.5b | 46/87 | 52.9% | 42.5-63.0% | FAIL | FAIL: Debt, Mortgage, Bank, Loan, Transfer | **FAIL** |
| llama3.2:1b | 20/87 | 23.0% | 15.4-32.9% | FAIL | FAIL: Debt, Mortgage, Card, Bank, Loan, Transfer | **FAIL** |
| Cascade S1 | 68/87 | 78.2% | 68.4-85.5% | PASS | PASS | **PASS** |
| Cascade S2 | 59/87 | 67.8% | 57.4-76.7% | FAIL | FAIL: Debt, Mortgage, Bank | **FAIL** |

## 2. Limits (from qwen2.5:7b on the test set)

- **Overall:** 80.5% - 10 points = **70.5%**, so at least 62/87 correct.
- **Per category:** 7b - 15 points:

| Category | Test tickets | 7b | Limit | Minimum correct | One ticket is worth |
|---|---|---|---|---|---|
| Credit reporting | 18 | 17/18 (94.4%) | 79.4% | 15/18 | 5.6 points |
| Debt collection | 13 | 10/13 (76.9%) | 61.9% | 9/13 | 7.7 points |
| Mortgage | 10 | 9/10 (90.0%) | 75.0% | 8/10 | 10.0 points |
| Credit card (small) | 9 | 6/9 (66.7%) | 51.7% | 5/9 | 11.1 points |
| Bank account or service | 19 | 14/19 (73.7%) | 58.7% | 12/19 | 5.3 points |
| Consumer loan (small) | 9 | 8/9 (88.9%) | 73.9% | 7/9 | 11.1 points |
| Money transfer or service (small) | 9 | 6/9 (66.7%) | 51.7% | 5/9 | 11.1 points |

**(small)** = fewer than 10 tickets, so the 15-point limit is not a fair test: losing 2 tickets already fails it. Mortgage, with exactly 10, is in the same position.

## 3. Accuracy per category

Bold = below the limit.

| Category | qwen2.5:7b | phi3.5:3.8b | qwen2.5:1.5b | llama3.2:1b | Cascade S1 | Cascade S2 |
|---|---|---|---|---|---|---|
| Credit reporting | 17/18 (94.4%) | **14/18 (77.8%)** | 17/18 (94.4%) | 16/18 (88.9%) | 17/18 (94.4%) | 18/18 (100.0%) |
| Debt collection | 10/13 (76.9%) | 10/13 (76.9%) | **4/13 (30.8%)** | **3/13 (23.1%)** | 9/13 (69.2%) | **7/13 (53.8%)** |
| Mortgage | 9/10 (90.0%) | 8/10 (80.0%) | **4/10 (40.0%)** | **0/10 (0.0%)** | 9/10 (90.0%) | **6/10 (60.0%)** |
| Credit card | 6/9 (66.7%) | 6/9 (66.7%) | 7/9 (77.8%) | **0/9 (0.0%)** | 6/9 (66.7%) | 6/9 (66.7%) |
| Bank account or service | 14/19 (73.7%) | 15/19 (78.9%) | **4/19 (21.1%)** | **1/19 (5.3%)** | 14/19 (73.7%) | **10/19 (52.6%)** |
| Consumer loan | 8/9 (88.9%) | 8/9 (88.9%) | **6/9 (66.7%)** | **0/9 (0.0%)** | 7/9 (77.8%) | 7/9 (77.8%) |
| Money transfer or service | 6/9 (66.7%) | 8/9 (88.9%) | **4/9 (44.4%)** | **0/9 (0.0%)** | 6/9 (66.7%) | 5/9 (55.6%) |
| **Overall** | 70/87 (80.5%) | 69/87 (79.3%) | **46/87 (52.9%)** | **20/87 (23.0%)** | 68/87 (78.2%) | **59/87 (67.8%)** |

## 4. Cascade: escalation

| | Cascade S1 | Cascade S2 |
|---|---|---|
| Accept list | Bank, Mortgage | Bank, CredRep, Debt, Mortgage |
| Escalated to 7b | 77/87 (88.5%) | 40/87 (46.0%) |
| Accuracy of accepted tickets (1.5b answered) | 8/10 (80.0%) | 29/47 (61.7%) |
| Accuracy of escalated tickets (7b answered) | 60/77 (77.9%) | 30/40 (75.0%) |
| 1.5b on the escalated tickets, had it answered | 38/77 (49.4%) | 17/40 (42.5%) |
| 7b alone on the accepted tickets | 10/10 (100.0%) | 40/47 (85.1%) |

Accepted answers by label (right / accepted), against the tuning-set rate used for the rule:

| 1.5b label | Tuning | S1 test | S2 test |
|---|---|---|---|
| Bank account or service | 4/4 (100.0%) | 4/4 (100.0%) | 4/4 (100.0%) |
| Mortgage | 6/7 (85.7%) | 4/6 (66.7%) | 4/6 (66.7%) |
| Credit reporting | 14/20 (70.0%) | escalated | 17/33 (51.5%) |
| Debt collection | 5/8 (62.5%) | escalated | 4/4 (100.0%) |

- **S2 fails mainly on Credit reporting.** 1.5b gave that label to 33 test tickets and only 17 were right (51.5%, against 70.0% on tuning). Of the 12 tickets 7b alone got right but S2 got wrong, 10 were kept as Credit reporting and 2 as Mortgage. S2 also got 1 right that 7b missed.
- **S1 passes but escalates most tickets.** It gets 2 fewer right than 7b (one Debt collection, one Consumer loan, both kept as Mortgage).
- Every 1.5b and 7b answer inside the cascades was the same as that model gave alone, so the differences come from the rule.

## 5. Confusion matrices

Rows = golden label, columns = answer.

### qwen2.5:7b

| | CredRep | Debt | Mortgage | Card | Bank | Loan | Transfer | Total |
|---|---|---|---|---|---|---|---|---|
| **CredRep** | **17** | 1 | 0 | 0 | 0 | 0 | 0 | 18 |
| **Debt** | 3 | **10** | 0 | 0 | 0 | 0 | 0 | 13 |
| **Mortgage** | 0 | 0 | **9** | 0 | 1 | 0 | 0 | 10 |
| **Card** | 2 | 0 | 0 | **6** | 1 | 0 | 0 | 9 |
| **Bank** | 1 | 0 | 0 | 2 | **14** | 0 | 2 | 19 |
| **Loan** | 0 | 0 | 0 | 0 | 0 | **8** | 1 | 9 |
| **Transfer** | 0 | 0 | 0 | 1 | 2 | 0 | **6** | 9 |

### phi3.5:3.8b

| | CredRep | Debt | Mortgage | Card | Bank | Loan | Transfer | Total |
|---|---|---|---|---|---|---|---|---|
| **CredRep** | **14** | 3 | 0 | 0 | 0 | 1 | 0 | 18 |
| **Debt** | 2 | **10** | 0 | 0 | 1 | 0 | 0 | 13 |
| **Mortgage** | 0 | 0 | **8** | 0 | 0 | 2 | 0 | 10 |
| **Card** | 1 | 0 | 0 | **6** | 2 | 0 | 0 | 9 |
| **Bank** | 0 | 0 | 0 | 3 | **15** | 0 | 1 | 19 |
| **Loan** | 0 | 0 | 0 | 0 | 1 | **8** | 0 | 9 |
| **Transfer** | 0 | 0 | 0 | 0 | 0 | 1 | **8** | 9 |

### qwen2.5:1.5b

| | CredRep | Debt | Mortgage | Card | Bank | Loan | Transfer | Total |
|---|---|---|---|---|---|---|---|---|
| **CredRep** | **17** | 0 | 0 | 1 | 0 | 0 | 0 | 18 |
| **Debt** | 5 | **4** | 1 | 2 | 0 | 1 | 0 | 13 |
| **Mortgage** | 3 | 0 | **4** | 2 | 0 | 1 | 0 | 10 |
| **Card** | 1 | 0 | 0 | **7** | 0 | 1 | 0 | 9 |
| **Bank** | 5 | 0 | 0 | 10 | **4** | 0 | 0 | 19 |
| **Loan** | 0 | 0 | 1 | 1 | 0 | **6** | 1 | 9 |
| **Transfer** | 2 | 0 | 0 | 2 | 0 | 1 | **4** | 9 |

### llama3.2:1b

| | CredRep | Debt | Mortgage | Card | Bank | Loan | Transfer | INVALID | Total |
|---|---|---|---|---|---|---|---|---|---|
| **CredRep** | **16** | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 18 |
| **Debt** | 9 | **3** | 0 | 0 | 0 | 0 | 0 | 1 | 13 |
| **Mortgage** | 8 | 2 | **0** | 0 | 0 | 0 | 0 | 0 | 10 |
| **Card** | 7 | 2 | 0 | **0** | 0 | 0 | 0 | 0 | 9 |
| **Bank** | 15 | 3 | 0 | 0 | **1** | 0 | 0 | 0 | 19 |
| **Loan** | 6 | 3 | 0 | 0 | 0 | **0** | 0 | 0 | 9 |
| **Transfer** | 5 | 4 | 0 | 0 | 0 | 0 | **0** | 0 | 9 |

### Cascade S1

| | CredRep | Debt | Mortgage | Card | Bank | Loan | Transfer | Total |
|---|---|---|---|---|---|---|---|---|
| **CredRep** | **17** | 1 | 0 | 0 | 0 | 0 | 0 | 18 |
| **Debt** | 3 | **9** | 1 | 0 | 0 | 0 | 0 | 13 |
| **Mortgage** | 0 | 0 | **9** | 0 | 1 | 0 | 0 | 10 |
| **Card** | 2 | 0 | 0 | **6** | 1 | 0 | 0 | 9 |
| **Bank** | 1 | 0 | 0 | 2 | **14** | 0 | 2 | 19 |
| **Loan** | 0 | 0 | 1 | 0 | 0 | **7** | 1 | 9 |
| **Transfer** | 0 | 0 | 0 | 1 | 2 | 0 | **6** | 9 |

### Cascade S2

| | CredRep | Debt | Mortgage | Card | Bank | Loan | Transfer | Total |
|---|---|---|---|---|---|---|---|---|
| **CredRep** | **18** | 0 | 0 | 0 | 0 | 0 | 0 | 18 |
| **Debt** | 5 | **7** | 1 | 0 | 0 | 0 | 0 | 13 |
| **Mortgage** | 3 | 0 | **6** | 0 | 1 | 0 | 0 | 10 |
| **Card** | 2 | 0 | 0 | **6** | 1 | 0 | 0 | 9 |
| **Bank** | 6 | 0 | 0 | 2 | **10** | 0 | 1 | 19 |
| **Loan** | 0 | 0 | 1 | 0 | 0 | **7** | 1 | 9 |
| **Transfer** | 2 | 0 | 0 | 0 | 2 | 0 | **5** | 9 |

## 6. Predictions vs results

Predictions: `a2/prediction-record.md`

| Prediction | Predicted | Result | Right? |
|---|---|---|---|
| qwen2.5:7b | 71/87, limit about 72% | 70/87, limit 70.5% | Close |
| phi3.5 | 69/87, fails Credit reporting or Card | 69/87, fails Credit reporting | Yes |
| qwen2.5:1.5b | 46/87, fails | 46/87, fails | Yes |
| llama3.2:1b | 20/87, fails | 20/87, fails | Yes |
| S1 accuracy | 72/87 (+/-3), passes | 68/87, passes | Score no, verdict yes |
| S1 escalated | 85-92% | 88.5% | Yes |
| S1 category losses | at most 1 ticket in any category | 1 in Debt, 1 in Loan | Yes |
| S2 accuracy | 66/87 (+/-3), passes | 59/87, fails | No |
| S2 escalated | 50-62% | 46.0% | No, lower |
| S2 most-hit categories | Loan, Transfer, then Card | CredRep +1, Debt -3, Mortgage -3, Card +0, Bank -4, Loan -1, Transfer -1 | No |
| Fastest that passes | S2 | S2 fails accuracy | No, whatever its speed |

The single-model predictions came from A1 results on the same tickets, so matching them is not surprising.

## 7. Run records and checks

| Configuration | Started (SGT) | Finished | Tickets | HTTP errors | INVALID | Log lines | Reconciliation | GPU memory |
|---|---|---|---|---|---|---|---|---|
| `single-7b` | 21:56 | 22:08 | 87 | 0 | 0 | 87 | clean | 0 |
| `single-phi` | 22:08 | 22:17 | 87 | 0 | 0 | 87 | clean | 0 |
| `single-1.5b` | 22:17 | 22:20 | 87 | 0 | 0 | 87 | clean | 0 |
| `single-llama` | 22:20 | 22:24 | 87 | 0 | 1 | 87 | clean | 0 |
| `cascade-S1` | 22:24 | 22:38 | 87 | 0 | 0 | 87 | clean | 0 |
| `cascade-S2` | 22:38 | 22:47 | 87 | 0 | 0 | 87 | clean | 0 |

- Ollama 0.35.1, CPU only. Models and prompt pinned as in A1.
- Rechecked for this file: each CSV has exactly the 87 test rows; labels match `golden_set/gold_labels.csv`; every answer, status and escalation flag matches its log line; no prompt was flagged as truncated; no model reloaded during either cascade run (all load times under 300 ms).
- Source files: `a2/results/accuracy_results/acc_<config>.csv`, `_summary.json`, `_requests.jsonl`.

## 8. Limitations

- **Small test set:** 87 tickets; three categories have 9. The confidence intervals of 7b, phi3.5 and S1 overlap heavily.
- **phi3.5 fails by one ticket:** Credit reporting 14/18, where 15/18 would have passed. Overall it is one ticket behind 7b.
- **Seen tickets:** all models ran on these tickets in A1.
- **Machine:** run on the accuracy laptop (`a2/env/environment_accuracy.md`). 