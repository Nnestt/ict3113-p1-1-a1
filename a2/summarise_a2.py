"""Recompute every A2 figure (slides 4-7) from the committed raw files.

Usage (from the repo root):  python a2/summarise_a2.py

Inputs (read only, all committed):
  golden_set/gold_labels.csv, a2/split/test_rows.csv, a2/speed_params.json
  a2/results/accuracy_results/acc_<config>_requests.jsonl   (accuracy: service log)
  load_test/results/a2_<config>_run<N>.jtl                    (speed: JMeter)
  load_test/results/a2_<config>_run<N>_stats_{pre,post}.json  (speed: GET /stats)
  load_test/logs/a2_<config>_run<N>_requests.jsonl            (speed: escalation)
Output: a2/results/a2_summary.md (overwritten; `git diff` shows any change).
Standard library only.
"""
import csv
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "a2" / "results" / "a2_summary.md"

CATEGORIES = ["Credit reporting", "Debt collection", "Mortgage", "Credit card",
              "Bank account or service", "Consumer loan", "Money transfer or service"]
SHORT = {"Credit reporting": "CredRep", "Debt collection": "Debt", "Mortgage": "Mortgage",
         "Credit card": "Card", "Bank account or service": "Bank",
         "Consumer loan": "Loan", "Money transfer or service": "Transfer"}
ACC_CONFIGS = ["single-7b", "single-phi", "single-1.5b", "single-llama", "cascade-S1", "cascade-S2"]
SPEED_CONFIGS = ["single-7b", "cascade-S1", "cascade-S2"]
REFERENCE = "single-7b"
RUNS = (1, 2, 3)


def pct(n, d):
    return f"{100 * n / d:.1f}%"


def count(n, d):
    return f"{n}/{d} ({pct(n, d)})"


def nearest_rank(values, p):
    v = sorted(values)
    return v[max(0, math.ceil(p / 100 * len(v)) - 1)]


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def row_of(request_id):
    return int(request_id.rsplit("_r", 1)[1])


