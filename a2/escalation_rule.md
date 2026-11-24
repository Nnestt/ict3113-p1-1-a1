# Escalation rule

```
ticket ──► qwen2.5:1.5b ──► is its label in the accept list? ── yes ──► answer = 1.5b's label
                                     │
                                     no (or invalid output, or the call failed)
                                     ▼
                               qwen2.5:7b ──► answer = 7b's label
```

## Rule
For each category, look at how often **qwen2.5:1.5b's prediction** of that category was correct on the **tuning set**. If it was correct at least **τ** of the time (over at least 4 predictions), that category goes on the **accept list**.

When a ticket arrives:
1. qwen2.5:1.5b classifies it.
2. If its label is on the accept list, return that label.
3. Otherwise, including an invalid output or a failed call, send the ticket to **qwen2.5:7b**, and return 7b's label.

The two settings differ only in τ:

| Setting | τ | Accept list |
|---|---|---|
| **S1** | 75% | Bank account or service, Mortgage |
| **S2** | 60% | Bank account or service, Credit reporting, Debt collection, Mortgage |

**Implementation details:**
- Same prompt and settings for both models as in A1.
- If 7b fails, the request returns an error (502/504), as in A1.
- Both models stay loaded at the same time (`a2/env/memory_check.txt`).
- Implemented in `service/cascade.py`; the accept lists are in `service/cascade_config.json`.

## Why this rule
- **1.5b is far more reliable on some labels than others.** On the tuning set, its "Bank account" predictions were 4/4 correct, but its "Credit card" predictions were only 7/27. So its predicted label tells us when to trust it, at no extra cost.
- **The other methods don't fit our data:**
  - Ticket length doesn't predict its errors.
  - The only other small model (llama3.2:1b) is too inaccurate for an agreement check (20%).
  - Asking for confidence would need an extra model call.
- **Why 7b and not phi3.5 as the large model:** phi3.5 already fails two category limits on the tuning set, and no rule could fix that.
- **Why these two settings:** they are far apart, so the trade-off is clear.

| Setting | Escalated | Accuracy | Est. latency vs 7b alone |
|---|---|---|---|
| S1 | 88% | 65/88 (more accurate than 7b alone, 64/88) | slower, ~1.1× |
| S2 | 56% | 59/88 | faster, ~0.8× |

Escalation and accuracy are tuning-set results. Latency is estimated with the brief's formula (small + escalated × large), using the A1 median latencies measured on the same test machine: 1.5b 487 ms, 7b 2,109 ms.

**How often a wrong answer slips through:** S1 kept 11 answers from 1.5b, of which 1 was wrong. S2 kept 39, of which 10 were wrong.

Full evidence: `a2/design/design_tables.md`, from `python a2/design_rule.py`, tuning set only.
