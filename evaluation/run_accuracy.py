# Accuracy experiment: posts every golden ticket to the triage service, once per candidate model.
# For each model it resets storage, starts the service with that model, checks storage is empty,
# warms the model up directly in Ollama (so storage holds only golden tickets), posts the 175 tickets
# one at a time with a unique X-Request-ID, then reconciles the results with /stats and the request log.
#
# Usage (repo root or evaluation/, Docker Desktop and Ollama running):
#   python evaluation/run_accuracy.py                          # all four models, about an hour
#   python evaluation/run_accuracy.py --models qwen2.5:7b      # one model
#   python evaluation/run_accuracy.py --dev-check 3 --models llama3.2:1b   # pipeline test on non-golden rows
#
# Output in evaluation/accuracy_results/: <run_id>.csv (one row per ticket) and <run_id>_summary.json.

import argparse
import csv
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import classifier
import data

ROOT = data.ROOT
LOG_PATH = ROOT / "logs" / "requests.jsonl"
OUT_DIR = Path(__file__).resolve().parent / "accuracy_results"
SERVICE_URL = "http://localhost:8000"
FREEZE_COMMIT = "c51e33c"  # evaluation setup frozen here, before any golden ticket reached a model
FROZEN_FILES = ["evaluation/classifier.py", "evaluation/eval_config.json", "evaluation/prompt_template.md"]
ERROR = "ERROR"  # prediction recorded when the service returns no category
CLIENT_TIMEOUT_S = classifier.REQUEST_TIMEOUT_S + 30  # longer than the service's own Ollama timeout
WARMUP_NARRATIVE = "I was charged a monthly maintenance fee on my checking account that I was told would be waived."
FIELDS = ["run_id", "row", "gold_label", "predicted", "correct", "http_status", "request_id", "ticket_id",
          "model", "model_digest", "client_ms", "error"]


def http(method, path, body=None, headers=None, timeout=30):
    req = urllib.request.Request(SERVICE_URL + path, method=method, headers={"Content-Type": "application/json",
                                 **(headers or {})}, data=json.dumps(body).encode("utf-8") if body else None)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, {"detail": exc.read().decode("utf-8", "replace")}


def compose(*args, model):
    env = {**os.environ, "MODEL": model}
    return subprocess.run(["docker", "compose", *args], cwd=ROOT, env=env, capture_output=True, text=True)


# Fails if the frozen evaluation files differ from the freeze commit
def check_freeze():
    result = subprocess.run(["git", "diff", "--quiet", FREEZE_COMMIT, "--", *FROZEN_FILES], cwd=ROOT)
    if result.returncode != 0:
        sys.exit(f"Frozen evaluation files differ from commit {FREEZE_COMMIT}: refusing to run")
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return head.stdout.strip()


# Resets storage, starts the service with this model and waits until it answers with empty storage
def start_service(model):
    compose("down", "-v", model=model)
    up = compose("up", "-d", "--build", model=model)
    if up.returncode != 0:
        sys.exit(f"docker compose up failed:\n{up.stderr}")
    deadline = time.time() + 180
    while time.time() < deadline:
        try:
            status, stats = http("GET", "/stats")
            if status == 200:
                if stats["total"] != 0:
                    sys.exit(f"Storage not empty after reset: {stats}")
                return
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        time.sleep(2)
    logs = compose("logs", "--tail", "20", model=model)
    sys.exit(f"Service did not become ready for {model}:\n{logs.stdout}{logs.stderr}")


# Unloads every other model from Ollama, then loads this one with an unrecorded request
def warm_up(model):
    for other in classifier.loaded_models():
        if other != model:
            classifier.ollama_post("/api/generate", {"model": other, "keep_alive": 0})
    classifier.classify(WARMUP_NARRATIVE, model)


def load_tickets(dev_check):
    team = {int(r["row"]): r for r in data.load_team_rows()}
    if dev_check:
        rows = data.load_dev_rows(list(team.values()))[:dev_check]
        return [(int(r["row"]), r["source_label"], r["narrative"]) for r in rows]
    golden = data.load_golden()
    return [(row, golden[row], team[row]["narrative"]) for row in sorted(golden)]


def post_ticket(run_id, model, row, gold, narrative):
    request_id = f"{run_id}_r{row}"
    rec = {"run_id": run_id, "row": row, "gold_label": gold, "request_id": request_id, "model": model,
           "model_digest": classifier.MODELS[model], "ticket_id": "", "error": ""}
    started = time.perf_counter()
    try:
        status, body = http("POST", "/tickets", {"narrative": narrative},
                            {"X-Request-ID": request_id, "X-Run-ID": run_id}, timeout=CLIENT_TIMEOUT_S)
    except Exception as exc:
        status, body = 0, {"detail": repr(exc)}
    rec["client_ms"] = round((time.perf_counter() - started) * 1000, 1)
    rec["http_status"] = status
    if status == 200:
        rec["predicted"] = body["category"]
        rec["ticket_id"] = body["id"]
    else:
        rec["predicted"] = ERROR
        rec["error"] = str(body.get("detail", body))[:500]
    rec["correct"] = rec["predicted"] == gold
    return rec


