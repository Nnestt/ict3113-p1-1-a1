# Speed Test Findings — A2 Step 4/5

**Team P1_1 · 25 Nov 2026 · owner: Lutfi (slide 5)**

Goal: find the **fastest triage configuration that still passes the accuracy limits**, measured on our own hardware under one fixed load.

---

## What we did

**Machines (unchanged from A1).** Load generator = Ryzen 5 7600 desktop running JMeter. SUT (system under test) = Intel laptop (~31 GB RAM) running the triage service in Docker, with Ollama on **CPU only**. The two are wired over LAN, load generator separate from the service as the brief requires.

**Setting the load (`measure_s.ps1`).** Restarted Ollama (clears its prompt cache), warmed up the top model, then sent **3 different typical tickets** to `qwen2.5:7b` one at a time and took the **middle time** as S (not the same ticket 3×, which Ollama would cache).

| Parameter | Value | How it's derived |
|---|---|---|
| **S** | **14.40 s** | middle of 9.91 / **14.40** / 14.96 s (rows 1181, 1342, 1322) |
| Arrival rate | 125 tickets/hour (one every 28.8 s) | round(3600 / 2S) — leaves 7b idle ~half the time, no queue |
| Run length | 15 min (~31 tickets) | ⌈S⌉, min 5 |
| HTTP timeout | 300 s | max(10S, 300) |
| End pause | 6 min | ⌈timeout/60⌉ + 1, so slow requests finish |

**The runs (`run_a2.ps1`).** Fixed workload of 150 non-golden tickets in the same order for every config. **3 interleaved runs each** for `single-7b`, `cascade-S1`, `cascade-S2` (run 1 of every config, then run 2, then run 3, so SUT drift is spread across configs). Each run: restart Ollama → 3 warm-up tickets (discarded) → for the cascade also warm the large model → confirm `ollama ps` lists every model at 100% CPU → JMeter open-loop at the rate above → let slow requests finish.

**Reliability note (honest record).** The first overnight attempt **failed**: the SUT laptop dropped off the network ~12 min into `single-7b` run 1 (requests 25–31 came back `HttpHostConnectException` / socket timeout, then the whole batch aborted). We cleared that run, fixed the laptop's sleep/lid settings, and re-ran. The reported session is the clean one: **all 9 runs completed with 0 errors**, stats deltas reconcile (31 sent = 31 completed = 31 stored per run), and both cascade models stayed resident the whole time.

**Metrics.** Latency from the JMeter `.jtl` (elapsed time of successful requests). p50 per run; mean + spread across the 3 runs; p95 pooled over ~93 requests (nearest-rank, as in A1). Escalation fraction from the service logs.

---

## The accuracy limits (the pass/fail floor)

Every config is judged against limits set by the **top model (`qwen2.5:7b`) on the test set** — the client's "don't get much worse than the current model" rule, fixed **before** measuring:

- **Overall limit = 7b's overall accuracy − 10 points.** 7b scored 80.5% (70/87), so the floor is **70.5%** (≥ 62/87 correct).
- **Per-category limit = 7b's accuracy in that category − 15 points.** A config must clear the floor in **every** category, not just overall.

| Category (test tickets) | 7b | Limit (−15) | Min correct |
|---|---|---|---|
| Credit reporting (18) | 94.4% | 79.4% | 15/18 |
| Debt collection (13) | 76.9% | 61.9% | 9/13 |
| Mortgage (10) | 90.0% | 75.0% | 8/10 |
| Credit card (9) | 66.7% | 51.7% | 5/9 |
| Bank account or service (19) | 73.7% | 58.7% | 12/19 |
| Consumer loan (9) | 88.9% | 73.9% | 7/9 |
| Money transfer or service (9) | 66.7% | 51.7% | 5/9 |

A config **passes only if it clears the overall floor AND every category floor.** On the test set: **single-7b** is the reference, **cascade-S1 passes**, **cascade-S2 fails** (below the floor on Debt collection, Mortgage, and Bank account). phi3.5, 1.5b and llama also failed accuracy, so they were not speed-tested.

> **⚠️ Don't confuse the accuracy limits with S1/S2.** The limits (−10 overall, −15 per category) are the **floor every config must clear**. S1 and S2 are the **cascade's own trust settings** (the τ knob, below) — *not* accuracy thresholds. Both come from the design work, but they are different things.

---

## Results

| Config | mean p50 | vs 7b | pooled p95 | escalation | accuracy verdict |
|---|---|---|---|---|---|
| **cascade-S2** | **4.65 s** | **0.41×** | 25.1 s | 41.9% | ❌ **FAILS** (Debt, Mortgage, Bank below limit) |
| **single-7b** (top model) | 11.30 s | 1.00× | 27.8 s | — | ✅ reference (sets the limits) |
| **cascade-S1** | 13.79 s | 1.22× | 35.6 s | 90.3% | ✅ **PASSES** both limits |

Per-run p50s (shows spread): single-7b 6.72 / 14.47 / 12.72 s · S1 8.12 / 19.14 / 14.12 s · S2 3.90 / 5.36 / 4.70 s.

---

## Summary — which was fastest, and what we recommend

