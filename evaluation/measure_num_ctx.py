# Picks num_ctx from the team's ticket lengths without sending any golden ticket to a model.
# Character lengths come from all 1,000 team rows (length only). Token counts come from the
# longest non-golden rows with a large temporary context, which gives each model's worst
# tokens-per-character ratio; that ratio is applied to the longest team narrative.
#
# Usage:
#   python measure_num_ctx.py                  # all candidates, print the recommendation
#   python measure_num_ctx.py --write          # also store it in eval_config.json
#   python measure_num_ctx.py --models llama3.2:1b --sample 5

import argparse
import json
import math
import statistics

import classifier
import data

CANDIDATE_CTX = (2048, 4096, 8192, 16384, 32768)
PROBE = {"num_ctx": 32768, "num_predict": 1}


def percentile(sorted_values, q):
    return sorted_values[min(len(sorted_values) - 1, math.ceil(q * len(sorted_values)) - 1)]


def length_stats(team):
    lengths = sorted(len(r["narrative"]) for r in team)
    return {"rows": len(lengths), "min": lengths[0], "median": statistics.median(lengths),
            "p95": percentile(lengths, 0.95), "p99": percentile(lengths, 0.99), "max": lengths[-1]}


# Returns (length stats, {model: tokens needed for the longest team ticket}, recommended num_ctx)
def measure(team, dev_rows, models, sample=20):
    stats = length_stats(team)
    longest_dev = sorted(dev_rows, key=lambda r: len(r["narrative"]), reverse=True)[:sample]
    data.assert_not_golden(longest_dev)

    needed = {}
    for model in models:
        template_tokens = classifier.classify("", model, PROBE)["prompt_tokens"]
        ratio = max((classifier.classify(r["narrative"], model, PROBE)["prompt_tokens"] - template_tokens)
                    / len(r["narrative"]) for r in longest_dev)
        needed[model] = template_tokens + math.ceil(ratio * stats["max"]) + classifier.OPTIONS["num_predict"]
        print(f"{model:13s} template {template_tokens} tok | worst {ratio:.3f} tok/char | "
              f"longest team ticket needs ~{needed[model]} tok")

    recommended = next(c for c in CANDIDATE_CTX if c >= max(needed.values()) * 1.1)
    return stats, needed, recommended


def write_num_ctx(value):
    config = json.loads(classifier.CONFIG_PATH.read_text(encoding="utf-8"))
    config["options"]["num_ctx"] = value
    classifier.CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Choose num_ctx from team ticket lengths")
    parser.add_argument("--models", nargs="+", choices=list(classifier.MODELS), default=list(classifier.MODELS))
    parser.add_argument("--sample", type=int, default=20, help="longest development rows to tokenise")
    parser.add_argument("--write", action="store_true", help="store the recommendation in eval_config.json")
    args = parser.parse_args()

    team = data.load_team_rows()
    stats = length_stats(team)
    print("Narrative characters (team rows): " + ", ".join(f"{k} {v:g}" for k, v in stats.items()))
    _, _, recommended = measure(team, data.load_dev_rows(team), args.models, args.sample)
    print(f"\nRecommended num_ctx (10% margin): {recommended} (current: {classifier.OPTIONS['num_ctx']})")
    if args.write:
        write_num_ctx(recommended)
        print(f"Wrote num_ctx = {recommended} to {classifier.CONFIG_PATH.name}")


if __name__ == "__main__":
    main()