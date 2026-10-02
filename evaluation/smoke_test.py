# CPU-only check and smoke test of every candidate on a seeded sample of non-golden team rows.
# Source labels are noisy, so agreement with them is only a sanity check, not accuracy.
# What we're looking for: every output parses, nothing truncates, no request fails,
# and latency looks plausible.
#
# Usage:
#   python smoke_test.py                                    # all candidates, 4 rows per source category
#   python smoke_test.py --models llama3.2:1b --per-source 1

import argparse
import csv
import math
import random
import statistics
from pathlib import Path

import classifier
import data

SMOKE_SEED = 3113
DEFAULT_OUT = Path(__file__).resolve().parent / "smoke_results"
FIELDS = ["row", "source_label", "model", "model_digest", "label", "raw_output", "wall_ms", "load_ms",
          "prompt_eval_ms", "eval_ms", "prompt_tokens", "output_tokens", "possibly_truncated", "error"]
WARMUP_NARRATIVE = "I was charged a monthly maintenance fee on my checking account that I was told would be waived."


# Loads each model and checks none of it sits in GPU memory; returns {model: size_vram}
def check_cpu_only(models):
    vram = {}
    for model in models:
        classifier.classify(WARMUP_NARRATIVE, model)
        vram[model] = classifier.loaded_models()[model]["size_vram"]
        print(f"{model:13s} size_vram {vram[model]} -> {'CPU only' if vram[model] == 0 else 'GPU IN USE'}")
    assert all(v == 0 for v in vram.values()), "GPU offload detected: fix before any measured run"
    return vram


def sample_rows(dev_rows, per_source, seed=SMOKE_SEED):
    rng = random.Random(seed)
    by_source = {}
    for r in dev_rows:
        by_source.setdefault(r["source_label"], []).append(r)
    rows = [r for label in sorted(by_source) for r in rng.sample(by_source[label], per_source)]
    data.assert_not_golden(rows)
    return rows


# Sends every row to every model after one warm-up request and writes one CSV per model
def run(models, rows, out_dir=DEFAULT_OUT):
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for model in models:
        classifier.classify(WARMUP_NARRATIVE, model)  # warm-up, not recorded
        records = []
        for r in rows:
            rec = {"row": r["row"], "source_label": r["source_label"], "model": model,
                   "model_digest": classifier.MODELS[model], "error": ""}
            try:
                rec.update(classifier.classify(r["narrative"], model))
            except Exception as exc:
                rec.update(label=classifier.INVALID, error=repr(exc))
            records.append(rec)
        results[model] = records
        path = out_dir / f"smoke_{model.replace(':', '_')}.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(records)
        print(f"{model} done -> {path}")
    return results


def summarise(results):
    print(f"\n{'model':13s} {'valid':>7s} {'errors':>6s} {'trunc':>5s} {'=source':>8s} {'median s':>9s} {'max s':>6s}")
    for model, records in results.items():
        n = len(records)
        valid = sum(r["label"] != classifier.INVALID for r in records)
        errors = sum(bool(r["error"]) for r in records)
        trunc = sum(bool(r.get("possibly_truncated")) for r in records)
        agree = sum(r["label"] == r["source_label"] for r in records)
        times = [r["wall_ms"] / 1000 for r in records if not r["error"]]
        med = statistics.median(times) if times else math.nan
        top = max(times) if times else math.nan
        print(f"{model:13s} {valid:>3d}/{n:<3d} {errors:>6d} {trunc:>5d} {agree:>4d}/{n:<3d} {med:>9.2f} {top:>6.2f}")

    unmapped = [(m, r) for m, records in results.items() for r in records if r["label"] == classifier.INVALID]
    print("\nOutputs the parser could not map (fix the parser for all models, not the prompt for one):")
    for model, r in unmapped:
        print(f"  {model} row {r['row']}: {r.get('raw_output', '')!r} {r['error']}")
    if not unmapped:
        print("  none")


def main():
    parser = argparse.ArgumentParser(description="CPU-only check and smoke test on non-golden team rows")
    parser.add_argument("--models", nargs="+", choices=list(classifier.MODELS), default=list(classifier.MODELS))
    parser.add_argument("--per-source", type=int, default=4, help="development rows per source category")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="folder for the per-model CSVs")
    parser.add_argument("--skip-cpu-check", action="store_true")
    args = parser.parse_args()

    if not args.skip_cpu_check:
        check_cpu_only(args.models)
    rows = sample_rows(data.load_dev_rows(), args.per_source)
    print(f"{len(rows)} smoke rows: {sorted(int(r['row']) for r in rows)}")
    summarise(run(args.models, rows, args.out))


if __name__ == "__main__":
    main()