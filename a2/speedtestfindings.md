# Speed Test Findings — A2 Step 4/5

**Team P1_1 · 25 Nov 2026 · owner: Lutfi (slide 5)**

## TL;DR

We speed-tested the three configurations still in contention under one fixed load (**125 tickets/hour, 15-min runs, 3 runs each**). **The cascade did not beat the top model — so our recommendation is `single-7b`.** The fastest overall (cascade-S2) is disqualified because it fails the accuracy limits.

**Results at a glance** (median latency; lower = faster):

| Configuration | Median (p50) | vs 7b | Pooled p95 | Overall accuracy | Verdict |
|---|---|---|---|---|---|
| cascade-S2 | **4.65 s** | 0.41× | 25.1 s | 59/87 (67.8%) | ❌ **FAIL** — fastest overall, but disqualified on accuracy |
| **single-7b** ⭐ | 11.30 s | 1.00× | 27.8 s | 70/87 (80.5%) | ✅ **Recommended** — reference model, fastest that passes |
| cascade-S1 | 13.79 s | 1.22× | 35.6 s | 68/87 (78.2%) | ✅ **PASS** — but slower than 7b (escalates ~90%) |

*Full method, per-run numbers, escalation fractions and definitions below.*

---

# 1. Background & definitions

## 1.1 Which configurations we speed-tested (and why not the rest)

All six configurations went through the **accuracy test** first. The brief's rule for the **speed test** is narrower: speed-test only the configurations that **pass both accuracy limits**, plus **the cascade in all cases** (both settings, even if one fails accuracy). *Single models that fail accuracy do not need a speed test.*

| Configuration | Overall accuracy | Verdict | Speed-tested? | Why |
|---|---|---|---|---|
| `single-7b` (top model) | 70/87 (80.5%) | reference | ✅ yes | Required baseline — the latency we're trying to beat. |
| `cascade-S1` | 68/87 (78.2%) | **PASS** | ✅ yes | Passes accuracy; and the cascade is tested in all cases. |
| `cascade-S2` | 59/87 (67.8%) | FAIL | ✅ yes | Cascade tested in all cases — reported as "fails accuracy". |
| `single-phi` (phi3.5) | 69/87 (79.3%) | FAIL | ❌ no | Clears the *overall* floor but fails a **category** limit (Credit reporting 77.8% < 79.4%), so it fails — and is exempt from the speed test. |
| `single-1.5b` (qwen2.5:1.5b) | 46/87 (52.9%) | FAIL | ❌ no | Failed accuracy badly — not in contention. |
| `single-llama` (llama3.2:1b) | 20/87 (23.0%) | FAIL | ❌ no | Failed accuracy badly — not in contention. |

> **The phi subtlety (worth a slide note):** phi's **overall** accuracy (79.3%) is actually *higher* than S1's (78.2%), yet phi **fails** and S1 **passes** — because passing requires clearing **every category floor**, not just the overall one. phi misses on Credit reporting (14/18 = 77.8% < the 79.4% floor); S1 clears all seven. Per the brief, single models that fail accuracy are exempt from the speed test, so phi, 1.5b and llama were not run.

## 1.2 What S1 and S2 are

Both are the **same cascade**: the small model `qwen2.5:1.5b` classifies a ticket first; if we don't trust its answer, we escalate to the large model `qwen2.5:7b`, whose answer is final. The rule is **category-based** — we keep the small model's label only for categories it gets right reliably on the tuning set.

The one knob is **τ (tau)**: keep the small model's predicted label if that label's tuning-set precision is ≥ τ (over at least 4 predictions). The two settings differ **only in τ**:

| | **S1** | **S2** |
|---|---|---|
| τ (trust threshold) | **75%** | **60%** |
| Accept list (labels trusted from 1.5b) | Bank account or service, Mortgage | Bank account or service, Credit reporting, Debt collection, Mortgage |
| Measured escalation (workload) | **90.3%** — cautious, almost everything still goes to 7b | **41.9%** — bold, keeps ~58% from the small model |
| Net effect | Accurate, but **slower than 7b** | **Fast**, but fails accuracy |

