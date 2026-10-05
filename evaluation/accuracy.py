# Accuracy analysis of the runs written by run_accuracy.py: overall accuracy, per-category correct/total,
# confusion matrices, requirement checks (R5, R6), predictions vs results and single-request latency.
# Failed requests (ERROR) and unparseable replies (INVALID) count as wrong and stay visible everywhere.

import csv
import json
import math
import statistics
from collections import Counter
from pathlib import Path

import classifier

RESULTS_DIR = Path(__file__).resolve().parent / "accuracy_results"
LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "requests.jsonl"
GOLDEN_SIZE = 175
ERROR = "ERROR"
LABELS = classifier.LABELS
PRED_COLUMNS = LABELS + [classifier.INVALID, ERROR]
R5_OVERALL = 0.80  # performance-requirements.md
R6_PER_CATEGORY = 0.65

# Frozen predictions from prediction-record.md: (overall accuracy, warm single-request latency in s)
PREDICTED = {
    "llama3.2:1b": (0.68, 2.5),
    "qwen2.5:1.5b": (0.73, 3.5),
    "phi3.5:3.8b": (0.79, 7.0),
    "qwen2.5:7b": (0.84, 12.0),
}

SHORT = {
    "Credit reporting": "CredRep", "Debt collection": "Debt", "Mortgage": "Mortg", "Credit card": "Card",
    "Bank account or service": "Bank", "Consumer loan": "Loan", "Money transfer or service": "Transfer",
    classifier.INVALID: "INVALID", ERROR: "ERROR",
}


# Latest complete golden run per model, in pinned-model order: {model: (summary, records)}
def load_runs(results_dir=RESULTS_DIR):
    runs = {}
    for path in sorted(results_dir.glob("acc_*_summary.json")):
        summary = json.loads(path.read_text(encoding="utf-8"))
        if summary["tickets"] != GOLDEN_SIZE:
            continue
        with (results_dir / f"{summary['run_id']}.csv").open(encoding="utf-8", newline="") as f:
            records = list(csv.DictReader(f))
        prev = runs.get(summary["model"])
        if prev is None or summary["started_utc"] > prev[0]["started_utc"]:
            runs[summary["model"]] = (summary, records)
    return {m: runs[m] for m in classifier.MODELS if m in runs}


# 95% Wilson score interval for k correct out of n
def wilson(k, n, z=1.96):
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


def metrics(records):
    n = len(records)
    correct = sum(r["predicted"] == r["gold_label"] for r in records)
    per_cat = {}
    confusion = {g: Counter() for g in LABELS}
    for r in records:
        confusion[r["gold_label"]][r["predicted"]] += 1
    for g in LABELS:
        total = sum(confusion[g].values())
        per_cat[g] = (confusion[g][g], total)
    off_diag = Counter({(g, p): c for g in LABELS for p, c in confusion[g].items() if p != g})
    return {"n": n, "correct": correct, "accuracy": correct / n, "ci": wilson(correct, n), "per_cat": per_cat,
            "confusion": confusion, "top_confusions": off_diag.most_common(),
            "invalid": sum(r["predicted"] == classifier.INVALID for r in records),
            "errors": sum(r["predicted"] == ERROR for r in records)}


def requirement_checks(m):
    present = [g for g in LABELS if m["per_cat"][g][1]]
    worst = min(present, key=lambda g: m["per_cat"][g][0] / m["per_cat"][g][1])
    worst_rate = m["per_cat"][worst][0] / m["per_cat"][worst][1]
    return {"R5": m["accuracy"] >= R5_OVERALL, "R6": worst_rate >= R6_PER_CATEGORY,
            "worst_category": worst, "worst_rate": worst_rate}