# ---------------------------------------------------------------- accuracy
def accuracy():
    gold = {int(r["row"]): r["gold_label"]
            for r in csv.DictReader(open(ROOT / "golden_set" / "gold_labels.csv", encoding="utf-8"))}
    test = sorted(int(r["row"]) for r in csv.DictReader(open(ROOT / "a2" / "split" / "test_rows.csv", encoding="utf-8")))
    totals = {c: sum(gold[r] == c for r in test) for c in CATEGORIES}

    res = {}
    for cfg in ACC_CONFIGS:
        run_id = f"acc_{cfg}"
        log = ROOT / "a2" / "results" / "accuracy_results" / f"{run_id}_requests.jsonl"
        lines = [x for x in read_jsonl(log)
                 if x.get("run_id") == run_id and x.get("method") == "POST" and x.get("route") == "/tickets"]
        by_row = {row_of(x["request_id"]): x for x in lines}
        missing = set(test) - set(by_row)
        if missing:
            raise SystemExit(f"{log}: no log line for test rows {sorted(missing)}")
        right = {r: by_row[r].get("status") == 200 and by_row[r].get("category") == gold[r] for r in test}
        esc = [r for r in test if by_row[r].get("escalated")]
        kept = [r for r in test if not by_row[r].get("escalated")]
        res[cfg] = {
            "correct": sum(right.values()),
            "per_cat": {c: sum(right[r] for r in test if gold[r] == c) for c in CATEGORIES},
            "esc": (sum(right[r] for r in esc), len(esc)),
            "kept": (sum(right[r] for r in kept), len(kept)),
            "lines": len(lines),
        }

    n = len(test)
    ref = res[REFERENCE]
    ref_acc = 100 * ref["correct"] / n
    overall_floor = ref_acc - 10
    cat_floor = {c: 100 * ref["per_cat"][c] / totals[c] - 15 for c in CATEGORIES}

    def verdict(cfg):
        r = res[cfg]
        over = 100 * r["correct"] / n >= overall_floor - 1e-9
        fails = [SHORT[c] for c in CATEGORIES if 100 * r["per_cat"][c] / totals[c] < cat_floor[c] - 1e-9]
        return over, fails

    md = ["## Accuracy (test set)", "",
          f"Source: `a2/results/accuracy_results/acc_<config>_requests.jsonl` (service log, `POST /tickets` lines "
          f"for `run_id` acc_<config>), scored against `golden_set/gold_labels.csv` on the {n} rows of "
          "`a2/split/test_rows.csv`. A non-200 or INVALID answer counts as wrong.", "",
          "### Limits (from the reference on the test set)", "",
          f"- Overall: {pct(ref['correct'], n)} - 10 = **{overall_floor:.1f}%** "
          f"(at least {math.ceil(overall_floor / 100 * n - 1e-9)}/{n})", "",
          "| Category | Tickets | Reference | Limit (-15) | Minimum correct | One ticket |", "|---|---|---|---|---|---|"]
    for c in CATEGORIES:
        t = totals[c]
        small = " (fewer than 10 tickets)" if t < 10 else ""
        md.append(f"| {c}{small} | {t} | {count(ref['per_cat'][c], t)} | {cat_floor[c]:.1f}% | "
                  f"{math.ceil(cat_floor[c] / 100 * t - 1e-9)}/{t} | {100 / t:.1f} pts |")

    md += ["", "### Overall and verdict", "",
           "| Configuration | Correct | Overall limit | Category limits | Verdict |", "|---|---|---|---|---|"]
    for cfg in ACC_CONFIGS:
        over, fails = verdict(cfg)
        if cfg == REFERENCE:
            v = ("reference", "reference", "reference")
        else:
            v = ("PASS" if over else "FAIL", "PASS" if not fails else "FAIL: " + ", ".join(fails),
                 "**PASS**" if over and not fails else "FAIL")
        md.append(f"| {cfg} | {count(res[cfg]['correct'], n)} | {v[0]} | {v[1]} | {v[2]} |")

    md += ["", "### Per category (right/total; * = below the limit)", "",
           "| Category | " + " | ".join(ACC_CONFIGS) + " |", "|---|" + "---|" * len(ACC_CONFIGS)]
    for c in CATEGORIES:
        cells = []
        for cfg in ACC_CONFIGS:
            k = res[cfg]["per_cat"][c]
            low = cfg != REFERENCE and 100 * k / totals[c] < cat_floor[c] - 1e-9
            cells.append(count(k, totals[c]) + (" *" if low else ""))
        md.append(f"| {c} | " + " | ".join(cells) + " |")

    md += ["", "### Cascade escalation (accuracy test)", "",
           "| Configuration | Escalated | Escalated accuracy (large model answered) | Non-escalated accuracy (small model answered) |",
           "|---|---|---|---|"]
    for cfg in ACC_CONFIGS:
        if cfg.startswith("cascade"):
            r = res[cfg]
            md.append(f"| {cfg} | {count(r['esc'][1], n)} | {count(*r['esc'])} | {count(*r['kept'])} |")
    return md, {cfg: res[cfg]["correct"] / n for cfg in ACC_CONFIGS}, verdict