S1 is the cautious end (trust the small model on only its 2 strongest categories); S2 is the bold end (trust it on 4). They were chosen far apart so the speed/accuracy trade-off is visible.

## 1.3 The accuracy limits (the pass/fail floor)

These are **not** S1/S2 — they are the floor **every** configuration must clear, set by the **top model (`qwen2.5:7b`) on the test set** and fixed before measuring:

- **Overall limit = 7b's overall accuracy − 10 points** = 80.5% − 10 = **70.5%** (≥ 62/87 correct).
- **Per-category limit = 7b's accuracy in that category − 15 points** — must be cleared in **every** category.

| Category (test tickets) | 7b | Limit (−15) | Min correct |
|---|---|---|---|
| Credit reporting (18) | 94.4% | 79.4% | 15/18 |
| Debt collection (13) | 76.9% | 61.9% | 9/13 |
| Mortgage (10) | 90.0% | 75.0% | 8/10 |
| Credit card (9) | 66.7% | 51.7% | 5/9 |
| Bank account or service (19) | 73.7% | 58.7% | 12/19 |
| Consumer loan (9) | 88.9% | 73.9% | 7/9 |
| Money transfer or service (9) | 66.7% | 51.7% | 5/9 |

A configuration passes only if it clears the overall floor **and** every category floor. On the test set: `single-7b` is the reference, **`cascade-S1` passes**, **`cascade-S2` fails** (below the floor on Debt collection, Mortgage, and Bank account).

> **⚠️ Don't confuse the accuracy limits with S1/S2.** The limits (−10 overall, −15 per category) are the **floor every config must clear**. S1 and S2 are the **cascade's own trust settings** (the τ knob in 1.2). "Best model − 10" is the *overall accuracy limit*, not a cascade setting.

## 1.4 Glossary — every parameter and term

| Term | What it means |
|---|---|
| **SUT** | System Under Test — the Intel laptop running the triage service: **ASUS Zenbook 14 (UX3405MA), Intel Core Ultra 7 155H (16 cores / 22 threads), 31.37 GB RAM, Windows 11 Home**, Ollama 0.35.1 + Docker Engine 29.8.2, **CPU only** (all GPU back-ends disabled), at 192.168.68.69 on the wired LAN. |
| **Load generator** | The **Ryzen 5 7600** desktop running JMeter 5.6.3, sending tickets to the SUT over LAN. Separate physical machine from the service, as the brief requires. |
| **S** | The "typical" time for the **top model** to answer one ticket: the **middle** of 3 timings on 3 different tickets = **14.40 s**. Everything below is derived from S. |
| **Arrival rate** | How often a ticket is sent: one every **2·S** = 28.8 s = **125/hour**. Spacing at 2·S keeps the model idle ~half the time, so no queue builds and the latency reflects the config, not the queue. |
| **Run length** | How long each run sends tickets: **⌈S⌉ min, min 5** = **15 min** (~31 tickets). |
| **HTTP timeout** | How long JMeter waits for one reply before giving up: **max(10·S, 300 s)** = **300 s**. |
| **End pause** | Idle time after sending stops, so slow replies can finish: **⌈timeout/60⌉ + 1** = **6 min**. Without it JMeter would cut off the slowest requests — the ones we most need. |
| **Warm-up** | 3 fixed tickets before each run (timings discarded) so the first real ticket isn't paying the model's cold-start load time. |
| **Workload** | The fixed 150 non-golden tickets, same order for every config, so configs are compared on identical inputs (~31 used per 15-min run). |
| **p50 (median latency)** | The middle request time — half the tickets faster, half slower. Our main speed number. |
| **p95** | The time 95% of requests beat (only 5% slower) — the slow tail. Pooled over all 3 runs (~93 requests), since one run is too few to measure it. |
| **Spread** | Gap between the fastest and slowest run's p50 — how stable the result is across runs. |
| **Cascade** | The two-model setup: small model (`qwen2.5:1.5b`) answers first; escalate to the large model (`qwen2.5:7b`) when the small one isn't trusted. |
| **Escalation fraction** | Share of tickets passed up to the large model. High = small model rarely trusted. |
| **τ (tau)** | The cascade's trust threshold: keep the small model's label only if that label is right ≥ τ of the time on the tuning set. **S1 = 75%, S2 = 60%.** |
| **Accept list** | The categories whose labels we trust from the small model (tuning precision ≥ τ). |
| **Overall accuracy limit** | Pass/fail floor = top model's overall accuracy **− 10 points** = 70.5%. |
| **Per-category limit** | Pass/fail floor per category = top model's category accuracy **− 15 points**. Must clear every category. |
| **Top model / reference** | `qwen2.5:7b`, our most accurate A1 model. Sets the accuracy limits and is the latency we try to beat. |