# Checks /stats and the request log agree with the CSV; returns a list of problems (empty when clean)
def reconcile(run_id, model, records):
    problems = []
    status, stats = http("GET", "/stats")
    stored = Counter(r["predicted"] for r in records if r["http_status"] == 200)
    if stats["total"] != sum(stored.values()):
        problems.append(f"/stats total {stats['total']} != {sum(stored.values())} successful posts")
    for label, count in stats["by_category"].items():
        if count != stored.get(label, 0):
            problems.append(f"/stats {label}: {count} != {stored.get(label, 0)} in CSV")

    time.sleep(1)  # the service writes the log line just after replying
    lines = [json.loads(l) for l in LOG_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    by_id = {}
    for line in lines:
        if line.get("run_id") == run_id:
            by_id.setdefault(line["request_id"], []).append(line)
    for r in records:
        found = by_id.get(r["request_id"], [])
        if len(found) != 1:
            problems.append(f"row {r['row']}: {len(found)} log lines for {r['request_id']}")
            continue
        line = found[0]
        if line["status"] != r["http_status"]:
            problems.append(f"row {r['row']}: log status {line['status']} != {r['http_status']}")
        if r["http_status"] == 200 and line.get("category") != r["predicted"]:
            problems.append(f"row {r['row']}: log category {line.get('category')} != {r['predicted']}")
        if line.get("model") != model or line.get("model_digest") != classifier.MODELS[model]:
            problems.append(f"row {r['row']}: log model/digest {line.get('model')} {line.get('model_digest')}")
    return problems, stats, len(by_id)


def run_model(model, tickets, dev_check, git_head):
    prefix = "devcheck" if dev_check else "acc"
    started_at = datetime.now(timezone.utc)
    run_id = f"{prefix}_{model.replace(':', '_')}_{started_at:%Y%m%dT%H%M%SZ}"
    print(f"\n=== {model} | run {run_id} | {len(tickets)} tickets")

    start_service(model)
    warm_up(model)
    vram = classifier.loaded_models()[model]["size_vram"]
    if vram:
        sys.exit(f"{model} is using GPU memory (size_vram={vram}): fix before measuring")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / f"{run_id}.csv"
    records = []
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for i, (row, gold, narrative) in enumerate(tickets, 1):
            rec = post_ticket(run_id, model, row, gold, narrative)
            records.append(rec)
            writer.writerow(rec)
            f.flush()  # keep partial results if the run is interrupted
            print(f"  {i:3d}/{len(tickets)} row {row}: {rec['predicted']:<26s} "
                  f"{'ok' if rec['correct'] else 'x '} {rec['client_ms'] / 1000:6.1f}s"
                  + (f"  HTTP {rec['http_status']}" if rec["http_status"] != 200 else ""))

    problems, stats, logged = reconcile(run_id, model, records)
    correct = sum(r["correct"] for r in records)
    summary = {
        "run_id": run_id, "model": model, "model_digest": classifier.MODELS[model], "dev_check": bool(dev_check),
        "started_utc": started_at.isoformat(timespec="seconds"),
        "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_head": git_head, "freeze_commit": FREEZE_COMMIT,
        "ollama_version": classifier.ollama_get("/api/version")["version"], "size_vram": vram,
        "tickets": len(records), "correct": correct,
        "http_errors": sum(r["http_status"] != 200 for r in records),
        "invalid": sum(r["predicted"] == classifier.INVALID for r in records),
        "stats_after": stats, "log_lines_for_run": logged, "reconciliation_problems": problems,
    }
    (OUT_DIR / f"{run_id}_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"  accuracy {correct}/{len(records)} = {correct / len(records):.1%} | "
          f"INVALID {summary['invalid']} | HTTP errors {summary['http_errors']}")
    print(f"  reconciliation: {'clean' if not problems else f'{len(problems)} PROBLEMS'}")
    for p in problems[:10]:
        print("   -", p)
    print(f"  -> {csv_path.relative_to(ROOT)}")


def main():
    global SERVICE_URL
    parser = argparse.ArgumentParser(description="Post every golden ticket to the triage service for each model")
    parser.add_argument("--models", nargs="+", choices=list(classifier.MODELS), default=list(classifier.MODELS))
    parser.add_argument("--dev-check", type=int, default=0, metavar="N",
                        help="pipeline test: post N non-golden rows instead of the golden set")
    parser.add_argument("--service-url", default=SERVICE_URL)
    args = parser.parse_args()
    SERVICE_URL = args.service_url.rstrip("/")

    git_head = check_freeze()
    classifier.verify_pins()
    tickets = load_tickets(args.dev_check)
    if args.dev_check:
        data.assert_not_golden([{"row": row} for row, _, _ in tickets])
    for model in args.models:
        run_model(model, tickets, args.dev_check, git_head)


if __name__ == "__main__":
    main()
