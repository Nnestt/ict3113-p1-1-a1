"""Per-minute analysis of one stress-ramp run, as Markdown for the results record.

Usage (from load_test/):
    python stress_summary.py qwen7b-stress --run 1 [--record ../results-record.md]

Inputs (all kept in the repository):
  results/<label>_run<N>.jtl            JMeter samples; timeStamp is the request START
                                         (sampleresult.timestamp.start=true in jmeter.properties)
  logs/<label>_run<N>_requests.jsonl    SUT log; ts is the END of the request, so
                                         start = ts - total_ms. queue wait = total_ms - model_ms
                                         (time waiting for a worker thread and inside Ollama's queue
                                         is split: worker-thread wait is outside model_ms, Ollama's
                                         own queue is inside model_ms; see service/DESIGN.md)
  results/<label>_run<N>_cpu.csv        SUT samples about every 5 s (SUT clock): total CPU %, free RAM MB,
                                         Ollama and Docker-VM process CPU as % of the whole machine

Minute bins are counted from the first JMeter sample. The two machines' clocks agree to well
under a second (checked on llama1b-15m-run1), so SUT-side data is binned on the same wall clock.

Limit criteria (fixed before the run):
  - R1 breach: first minute whose POSTs (by start time) have p95 > 60 s.
  - Error onset: first minute whose POSTs have an error rate >= 1%.
  - Saturation: the highest sustained completion rate (best 3-minute rolling mean of
    successful completions per minute) is the service's measured capacity; the ramp passes it
    when the offered rate exceeds it, after which latency grows without bound.
"""
import argparse
import csv
import json
import math
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
R1_MS = 60_000


def pct(v, p):
    if not v:
        return None
    s = sorted(v)
    return s[min(len(s) - 1, math.ceil(p / 100 * len(s)) - 1)]


