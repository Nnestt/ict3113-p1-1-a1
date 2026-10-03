# Ticket classifier used by the triage service, the smoke test and the accuracy run.
# Every candidate model gets the same prompt (prompt_template.md), the same generation
# options and pins (eval_config.json) and the same parser. Standard library only.
#
# Usage:
#   python classifier.py --self-test
#   python classifier.py --model qwen2.5:1.5b "My bank froze my account and kept my paycheck."
#
# OLLAMA_URL overrides the Ollama address, e.g. http://host.docker.internal:11434 inside Docker.

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "eval_config.json"
CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
PROMPT_TEMPLATE = (HERE / CONFIG["prompt_file"]).read_text(encoding="utf-8").rstrip()
assert "{narrative}" in PROMPT_TEMPLATE, "prompt template must contain {narrative}"

MODELS = CONFIG["models"]
LABELS = CONFIG["labels"]
INVALID = CONFIG["invalid_label"]
OPTIONS = CONFIG["options"]
KEEP_ALIVE = CONFIG["keep_alive"]
REQUEST_TIMEOUT_S = CONFIG["request_timeout_seconds"]
OLLAMA_URL = os.environ.get("OLLAMA_URL", CONFIG["ollama_url"]).rstrip("/")

PARSER_RULES = [
    "Exact match against a label, ignoring case, surrounding quotes/asterisks/punctuation and a leading 'Category:'",
    "Otherwise, if exactly one label name appears anywhere in the output, use it",
    "Otherwise INVALID (counted as wrong, kept visible)",
]

# Made-up model outputs and the label the parser should return for each
PARSER_CASES = [
    ("Credit reporting", "Credit reporting"),
    ("Credit reporting: dispute.", "Credit reporting"),
    ("Debt collection", "Debt collection"),
    ("**Credit card**", "Credit card"),
    ("Category: mortgage.", "Mortgage"),
    ('"Bank account or service"', "Bank account or service"),
    ("The principal problem is Consumer loan because the borrower ...", "Consumer loan"),
    ("Money transfer or service\n\nThe customer sent a wire ...", "Money transfer or service"),
    ("Credit card or Bank account or service", INVALID),
    ("I cannot determine this.", INVALID),
    ("", INVALID),
]


def ollama_get(path, timeout=30):
    with urllib.request.urlopen(OLLAMA_URL + path, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ollama_post(path, payload, timeout=REQUEST_TIMEOUT_S):
    req = urllib.request.Request(OLLAMA_URL + path, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def build_prompt(narrative):
    return PROMPT_TEMPLATE.replace("{narrative}", narrative.strip())


# Maps raw model text to one of the seven labels, or INVALID (rules in PARSER_RULES)
def parse_label(raw):
    text = raw.strip()
    first = text.splitlines()[0] if text else ""
    cand = first.strip().strip("\"'`*.:- ").strip()
    if cand.casefold().startswith("category:"):
        cand = cand[len("category:"):].strip().strip("\"'`*.:- ").strip()
    for label in LABELS:
        if cand.casefold() == label.casefold():
            return label
    found = [label for label in LABELS if label.casefold() in text.casefold()]
    return found[0] if len(found) == 1 else INVALID


# Classifies one narrative. HTTP and connection errors are raised so the caller can log them.
# Timings are in ms: wall_ms is the whole call as the caller sees it, load_ms is non-zero
# when Ollama had to load the model first.
def classify(narrative, model, options=None):
    if model not in MODELS:
        raise ValueError(f"{model} is not a pinned candidate")
    opts = {**OPTIONS, **(options or {})}
    started = time.perf_counter()
    body = ollama_post("/api/generate", {"model": model, "prompt": build_prompt(narrative), "stream": False,
                                         "options": opts, "keep_alive": KEEP_ALIVE})
    wall_ms = (time.perf_counter() - started) * 1000
    raw = body.get("response", "")
    prompt_tokens = body.get("prompt_eval_count", 0)
    return {
        "label": parse_label(raw),
        "raw_output": raw,
        "wall_ms": round(wall_ms, 1),
        "load_ms": round(body.get("load_duration", 0) / 1e6, 1),
        "prompt_eval_ms": round(body.get("prompt_eval_duration", 0) / 1e6, 1),
        "eval_ms": round(body.get("eval_duration", 0) / 1e6, 1),
        "prompt_tokens": prompt_tokens,
        "output_tokens": body.get("eval_count", 0),
        # Ollama silently drops the start of a prompt longer than num_ctx
        "possibly_truncated": prompt_tokens + opts["num_predict"] >= opts["num_ctx"],
    }


# Fails if any pinned model is missing or its local digest differs from the pin
def verify_pins():
    local = {m["name"]: m for m in ollama_get("/api/tags")["models"]}
    details = {}
    for model, pinned in MODELS.items():
        entry = local.get(model)
        if entry is None:
            raise LookupError(f"{model} is not pulled in Ollama")
        if entry["digest"] != pinned:
            raise ValueError(f"{model}: local digest {entry['digest']} != pinned {pinned}")
        d = entry.get("details", {})
        details[model] = {"size_gb": round(entry["size"] / 1e9, 2), "parameters": d.get("parameter_size"),
                          "quantization": d.get("quantization_level")}
    return details


# Models currently in memory; size_vram == 0 means the model runs entirely on CPU
def loaded_models():
    return {m["name"]: {"size": m["size"], "size_vram": m.get("size_vram", 0)}
            for m in ollama_get("/api/ps")["models"]}


def self_test():
    for raw, expected in PARSER_CASES:
        got = parse_label(raw)
        assert got == expected, f"parse_label({raw!r}) returned {got!r}, expected {expected!r}"
    print(f"Parser self-check passed ({len(PARSER_CASES)} cases)")
    print("Ollama version:", ollama_get("/api/version")["version"])
    for model, d in verify_pins().items():
        print(f"{model:13s} digest OK | {d['size_gb']:.2f} GB | {d['parameters']} | {d['quantization']}")


def main():
    parser = argparse.ArgumentParser(description="Classify one complaint narrative with a pinned candidate model")
    parser.add_argument("narrative", nargs="?", help="complaint text (do not use golden-set tickets)")
    parser.add_argument("--model", choices=list(MODELS), help="candidate model tag")
    parser.add_argument("--self-test", action="store_true", help="check the parser and the model digests")
    args = parser.parse_args()

    if args.self_test:
        self_test()
    elif args.narrative and args.model:
        print(json.dumps(classify(args.narrative, args.model), indent=2))
    else:
        parser.error("give --self-test, or --model and a narrative")


if __name__ == "__main__":
    sys.exit(main())