---

# 2. Method — what we did

## 2.1 Machines

Load generator and service on **separate physical machines**, wired over LAN (see the SUT and Load generator rows in the glossary for full specs). Ollama runs **CPU only** on the SUT; before every run the script confirms `ollama ps` shows each model at 100% CPU and aborts otherwise.

**Cascade memory constraint.** A cascade only counts if both models stay resident at once. We checked first: `qwen2.5:1.5b` + `qwen2.5:7b` both load together with ~5.4 GB RAM to spare, both at 100% CPU — so the cascade runs measure routing, not model reloading.

## 2.2 Setting the load — measuring S (`measure_s.ps1`)

Restarted Ollama (clears its prompt cache), warmed up the top model, then sent **3 different typical tickets** to `qwen2.5:7b` one at a time and took the **middle** time as S (not the same ticket 3×, which Ollama would cache into a false speed-up).

| Parameter | Value | Derivation |
|---|---|---|
| **S** | **14.40 s** | middle of 9.91 / **14.40** / 14.96 s (rows 1181, 1342, 1322) |
| Arrival rate | 125 tickets/hour (one every 28.8 s) | round(3600 / 2S) |
| Run length | 15 min (~31 tickets) | ⌈S⌉, min 5 |
| HTTP timeout | 300 s | max(10S, 300) |
| End pause | 6 min | ⌈timeout/60⌉ + 1 |

## 2.3 The runs (`run_a2.ps1`)

**3 interleaved runs each** for `single-7b`, `cascade-S1`, `cascade-S2` — run 1 of every config, then run 2, then run 3, so any slow drift on the SUT is spread evenly across configs. Every run used the same fixed 150-ticket workload in the same order. Each run: restart Ollama → 3 warm-up tickets (discarded) → for the cascade also warm the large model directly → confirm both models resident at 100% CPU → JMeter open-loop at 125/hour for 15 min → 6-min pause so slow requests finish.

## 2.4 Reliability note (honest record)

The **first overnight attempt failed**: the SUT laptop dropped off the network ~12 min into `single-7b` run 1 (requests 25–31 came back `HttpHostConnectException` / socket timeout, then the whole batch aborted). We cleared that run, fixed the laptop's sleep/lid-close settings, and re-ran. The reported session is the clean one: **all 9 runs completed with 0 errors**, stats deltas reconcile (31 sent = 31 completed = 31 stored per run), and both cascade models stayed resident throughout.

---

# 3. Results

Latency = elapsed time of successful requests from the JMeter `.jtl`. p50 per run → mean across the 3 runs; p95 pooled over ~93 requests (nearest-rank, as in A1).

| Config | mean p50 | vs 7b | pooled p95 | escalation | accuracy verdict |
|---|---|---|---|---|---|
| **cascade-S2** | **4.65 s** | **0.41×** | 25.1 s | 41.9% | ❌ **FAILS** (Debt, Mortgage, Bank below floor) |
| **single-7b** (top model) | 11.30 s | 1.00× | 27.8 s | — | ✅ reference (sets the limits) |
| **cascade-S1** | 13.79 s | 1.22× | 35.6 s | 90.3% | ✅ **PASSES** both limits |

**Per-run p50 (the only metric that varies run to run):**

