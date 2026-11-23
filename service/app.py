# Ticket triage service: HTTP layer. Classifies a complaint with Ollama and stores it in SQLite.
# Deliberately plain baseline: synchronous classification, no cache, no queue, one process.
# Storage is in storage.py, request logging in request_log.py and model routing (single model, or the
# Assignment 2 small->large cascade) in cascade.py. classifier.py, eval_config.json and prompt_template.md
# are unchanged copies of the frozen files in evaluation/ (do not edit them here).
#
# Run (see service/README.md):
#   MODEL=qwen2.5:7b docker compose up -d --build
#   TRIAGE_MODE=cascade SMALL_MODEL=qwen2.5:1.5b LARGE_MODEL=qwen2.5:7b CASCADE_SETTING=S1 docker compose up -d --build
# Env vars: TRIAGE_MODE (single|cascade, default single), MODEL (single), SMALL_MODEL, LARGE_MODEL and
# CASCADE_SETTING (cascade), TRIAGE_CONFIG (config name, logged), OLLAMA_URL, DB_PATH, LOG_PATH.
# Contract for the env vars and log fields: a2/CONTRACTS.md.

import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

os.environ.setdefault("OLLAMA_URL", "http://host.docker.internal:11434")
import cascade  # noqa: E402
import classifier  # noqa: E402  (reads OLLAMA_URL when imported)
import request_log  # noqa: E402
import storage  # noqa: E402

MODE = os.environ.get("TRIAGE_MODE", "single")
MODEL = os.environ.get("MODEL", "")
SMALL_MODEL = os.environ.get("SMALL_MODEL", "")
LARGE_MODEL = os.environ.get("LARGE_MODEL", "")
SETTING = os.environ.get("CASCADE_SETTING", "")
CONFIG_NAME = os.environ.get("TRIAGE_CONFIG", "")
DB_PATH = os.environ.get("DB_PATH", "/data/tickets.db")
LOG_PATH = os.environ.get("LOG_PATH", "/logs/requests.jsonl")
ACCEPT = frozenset()  # cascade accept list, loaded at startup from cascade_config.json


# Every model the current configuration calls
def configured_models():
    return [SMALL_MODEL, LARGE_MODEL] if MODE == "cascade" else [MODEL]


# Model fields for log lines that are not a classified ticket (the POST line overrides them with the final model)
def log_model():
    if MODE == "cascade":
        return f"{SMALL_MODEL}>{LARGE_MODEL}", None
    return MODEL, classifier.MODELS.get(MODEL)


# Raises ValueError if the mode or cascade setting is invalid; returns the accept list (empty in single mode)
def check_config(settings_loader=lambda: cascade.load_settings(classifier.LABELS)):
    if MODE not in ("single", "cascade"):
        raise ValueError(f"TRIAGE_MODE={MODE!r} must be single or cascade")
    if MODE == "single":
        return frozenset()
    settings = settings_loader()
    if SETTING not in settings:
        raise ValueError(f"CASCADE_SETTING={SETTING!r} is not one of {', '.join(sorted(settings))}")
    return settings[SETTING]


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


# Fails fast with one clear line if the configuration or any model check fails, then creates the table
@asynccontextmanager
async def lifespan(app):
    global ACCEPT
    try:
        ACCEPT = check_config()
        for model in configured_models():
            check_model(model, classifier.MODELS, lambda: classifier.ollama_get("/api/tags"))
    except ValueError as exc:
        raise SystemExit(f"STARTUP ERROR: {exc}") from None
    storage.init_db(DB_PATH)
    yield


app = FastAPI(title="Ticket triage service", lifespan=lifespan)
request_log.add_request_logging(app, lambda: (LOG_PATH, *log_model()))


# Classifies the narrative (blocking calls to Ollama: one model, or the cascade), stores the ticket and
# returns its category. The caller cannot tell which model answered; the log records it.
@app.post("/tickets")
def create_ticket(body: TicketIn, request: Request):
    extra = request.state.extra
    extra["narrative_chars"] = len(body.narrative)
    extra["config"] = CONFIG_NAME
    started = time.perf_counter()
    try:
        label, final_model = cascade.route(
            body.narrative, extra, MODE, lambda n, m: classifier.classify(n, m), classifier.INVALID,
            model=MODEL, small=SMALL_MODEL, large=LARGE_MODEL, accept=ACCEPT)
    except Exception as exc:
        extra["error"] = repr(exc)
        extra["model_ms"] = round((time.perf_counter() - started) * 1000, 1)
        timed_out = isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError)
        raise HTTPException(504 if timed_out else 502, "Ollama call timed out" if timed_out else "Ollama call failed")
    # logged before the insert so a storage failure still leaves the model's result and timings in the log;
    # model/model_digest override the defaults so each line names the model that produced the category
    extra.update({"category": label, "final_model": final_model, "model": final_model,
                  "model_digest": classifier.MODELS.get(final_model)})
    ticket_id = storage.insert_ticket(DB_PATH, body.narrative, label, final_model, request.state.request_id)
    extra["ticket_id"] = ticket_id
    return {"id": ticket_id, "category": label, "request_id": request.state.request_id}


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
