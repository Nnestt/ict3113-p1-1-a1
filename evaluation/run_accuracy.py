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
#
# Assignment 2: --config runs named configurations from a2/configs.json (single models or the cascade) on the
# rows listed in --rows (default: the test set), and writes to a2/results/accuracy_results/ (see a2/CONTRACTS.md):
#   python evaluation/run_accuracy.py --config single-7b single-phi single-1.5b single-llama cascade-S1 cascade-S2
#   python evaluation/run_accuracy.py --config cascade-S1 --rows a2/split/test_rows.csv
#   python evaluation/run_accuracy.py --config cascade-S1 --dev-check 3        # pipeline test, non-golden rows

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


A2_CONFIGS = json.loads((ROOT / "a2" / "configs.json").read_text(encoding="utf-8"))
A2_OUT_DIR = ROOT / "a2" / "results" / "accuracy_results"
A2_DEFAULT_ROWS = ROOT / "a2" / "split" / "test_rows.csv"
A2_FIELDS = FIELDS + ["config", "escalated", "escalation_reason", "final_model", "small_label", "large_label"]


# Service environment for an A2 configuration name (a2/CONTRACTS.md)
def config_env(name):
    cfg = A2_CONFIGS[name]
    if cfg["mode"] == "single":
        return {"TRIAGE_MODE": "single", "TRIAGE_CONFIG": name, "MODEL": cfg["model"]}
    return {"TRIAGE_MODE": "cascade", "TRIAGE_CONFIG": name, "SMALL_MODEL": cfg["small"],
            "LARGE_MODEL": cfg["large"], "CASCADE_SETTING": cfg["setting"]}


def config_models(name):
    cfg = A2_CONFIGS[name]
    return [cfg["model"]] if cfg["mode"] == "single" else [cfg["small"], cfg["large"]]


def compose(*args, model=None, env=None):
    env = {**os.environ, **(env or {"MODEL": model})}
    return subprocess.run(["docker", "compose", *args], cwd=ROOT, env=env, capture_output=True, text=True)


# Fails if the frozen evaluation files differ from the freeze commit
def check_freeze():
    result = subprocess.run(["git", "diff", "--quiet", FREEZE_COMMIT, "--", *FROZEN_FILES], cwd=ROOT)
    if result.returncode != 0:
        sys.exit(f"Frozen evaluation files differ from commit {FREEZE_COMMIT}: refusing to run")
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return head.stdout.strip()


# Resets storage, starts the service with this model (or A2 env) and waits until it answers with empty storage
def start_service(model, env=None):
    compose("down", "-v", model=model, env=env)
    up = compose("up", "-d", "--build", model=model, env=env)
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
    logs = compose("logs", "--tail", "20", model=model, env=env)
    sys.exit(f"Service did not become ready for {model or env}:\n{logs.stdout}{logs.stderr}")


# Unloads every model not in `models` from Ollama, then loads each of them with an unrecorded request.
# A cascade needs both of its models resident, so neither is unloaded.
def warm_up(model, models=None):
    keep = set(models or [model])
    for other in classifier.loaded_models():
        if other not in keep:
            classifier.ollama_post("/api/generate", {"model": other, "keep_alive": 0})
    for m in models or [model]:
        classifier.classify(WARMUP_NARRATIVE, m)


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


# A2: (row, gold, narrative) for the rows listed in a row file (row,gold_label), in file order
def load_row_file(path):
    team = {int(r["row"]): r for r in data.load_team_rows()}
    golden = data.load_golden()
    with open(path, encoding="utf-8", newline="") as f:
        rows = [int(r["row"]) for r in csv.DictReader(f)]
    missing = [row for row in rows if row not in golden]
    if missing:
        sys.exit(f"{path}: rows not in the golden set: {missing[:5]}")
    return [(row, golden[row], team[row]["narrative"]) for row in rows]