| Config | run 1 | run 2 | run 3 | mean | spread |
|---|---|---|---|---|---|
| single-7b | 6.72 s | 14.47 s | 12.72 s | **11.30 s** | 7.75 s |
| cascade-S1 | 8.12 s | 19.14 s | 14.12 s | **13.79 s** | 11.02 s |
| cascade-S2 | 3.90 s | 5.36 s | 4.70 s | **4.65 s** | 1.46 s |

**Per-run counts — identical across all 9 runs:** 31 sent = 31 completed, **0 errored, 0 unfinished (0% error rate)**, achieved throughput **0.036 req/s** = the 125/hour arrival rate, confirming the service kept up and no queue formed.

**Escalation under load vs the accuracy test:** S1 90.3% (vs 88.5%), S2 41.9% (vs 46.0%) — close; the small gap is expected because the speed-test tickets differ from the accuracy-test tickets.

**Raw evidence (every figure traces to a file):** JMeter `.jtl` in `load_test/results/`, service logs in `load_test/logs/*_requests.jsonl`, matched by `X-Run-ID`. Model tags and pinned digests: `a2/env/environment_accuracy.md`.

---

# 4. Conclusion

## 4.1 Which was fastest, and what we recommend

- **Fastest overall: `cascade-S2` (4.65 s, less than half of 7b)** — but it **fails the accuracy limits**, so it cannot be recommended. Its speed comes from answering ~58% of tickets with the tiny model alone, which is exactly why its accuracy drops.
- **Among the configurations that pass accuracy** (`single-7b` and `cascade-S1`), **`single-7b` is faster**: 11.30 s vs S1's 13.79 s.
- **The cascade did not beat the top model.** At the only accurate setting (S1) it escalates ~90% of tickets, so almost every ticket pays the small-model cost **on top of** 7b — making it 1.22× slower than just running 7b.

### ➡️ Recommendation: **`single-7b` (the top model alone).**
The cascade is faster only at a setting (S2) that sacrifices too much accuracy. This is an outcome the brief explicitly allows: we recommend the top model and report what the cascade cost and why.

## 4.2 Prediction vs measurement (analysis marks)

- **S1** predicted ≈ 1.1× of 7b (no faster) → **measured 1.22×**. Right direction, slightly worse.
- **S2** predicted to be *the fastest passing config* at ≈ 0.8× → it **was** the fastest (0.41×, even faster than predicted) but it **did not pass accuracy**, so the "fastest *passing*" prediction was wrong. Useful miss: we underestimated how much trusting the small model on Credit reporting / Debt would cost in accuracy.

## 4.3 Limitations

- `single-7b` and S1 show wide run-to-run spread (7b: 6.7 → 14.5 s), most likely the laptop's thermal state drifting over the ~3.5 h session; S2 is tight (1.5 s spread). The spread is part of the result.
- Our test rate (125/hour) is well above the client's peak (~23/hour), so the result also shows the system handles the client's load.

---

# 5. 🐒 Monkey explanation

Picture the service as a monkey sorting letters into 7 boxes.

- **Big Monkey (7b)** is smart but slow — reads every letter carefully, ~11 seconds each.
- **Small Monkey (1.5b)** is fast but dumb — glances and guesses in ~1 second, often wrong.

**The cascade:** Small Monkey looks first and shouts a box. If it's a box he's usually right about, we keep his answer. If not, we hand the letter to Big Monkey.

- **S1 = careful.** We only trust Small Monkey on **2 boxes** he's genuinely good at. So he ends up passing **~90%** of letters to Big Monkey anyway — most letters get looked at **twice**. Double work → **slower than just using Big Monkey**. 🐢
- **S2 = greedy.** We trust Small Monkey on **4 boxes**. Now he keeps **~58%** of letters himself → **super fast, less than half the time**. ⚡ But he's wrong too often on the extra boxes → **too many letters in the wrong box** → fails the accuracy test. ❌

And **phi** (phi3.5) was a third monkey we auditioned for the smart job — but he kept miscounting one whole box (Credit reporting), so he failed the exam and never got to race. 🙈

**Moral:** Small Monkey is only worth asking when he actually knows the answer. Careful (S1) makes him almost useless; greedy (S2) makes him fast but sloppy. So for now, we just let **Big Monkey** do the whole job. 🧠
