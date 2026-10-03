# Request logging for the triage service: one JSON object per line for every request.
# The log file is the measurement evidence, so it is written for failures and unknown routes too.
# Knows nothing about SQLite or the classifier.

import json
import time
import uuid
from datetime import datetime, timezone


# Appends one record as a single JSON line (json escapes newlines and quotes, so one record is one line)
def write_log_line(log_path, record):
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# The fields every line has, followed by whatever the endpoint put in request.state.extra
def build_record(request, status, started, model, model_digest):
    return {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "request_id": request.state.request_id,
        "run_id": request.headers.get("X-Run-ID"),
        "method": request.method,
        "route": request.url.path,
        "status": status,
        "total_ms": round((time.perf_counter() - started) * 1000, 1),
        "model": model,
        "model_digest": model_digest,
        **request.state.extra,
    }


# Installs the logging middleware. get_config() returns (log_path, model, model_digest) when a request ends.
def add_request_logging(app, get_config):
    @app.middleware("http")
    async def log_request(request, call_next):
        started = time.perf_counter()
        request.state.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.extra = {}  # the endpoint adds its own fields here
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request.state.request_id
            return response
        except Exception as exc:
            request.state.extra["error"] = repr(exc)
            raise
        finally:
            log_path, model, model_digest = get_config()
            write_log_line(log_path, build_record(request, status, started, model, model_digest))