def a2_reconcile(run_id, name, records):
    models = config_models(name)
    problems = []
    status, stats = http("GET", "/stats")
    ok = [r for r in records if r["http_status"] == 200]
    if stats["total"] != len(ok):
        problems.append(f"/stats total {stats['total']} != {len(ok)} successful posts")
    time.sleep(1)  # the service writes the log line just after replying
    lines = [json.loads(l) for l in LOG_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    run_lines = [l for l in lines if l.get("run_id") == run_id]
    by_id = {}
    for line in run_lines:
        by_id.setdefault(line["request_id"], []).append(line)
    for r in records:
        found = by_id.get(r["request_id"], [])
        if len(found) != 1:
            problems.append(f"row {r['row']}: {len(found)} log lines for {r['request_id']}")
            continue
        line = found[0]
        for field in ["config", "escalated", "escalation_reason", "final_model", "small_label", "large_label"]:
            r[field] = line.get(field)
        if line["status"] != r["http_status"]:
            problems.append(f"row {r['row']}: log status {line['status']} != {r['http_status']}")
        if r["http_status"] != 200:
            continue
        r["model"], r["model_digest"] = line.get("model"), line.get("model_digest")
        if line.get("category") != r["predicted"]:
            problems.append(f"row {r['row']}: log category {line.get('category')} != {r['predicted']}")
        if line.get("model") not in models or line.get("model_digest") != classifier.MODELS.get(line.get("model")):
            problems.append(f"row {r['row']}: log model/digest {line.get('model')} {line.get('model_digest')}")
        if line.get("config") != name:
            problems.append(f"row {r['row']}: log config {line.get('config')} != {name}")
    return problems, stats, run_lines


def run_config(name, tickets, dev_check, git_head):
    started_at = datetime.now(timezone.utc)
    run_id = f"devcheck_{name}_{started_at:%Y%m%dT%H%M%SZ}" if dev_check else f"acc_{name}"
    csv_path = A2_OUT_DIR / f"{run_id}.csv"
    if csv_path.exists():
        sys.exit(f"{csv_path.relative_to(ROOT)} already exists: never overwrite an accuracy result")
    models = config_models(name)
    print(f"\n=== {name} ({' -> '.join(models)}) | run {run_id} | {len(tickets)} tickets")

    start_service(None, env=config_env(name))
    warm_up(None, models)
    loaded = classifier.loaded_models()
    missing = [m for m in models if m not in loaded]
    if missing:
        sys.exit(f"{missing} not loaded after warm-up: both cascade models must be resident (ollama ps)")
    vram = {m: loaded[m]["size_vram"] for m in models}
    if any(vram.values()):
        sys.exit(f"GPU memory in use {vram}: fix before measuring")

    A2_OUT_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    for i, (row, gold, narrative) in enumerate(tickets, 1):
        rec = post_ticket(run_id, models[-1], row, gold, narrative)
        records.append(rec)
        print(f"  {i:3d}/{len(tickets)} row {row}: {rec['predicted']:<26s} "
              f"{'ok' if rec['correct'] else 'x '} {rec['client_ms'] / 1000:6.1f}s"
              + (f"  HTTP {rec['http_status']}" if rec["http_status"] != 200 else ""))

    problems, stats, run_lines = a2_reconcile(run_id, name, records)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=A2_FIELDS)
        writer.writeheader()
        writer.writerows(records)
    log_copy = A2_OUT_DIR / f"{run_id}_requests.jsonl"
    log_copy.write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in run_lines), encoding="utf-8")

    correct = sum(r["correct"] for r in records)
    escalated = sum(r.get("escalated") is True for r in records)
    summary = {
        "run_id": run_id, "config": name, "models": {m: classifier.MODELS[m] for m in models},
        "rows_file": None if dev_check else str(ARGS_ROWS.relative_to(ROOT)), "dev_check": bool(dev_check),
        "started_utc": started_at.isoformat(timespec="seconds"),
        "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_head": git_head, "freeze_commit": FREEZE_COMMIT,
        "ollama_version": classifier.ollama_get("/api/version")["version"], "size_vram": vram,
        "tickets": len(records), "correct": correct, "escalated": escalated,
        "http_errors": sum(r["http_status"] != 200 for r in records),
        "invalid": sum(r["predicted"] == classifier.INVALID for r in records),
        "stats_after": stats, "log_lines_for_run": len(run_lines), "reconciliation_problems": problems,
    }
    (A2_OUT_DIR / f"{run_id}_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"  accuracy {correct}/{len(records)} = {correct / len(records):.1%} | escalated {escalated} | "
          f"INVALID {summary['invalid']} | HTTP errors {summary['http_errors']}")
    print(f"  reconciliation: {'clean' if not problems else f'{len(problems)} PROBLEMS'}")
    for p in problems[:10]:
        print("   -", p)
    print(f"  -> {csv_path.relative_to(ROOT)}")
    return csv_path


ARGS_ROWS = A2_DEFAULT_ROWS


def main():
    global SERVICE_URL, ARGS_ROWS
    parser = argparse.ArgumentParser(description="Post every golden ticket to the triage service for each model")
    parser.add_argument("--models", nargs="+", choices=list(classifier.MODELS), default=list(classifier.MODELS))
    parser.add_argument("--config", nargs="+", choices=list(A2_CONFIGS), metavar="NAME",
                        help=f"A2: run these configurations from a2/configs.json ({', '.join(A2_CONFIGS)})")
    parser.add_argument("--rows", type=Path, default=A2_DEFAULT_ROWS,
                        help="A2: row file (row,gold_label) to post, default a2/split/test_rows.csv")
    parser.add_argument("--dev-check", type=int, default=0, metavar="N",
                        help="pipeline test: post N non-golden rows instead of the golden set")
    parser.add_argument("--service-url", default=SERVICE_URL)
    args = parser.parse_args()
    SERVICE_URL = args.service_url.rstrip("/")
    ARGS_ROWS = args.rows.resolve()

    git_head = check_freeze()
    classifier.verify_pins()
    if args.config:
        tickets = load_tickets(args.dev_check) if args.dev_check else load_row_file(ARGS_ROWS)
        if args.dev_check:
            data.assert_not_golden([{"row": row} for row, _, _ in tickets])
        written = [run_config(name, tickets, args.dev_check, git_head) for name in args.config]
        if not args.dev_check:
            print("\nCommit the results (commit 5 in plan.md):")
            print(f"  git add {' '.join(str(p.relative_to(ROOT).parent / (p.stem + '*')) for p in written)}")
            print('  git commit -m "A2 Step 4: accuracy test on the test set"')
            print("  git push")
        return
    tickets = load_tickets(args.dev_check)
    if args.dev_check:
        data.assert_not_golden([{"row": row} for row, _, _ in tickets])
    for model in args.models:
        run_model(model, tickets, args.dev_check, git_head)


if __name__ == "__main__":
    main()