def f0(x):
    return "-" if x is None else f"{x:,.0f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--record")
    a = ap.parse_args()
    base = f"{a.label}_run{a.run}"
    run_id = f"{a.label}-run{a.run}"

    with open(os.path.join(HERE, "results", base + ".jtl"), newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit("empty jtl")
    t0 = min(int(r["timeStamp"]) for r in rows) / 1000
    post = [r for r in rows if r["label"] == "POST /tickets"]
    srch = [r for r in rows if r["label"] == "GET /search"]
    end = max((int(r["timeStamp"]) + int(r["elapsed"])) / 1000 for r in rows)
    nmin = int((end - t0) // 60) + 1

    def minute(ts):
        return int((ts - t0) // 60)

    B = [dict(off=0, ok_done=0, lat=[], err=0, s_lat=[], qwait=[], model=[], cpu=[], mem=[], oll=[]) for _ in range(nmin)]
    for r in post:
        st = int(r["timeStamp"]) / 1000
        b = B[minute(st)]
        b["off"] += 1
        b["lat"].append(int(r["elapsed"]))
        if r["success"] != "true":
            b["err"] += 1
        else:
            B[min(nmin - 1, minute(st + int(r["elapsed"]) / 1000))]["ok_done"] += 1
    for r in srch:
        B[minute(int(r["timeStamp"]) / 1000)]["s_lat"].append(int(r["elapsed"]))

    # SUT log: queue wait and model time per POST, by start time
    logp = os.path.join(HERE, "logs", base + "_requests.jsonl")
    n_log = 0
    if os.path.exists(logp):
        with open(logp, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                if rec.get("run_id") != run_id:
                    continue
                n_log += 1
                if rec.get("route") != "/tickets" or rec.get("method") != "POST" or "model_ms" not in rec:
                    continue
                st = datetime.fromisoformat(rec["ts"]).timestamp() - rec["total_ms"] / 1000
                m = minute(st)
                if 0 <= m < nmin:
                    B[m]["qwait"].append(rec["total_ms"] - rec["model_ms"])
                    B[m]["model"].append(rec["model_ms"])

    # SUT CPU / memory: run_stress.ps1 writes time,cpu_total_pct,avail_mb,ollama_cpu_pct,vmmem_cpu_pct
    # (SUT local time; process CPU already divided by the logical core count)
    cpup = os.path.join(HERE, "results", base + "_cpu.csv")
    cpu_note = "CPU log missing."
    if os.path.exists(cpup):
        with open(cpup, newline="", encoding="utf-8-sig", errors="replace") as f:
            rd = list(csv.DictReader(f))
        for row in rd:
            try:
                ts = datetime.fromisoformat(row["time"]).timestamp()
                m = minute(ts)
                if 0 <= m < nmin:
                    B[m]["cpu"].append(float(row["cpu_total_pct"]))
                    B[m]["mem"].append(float(row["avail_mb"]))
                    B[m]["oll"].append(float(row["ollama_cpu_pct"]))
            except (ValueError, KeyError, TypeError):
                continue
        peak = max((float(r["cpu_total_pct"]) for r in rd if r.get("cpu_total_pct")), default=None)
        cpu_note = f"CPU log: {len(rd)} samples on the SUT, peak total CPU {f0(peak)}%."

    # Limit findings
    ok = [b["ok_done"] for b in B]
    roll = [sum(ok[i:i + 3]) / 3 for i in range(max(1, len(ok) - 2))]
    cap_per_min = max(roll) if roll else 0
    cap_at = roll.index(cap_per_min) if roll else 0
    r1 = next((i for i, b in enumerate(B) if b["lat"] and pct(b["lat"], 95) > R1_MS), None)
    eon = next((i for i, b in enumerate(B) if b["off"] and b["err"] / b["off"] >= 0.01), None)
    sat = next((i for i, b in enumerate(B) if b["off"] > cap_per_min and cap_per_min > 0), None)

    tot_ok = sum(ok)
    tot_err = sum(b["err"] for b in B)
    out = [f"<!-- generated by load_test/stress_summary.py {a.label} --run {a.run} -->"]
    out.append(f"Run `{run_id}`: {len(post)} POST /tickets offered, {tot_ok} succeeded, {tot_err} failed; "
               f"{len(srch)} GET /search. JMeter requests {len(rows)}, SUT log lines for this run ID {n_log} "
               f"({'match' if n_log == len(rows) else 'MISMATCH'}). {cpu_note}")
    out.append("")
    out.append("| Minute | POST offered (/hr) | POST succeeded (/hr) | POST p50 (ms) | POST p95 (ms) | POST errors | Mean queue wait (ms) | Mean model time (ms) | Search p95 (ms) | SUT CPU mean (%) | Ollama CPU mean (%) | SUT free RAM min (MB) |")
    out.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for i, b in enumerate(B):
        mean = lambda v: sum(v) / len(v) if v else None
        out.append(
            f"| {i} | {b['off'] * 60} | {b['ok_done'] * 60} | {f0(pct(b['lat'], 50))} | {f0(pct(b['lat'], 95))} | "
            f"{b['err']} | {f0(mean(b['qwait']))} | {f0(mean(b['model']))} | {f0(pct(b['s_lat'], 95))} | "
            f"{f0(mean(b['cpu']))} | {f0(mean(b['oll']))} | {f0(min(b['mem']) if b['mem'] else None)} |"
        )
    out.append("")
    out.append("Minutes count from the first request. Rates are per-minute counts × 60. "
               "Offered and latency columns use each request's start minute; succeeded uses its finish minute.")
    out.append("")
    out.append("**Limit findings (criteria fixed before the run):**")
    out.append("")
    out.append(f"- **Measured capacity:** {cap_per_min * 60:,.0f} successful classifications/hour "
               f"(best 3-minute rolling mean, minutes {cap_at}–{cap_at + 2}).")
    out.append(f"- **Saturation:** offered rate first exceeded that capacity in minute {sat} "
               f"({B[sat]['off'] * 60:,} /hr offered)." if sat is not None else "- **Saturation:** offered rate never exceeded measured capacity — the ramp did not reach the limit; rerun with a higher end rate.")
    out.append(f"- **R1 breach (POST p95 > 60 s):** minute {r1}, at {B[r1]['off'] * 60:,} /hr offered." if r1 is not None else "- **R1 breach (POST p95 > 60 s):** not reached.")
    out.append(f"- **Error onset (≥ 1% POST errors):** minute {eon}, at {B[eon]['off'] * 60:,} /hr offered." if eon is not None else "- **Error onset (≥ 1% POST errors):** no minute reached 1% errors.")
    text = "\n".join(out) + "\n"

    sys.stdout.reconfigure(encoding="utf-8")
    print(text, end="")
    with open(os.path.join(HERE, "results", base + "_summary.md"), "w", encoding="utf-8") as f:
        f.write(text)
    if a.record:
        with open(a.record, encoding="utf-8") as f:
            rec = f.read()
        b_, e_ = f"<!-- BEGIN {a.label} -->", f"<!-- END {a.label} -->"
        i, j = rec.find(b_), rec.find(e_)
        if i < 0 or j < i:
            sys.exit(f"markers for {a.label} not found in {a.record}")
        rec = rec[: i + len(b_)] + "\n" + text + rec[j:]
        with open(a.record, "w", encoding="utf-8", newline="") as f:
            f.write(rec)
        print(f"updated {a.record} ({a.label})", file=sys.stderr)


if __name__ == "__main__":
    main()
