# Ticket triage service: HTTP layer. Classifies a complaint with one Ollama model and stores it in SQLite.
# Deliberately plain baseline: synchronous classification, no cache, no queue, one process.
# Storage is in storage.py, request logging in request_log.py, the classifier is evaluation/classifier.py.
# service/Dockerfile copies all of them flat into /app.
#
# Run (see service/README.md):  MODEL=qwen2.5:7b docker compose up -d --build
# Env vars: MODEL (required), OLLAMA_URL, DB_PATH, LOG_PATH

import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

os.environ.setdefault("OLLAMA_URL", "http://host.docker.internal:11434")
import classifier  # noqa: E402  (reads OLLAMA_URL when imported)
import request_log  # noqa: E402
import storage  # noqa: E402

MODEL = os.environ.get("MODEL", "")
DB_PATH = os.environ.get("DB_PATH", "/data/tickets.db")
LOG_PATH = os.environ.get("LOG_PATH", "/logs/requests.jsonl")


class TicketIn(BaseModel):
    narrative: str = Field(pattern=r"\S")  # at least one non-whitespace character


# Raises ValueError with a clear message if the model is not pinned, Ollama is unreachable,
# the model is not pulled, or its local digest differs from the pin. get_tags returns the /api/tags reply.
def check_model(model, pins, get_tags):
    if model not in pins:
        raise ValueError(f"MODEL={model!r} is not a pinned model, use one of: {', '.join(pins)}")
    try:
        local = {m["name"]: m["digest"] for m in get_tags()["models"]}
    except Exception as exc:
        raise ValueError(f"cannot reach Ollama at {classifier.OLLAMA_URL}: {exc!r}") from None
    if model not in local:
        raise ValueError(f"{model} is not pulled in Ollama (run: ollama pull {model})")
    if local[model] != pins[model]:
        raise ValueError(f"{model} local digest {local[model]} != pinned {pins[model]}")


# Fails fast with one clear line if the model check fails, then creates the table
@asynccontextmanager
async def lifespan(app):
    try:
        check_model(MODEL, classifier.MODELS, lambda: classifier.ollama_get("/api/tags"))
    except ValueError as exc:
        raise SystemExit(f"STARTUP ERROR: {exc}") from None
    storage.init_db(DB_PATH)
    yield


app = FastAPI(title="Ticket triage service", lifespan=lifespan)
request_log.add_request_logging(app, lambda: (LOG_PATH, MODEL, classifier.MODELS.get(MODEL)))


# Classifies the narrative (blocking call to Ollama), stores the ticket and returns its category
@app.post("/tickets")
def create_ticket(body: TicketIn, request: Request):
    extra = request.state.extra
    extra["narrative_chars"] = len(body.narrative)
    started = time.perf_counter()
    try:
        result = classifier.classify(body.narrative, MODEL)
    except Exception as exc:
        extra["error"] = repr(exc)
        extra["model_ms"] = round((time.perf_counter() - started) * 1000, 1)
        timed_out = isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError)
        raise HTTPException(504 if timed_out else 502, "Ollama call timed out" if timed_out else "Ollama call failed")
    ticket_id = storage.insert_ticket(DB_PATH, body.narrative, result["label"], MODEL, request.state.request_id)
    extra.update({
        "ticket_id": ticket_id,
        "category": result["label"],
        "raw_output": result["raw_output"],
        "model_ms": result["wall_ms"],
        "load_ms": result["load_ms"],
        "prompt_eval_ms": result["prompt_eval_ms"],
        "eval_ms": result["eval_ms"],
        "prompt_tokens": result["prompt_tokens"],
        "output_tokens": result["output_tokens"],
        "possibly_truncated": result["possibly_truncated"],
    })
    return {"id": ticket_id, "category": result["label"], "request_id": request.state.request_id}


# Returns every ticket whose narrative contains q (case-insensitive, literal match), no limit
@app.get("/search")
def search(request: Request, q: str = Query(min_length=1)):
    tickets = storage.search_tickets(DB_PATH, q)
    request.state.extra.update({"query": q, "result_count": len(tickets)})
    return {"query": q, "count": len(tickets), "tickets": tickets}


# Ticket counts per category, always all eight keys
@app.get("/stats")
def stats():
    by_category = storage.count_by_category(DB_PATH, classifier.LABELS + [classifier.INVALID])
    return {"total": sum(by_category.values()), "by_category": by_category}