# ---------------------------------------------------------------- speed
def speed():
    params = json.load(open(ROOT / "a2" / "speed_params.json", encoding="utf-8"))
    load_s = params["load_min"] * 60
    md = ["## Speed test", "",
          f"Set-up (`a2/speed_params.json`): S = {params['S_s']:.3f} s, the middle of "
          f"{', '.join(f'{t / 1000:.3f}' for t in sorted(params['s_timings_ms']))} s from rows "
          f"{', '.join(map(str, params['s_rows']))}; rate {params['rate_per_hour']}/hour; load "
          f"{params['load_min']} min; timeout {params['timeout_ms'] // 1000} s; pause {params['pause_min']} min.", "",
          "Sources: latency, sent and errors from `load_test/results/a2_<config>_run<N>.jtl` (successful samples' "
          "`elapsed`); completed = `GET /stats` total after minus before (`_stats_pre/_post.json`); "
          "escalation from `load_test/logs/a2_<config>_run<N>_requests.jsonl` (`POST /tickets`, status 200, "
          "matching `run_id`; warm-up lines excluded). p95 is nearest-rank over the three runs pooled. "
          f"Throughput = completed / {load_s} s load period.", "",
          "### Per run", "",
          "| Run | Sent | Completed | Errored | Unfinished | p50 | Throughput | Error rate | Escalated |",
          "|---|---|---|---|---|---|---|---|---|"]
    summary = {}
    for cfg in SPEED_CONFIGS:
        p50s, pooled = [], []
        for n in RUNS:
            run_id = f"a2_{cfg}_run{n}"
            rows = list(csv.DictReader(open(ROOT / "load_test" / "results" / f"{run_id}.jtl", encoding="utf-8")))
            ok = [int(r["elapsed"]) for r in rows if r["success"] == "true"]
            errored = len(rows) - len(ok)
            pre = json.load(open(ROOT / "load_test" / "results" / f"{run_id}_stats_pre.json", encoding="utf-8"))
            post = json.load(open(ROOT / "load_test" / "results" / f"{run_id}_stats_post.json", encoding="utf-8"))
            completed = post["total"] - pre["total"]
            unfinished = len(rows) - completed - errored
            log = [x for x in read_jsonl(ROOT / "load_test" / "logs" / f"{run_id}_requests.jsonl")
                   if x.get("run_id") == run_id and x.get("method") == "POST" and x.get("status") == 200]
            esc = sum(bool(x.get("escalated")) for x in log)
            p50 = statistics.median(ok)
            p50s.append(p50)
            pooled += ok
            thr = completed / load_s
            esc_txt = count(esc, len(log)) if cfg.startswith("cascade") else "-"
            md.append(f"| {run_id} | {len(rows)} | {completed} | {errored} | {unfinished} | {p50 / 1000:.3f} s | "
                      f"{thr:.4f} req/s ({thr * 3600:.0f}/hour) | {pct(errored, len(rows))} | {esc_txt} |")
        summary[cfg] = {"mean": statistics.mean(p50s), "spread": max(p50s) - min(p50s),
                        "p95": nearest_rank(pooled, 95), "n": len(pooled)}

    ref = summary[REFERENCE]["mean"]
    md += ["", "### Per configuration", "",
           "| Configuration | Mean p50 | Spread (max - min run p50) | Pooled p95 (n) | vs reference mean p50 |",
           "|---|---|---|---|---|"]
    for cfg in SPEED_CONFIGS:
        s = summary[cfg]
        if cfg == REFERENCE:
            rel = "reference"
        else:
            d = s["mean"] - ref
            rel = f"{abs(d) / 1000:.3f} s ({100 * abs(d) / ref:.1f}%) {'slower' if d > 0 else 'faster'}; {s['mean'] / ref:.2f}x"
        md.append(f"| {cfg} | {s['mean'] / 1000:.3f} s | {s['spread'] / 1000:.3f} s | "
                  f"{s['p95'] / 1000:.3f} s ({s['n']}) | {rel} |")
    return md, summary


def main():
    acc_md, acc, verdict = accuracy()
    speed_md, spd = speed()
    md = ["# A2 summary (generated)", "",
          "Generated by `python a2/summarise_a2.py` from committed raw files only. Do not edit by hand.", ""]
    md += acc_md + [""] + speed_md
    md += ["", "## Trade-off chart points (slide 6)", "",
           "| Configuration | Mean p50 (s) | Overall accuracy | Passes both limits |", "|---|---|---|---|"]
    for cfg in SPEED_CONFIGS:
        over, fails = verdict(cfg)
        md.append(f"| {cfg} | {spd[cfg]['mean'] / 1000:.3f} | {100 * acc[cfg]:.1f}% | "
                  f"{'reference' if cfg == REFERENCE else ('yes' if over and not fails else 'no')} |")
    OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