# Service-side timings for the run's requests from the request log: medians and p95 in seconds
def run_latency(run_id, log_path=LOG_PATH):
    lines = [json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    lines = [l for l in lines if l.get("run_id") == run_id and l.get("status") == 200]
    if not lines:
        return None
    pick = lambda key: sorted(l[key] / 1000 for l in lines if l.get(key) is not None)
    p95 = lambda xs: xs[min(len(xs) - 1, math.ceil(0.95 * len(xs)) - 1)]
    total, model = pick("total_ms"), pick("model_ms")
    return {"requests": len(lines), "total_median_s": statistics.median(total), "total_p95_s": p95(total),
            "model_median_s": statistics.median(model), "model_p95_s": p95(model),
            "truncated": sum(bool(l.get("possibly_truncated")) for l in lines)}


def print_summary(runs):
    print(f"{'model':13s} {'correct':>8s} {'acc':>6s} {'95% CI':>13s} {'INVALID':>7s} {'ERROR':>5s} "
          f"{'R5>=80%':>7s} {'R6>=65%':>7s}  worst category")
    for model, (_, records) in runs.items():
        m, req = metrics(records), requirement_checks(metrics(records))
        lo, hi = m["ci"]
        print(f"{model:13s} {m['correct']:>4d}/{m['n']:<3d} {m['accuracy']:>6.1%} {lo:>6.1%}-{hi:<6.1%} "
              f"{m['invalid']:>7d} {m['errors']:>5d} {'PASS' if req['R5'] else 'FAIL':>7s} "
              f"{'PASS' if req['R6'] else 'FAIL':>7s}  {req['worst_category']} ({req['worst_rate']:.0%})")


def print_per_category(runs):
    models = list(runs)
    print(f"{'gold category':26s} {'n':>3s} " + " ".join(f"{m:>14s}" for m in models))
    for g in LABELS:
        cells = []
        for model in models:
            c, t = metrics(runs[model][1])["per_cat"][g]
            rate = c / t if t else 0
            cells.append(f"{c:>3d}/{t:<3d}{rate:>6.0%}{'*' if t and rate < R6_PER_CATEGORY else ' '}")
        print(f"{g:26s} {metrics(runs[models[0]][1])['per_cat'][g][1]:>3d} " + " ".join(f"{x:>14s}" for x in cells))
    print("* below the 65% per-category requirement (R6)")


def print_confusion(model, records):
    conf = metrics(records)["confusion"]
    cols = [p for p in PRED_COLUMNS if p in LABELS or any(conf[g][p] for g in LABELS)]
    print(f"{model}: rows = gold label, columns = prediction")
    print(f"{'':10s}" + "".join(f"{SHORT[p]:>9s}" for p in cols) + f"{'total':>7s}")
    for g in LABELS:
        print(f"{SHORT[g]:10s}" + "".join(f"{conf[g][p]:>9d}" for p in cols) + f"{sum(conf[g].values()):>7d}")


def print_top_confusions(runs, k=3):
    for model, (_, records) in runs.items():
        top = metrics(records)["top_confusions"][:k]
        print(f"{model:13s} " + "; ".join(f"{g} -> {p} ({c})" for (g, p), c in top))


def print_predictions(runs):
    print(f"{'model':13s} {'pred acc':>8s} {'actual':>7s} {'diff':>6s} {'pred lat':>8s} {'median':>7s} {'p95':>6s}")
    for model, (summary, records) in runs.items():
        p_acc, p_lat = PREDICTED[model]
        m, lat = metrics(records), run_latency(summary["run_id"])
        med = f"{lat['total_median_s']:.2f}s" if lat else "n/a"
        p95 = f"{lat['total_p95_s']:.2f}s" if lat else "n/a"
        print(f"{model:13s} {p_acc:>8.0%} {m['accuracy']:>7.1%} {(m['accuracy'] - p_acc) * 100:>+5.1f}pp "
              f"{p_lat:>7.1f}s {med:>7s} {p95:>6s}")
    print("Latency = service total_ms from the request log for this run (sequential, warm, one request at a time)")


# Writes summary, per-category and confusion CSVs for the slides and for Ernest's cross-check
def export(runs, out_dir=RESULTS_DIR):
    with (out_dir / "accuracy_summary.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "model_digest", "run_id", "correct", "total", "accuracy", "ci_low", "ci_high",
                    "invalid", "errors", "R5_pass", "R6_pass", "worst_category", "worst_rate"])
        for model, (summary, records) in runs.items():
            m, req = metrics(records), requirement_checks(metrics(records))
            w.writerow([model, summary["model_digest"], summary["run_id"], m["correct"], m["n"],
                        round(m["accuracy"], 4), round(m["ci"][0], 4), round(m["ci"][1], 4), m["invalid"],
                        m["errors"], req["R5"], req["R6"], req["worst_category"], round(req["worst_rate"], 4)])
    with (out_dir / "accuracy_per_category.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "gold_label", "correct", "total", "accuracy"])
        for model, (_, records) in runs.items():
            for g, (c, t) in metrics(records)["per_cat"].items():
                w.writerow([model, g, c, t, round(c / t, 4) if t else ""])
    for model, (_, records) in runs.items():
        conf = metrics(records)["confusion"]
        with (out_dir / f"confusion_{model.replace(':', '_')}.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["gold \\ predicted"] + PRED_COLUMNS + ["total"])
            for g in LABELS:
                w.writerow([g] + [conf[g][p] for p in PRED_COLUMNS] + [sum(conf[g].values())])
    print("Wrote accuracy_summary.csv, accuracy_per_category.csv and confusion_<model>.csv to", out_dir.name)