- **Fastest overall: cascade-S2 (4.65 s, less than half of 7b).** But S2 **fails the accuracy limits**, so it cannot be recommended. Its speed comes from answering ~58% of tickets with the tiny model alone — which is exactly why its accuracy drops.
- **Among the configs that pass accuracy** (single-7b and cascade-S1), **single-7b is faster**: 11.30 s vs S1's 13.79 s.
- **The cascade did not beat the top model.** At the only accurate setting (S1) it escalates ~90% of tickets, so almost every ticket pays the small-model cost **on top of** 7b — making it 1.22× slower than just running 7b.

### ➡️ Recommendation: **single-7b (the top model alone).**
The cascade is faster only at a setting (S2) that sacrifices too much accuracy. This is an outcome the brief explicitly allows: the recommended config is the top model, and we report what the cascade cost us and why.

**Prediction vs measurement (for the analysis marks).**
- S1 predicted ≈ 1.1× of 7b (no faster) → **measured 1.22×**. Right direction, slightly worse.
- S2 predicted to be *the fastest passing config* at ≈ 0.8× → it **was** the fastest (0.41×, even faster than predicted) but it **did not pass accuracy**, so the "fastest *passing*" prediction was wrong. Useful miss: we underestimated how much trusting the small model on Credit reporting / Debt would cost.

**Limitations.** single-7b and S1 show wide run-to-run spread (7b: 6.7 → 14.5 s), most likely the laptop's thermal state drifting over the ~3.5 h session; S2 is tight (1.5 s). Our test rate (125/hr) is well above the client's peak (~23/hr), so the result also shows the system handles the client's load.

---

## What are S1 and S2?

Both are the **same cascade**: the small model `qwen2.5:1.5b` classifies a ticket first; if we don't trust its answer, we escalate to the large model `qwen2.5:7b`, whose answer is final. The rule is **category-based** — we keep the small model's label only for categories it gets right reliably on the tuning set.

The one knob is **τ (tau)**: keep the small model's predicted label if that label's tuning-set precision is ≥ τ (over at least 4 predictions). The two settings differ **only in τ**:

| | **S1** | **S2** |
|---|---|---|
| τ (trust threshold) | **75%** | **60%** |
| Accept list (labels we trust from 1.5b) | Bank account or service, Mortgage | Bank account or service, Credit reporting, Debt collection, Mortgage |
| Measured escalation | **90.3%** (cautious — almost everything still goes to 7b) | **41.9%** (bold — keeps ~58% from the small model) |
| Effect | Accurate but **slower than 7b** | **Fast** but fails accuracy |

S1 is the cautious end (trust the small model on only its 2 strongest categories); S2 is the fast end (trust it on 4). They were chosen far apart on purpose so the speed/accuracy trade-off is visible.

---

## Glossary — every parameter and term

| Term | What it means |
|---|---|
| **SUT** | System Under Test — the Intel laptop running the triage service: **ASUS Zenbook 14 (UX3405MA), Intel Core Ultra 7 155H (16 cores / 22 threads), 31.37 GB RAM, Windows 11 Home**, Ollama 0.35.1 + Docker Engine 29.8.2, **CPU only** (all GPU back-ends disabled), at 192.168.68.69 on the wired LAN. |
| **Load generator** | The Ryzen 5 7600 desktop running JMeter, sending tickets to the SUT over LAN. Separate from the service, as the brief requires. |
| **S** | The "typical" time for the **top model** to answer one ticket: the **middle** of 3 timings on 3 different tickets = **14.40 s**. Everything below is derived from S. |
| **Arrival rate** | How often we send a ticket: one every **2·S** = 28.8 s = **125/hour**. Spacing at 2·S keeps the model idle ~half the time, so no queue builds and the latency reflects the config, not the queue. |
| **Run length** | How long each run sends tickets: **⌈S⌉ min, min 5** = **15 min** (~31 tickets). |
| **HTTP timeout** | How long JMeter waits for one reply before giving up: **max(10·S, 300 s)** = **300 s**. |
| **End pause** | Idle time after sending stops, so slow replies can finish: **⌈timeout/60⌉ + 1** = **6 min**. Without it JMeter would cut off the slowest requests — the ones we most need. |
| **Warm-up** | 3 fixed tickets before each run (timings discarded) so the first real ticket isn't paying the model's cold-start load time. |
| **Workload** | The fixed 150 non-golden tickets, same order for every config, so configs are compared on identical inputs. |
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

## 🐒 Monkey explanation

Picture the service as a monkey sorting letters into 7 boxes.

- **Big Monkey (7b)** is smart but slow — reads every letter carefully, ~11 seconds each.
- **Small Monkey (1.5b)** is fast but dumb — glances and guesses in ~1 second, often wrong.

**The cascade:** Small Monkey looks first and shouts a box. If it's a box he's usually right about, we keep his answer. If not, we hand the letter to Big Monkey.

- **S1 = careful.** We only trust Small Monkey on **2 boxes** he's genuinely good at. So he ends up passing **~90%** of letters to Big Monkey anyway — meaning most letters get looked at **twice**. Double work → **slower than just using Big Monkey**. 🐢
- **S2 = greedy.** We trust Small Monkey on **4 boxes**. Now he keeps **~58%** of letters himself → **super fast, less than half the time**. ⚡ But he's wrong too often on the extra boxes → **he sorts too many letters into the wrong box** → fails the accuracy test. ❌

**Moral:** Small Monkey is only worth asking when he actually knows the answer. Being careful (S1) makes him almost useless; being greedy (S2) makes him fast but sloppy. So for now, we just let **Big Monkey** do the whole job. 🧠
