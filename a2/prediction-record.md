# Prediction record

**Team P1_1, 24 Nov 2026.**

Committed before any A2 measurement and not changed afterwards. The basis is:
- the tuning set (`a2/design/design_tables.md`);
- the brief's cascade latency formula, small + escalated × large;
- A1 latencies measured on the same test machine (`results-record.md`), used only to make these predictions, not as A2 results: p50 qwen2.5:1.5b 487 ms, phi3.5 1,431 ms, qwen2.5:7b 2,109 ms, and about 5.8 s per ticket for 7b in the stress test.

## 1. Fastest configuration that passes the accuracy limits
**Prediction: the cascade at setting S2.** Its median latency should be about **0.8× of qwen2.5:7b alone**, so about 20% faster.

**Reason:**
- phi3.5 alone would be faster still: 1,431 / 2,109 ≈ 0.68× of 7b.
- But on the tuning set phi3.5 already fails two category limits: Credit reporting and Credit card. We expect it to fail on the test set too.
- **If phi3.5 passes, it wins and the cascade loses.** To beat phi, the cascade would need to escalate fewer than 45% of tickets.

## 2. Accuracy on the test set (87 tickets)

| Configuration | Predicted accuracy | Passes the limits? |
|---|---|---|
| qwen2.5:7b (top model) | 71/87 (82%) → overall limit ≈ 72% | reference |
| phi3.5:3.8b | 69/87 (79%) | **no**: fails Credit reporting or Credit card |
| qwen2.5:1.5b | 46/87 (53%) | no |
| llama3.2:1b | 20/87 (23%) | no |
| Cascade S1 | 72/87 (83%) | yes |
| Cascade S2 | 66/87 (76%) | yes, but only just on Money transfer |

**Note:** the single-model figures follow from the A1 results, which already covered these tickets. The cascade figures come from the tuning set only.

## 3. The cascade at each setting

| | S1 (τ 75%) | S2 (τ 60%) |
|---|---|---|
| Tickets escalated to 7b | **85–92%** | **50–62%** |
| Accuracy | 72/87 (±3) | 66/87 (±3) |
| Median latency vs 7b alone | **≈ 1.1×** (no faster) | **≈ 0.8×** |
| Median latency | 4.5–8 s | 3–5.5 s |

- **Ratios use the brief's formula:** S1 = 0.23 + 0.88 × 1 ≈ 1.1×; S2 = 0.23 + 0.56 × 1 ≈ 0.8× (1.5b = 0.23× of 7b in A1).
- **Absolute times assume 7b's median is 4–7 s** on the A2 tickets. These tickets are longer than A1's short peak-test tickets, and A1's stress test averaged about 5.8 s per ticket.
- **Why we might be wrong:** the formula ignores queueing and the two cascade models sharing the CPU. The brief notes this too: "ignoring queueing and routing overhead". So the measured cascade latency may differ from these estimates.
- **Escalation under load** will be within about 8 points of the accuracy-test figure, because the speed-test tickets are different ones.

## 4. Categories expected to lose the most
**Consumer loan** and **Money transfer**, then **Credit card**. These are tickets that 1.5b mislabels as an accepted category, so its wrong answer is kept. S1 should lose at most 1 ticket in any category.

## 5. Speed-test set-up
- **S ≈ 4–6 s** (the 3 S tickets are around the median length; A1 averaged about 5.8 s per ticket on 7b).
- Rate ≈ 300–450 tickets/hour (one every 8–12 s), about 13–20× the client peak of 23/hour.
- 5–6-minute runs, about 30–40 tickets each.
- Median latency of 7b alone: **4–7 s**; phi3.5 alone (if speed-tested): 2.5–5 s.
- No errors in any run.
