# Triage service

A small web service that classifies a financial complaint ticket into one of 7 categories by calling an Ollama model, stores the ticket, and lets you search and count tickets. It is a deliberately plain **baseline** for load testing: no cache, no queue, no background workers, no proxy.

How it works and why (architecture, request flows, how to read the log for bottlenecks): [DESIGN.md](DESIGN.md).

## Scope

The service covers the HTTP API (three endpoints), ticket storage (SQLite), request logging, the Docker image and Compose file, and the startup model/digest check. The prompt, generation settings and answer parser are frozen in `evaluation/`; the service holds unchanged copies. Ollama itself and its host settings are outside the service.

## Files

| File | What it is |
| --- | --- |
| `app.py` | HTTP layer: config from env, startup check, the three endpoints, error mapping (422, 502, 504) |
| `storage.py` | SQLite only: create table, insert, search, count |
| `request_log.py` | Request logging only: one JSON line per request |
| `classifier.py`, `eval_config.json`, `prompt_template.md` | Unchanged copies of the frozen files in `evaluation/`, as its README asks. Never edit them here. If the originals change, copy them again; a test fails while a copy differs. `data.py` is not copied |
| `Dockerfile` | Built from this folder alone: copies the three modules and the three classifier files into `/app` |
| `.dockerignore` | Keeps `.venv`, `tests` and Python caches out of the Docker build |
| `requirements.txt` | Pinned runtime packages (this is all the image installs) |
| `requirements-dev.txt` | Pinned test packages, not installed in the image |
| `tests/` | Unit and integration tests. Every test case, and the system checks run by hand, are recorded in [tests/README.md](tests/README.md) |

The service never reads the dataset CSV.

## Endpoints

Create a ticket. The narrative is classified (synchronously), stored and returned with its category. A reply the parser cannot read is stored and returned as `INVALID`. Empty or missing narrative gives 422. If the Ollama call times out the reply is 504, any other Ollama failure gives 502, and nothing is stored.

```bash
curl -X POST localhost:8000/tickets -H "Content-Type: application/json" \
     -d '{"narrative": "My bank froze my account and kept my paycheck."}'
# {"id":1,"category":"Bank account or service","request_id":"..."}
```

Search stored tickets by a substring of the narrative, ignoring case for ASCII letters (`%` and `_` are literal; `café` does not match `CAFÉ`). `q` is required. All matches are returned, ordered by id, with no limit.

```bash
curl "localhost:8000/search?q=paycheck"
# {"query":"paycheck","count":1,"tickets":[{"id":1,"narrative":"...","category":"...","model":"...","created_at":"..."}]}
```

Ticket counts per category. All 7 categories and `INVALID` are always present, zeros included.

```bash
curl localhost:8000/stats
# {"total":1,"by_category":{"Credit reporting":0,...,"INVALID":0}}
```

## Prerequisites

- Docker (Compose v2).
- Ollama running on the host with the four pinned models pulled. Check from the repo root:

  ```bash
  cd evaluation
  python classifier.py --self-test
  ```

## Start

Set `MODEL` to one of the pinned tags in `evaluation/eval_config.json`. Compose refuses to start without it. The service also refuses to start if the model is not pinned, Ollama cannot be reached, the model is not pulled, or its local digest differs from the pin; the reason is the last line printed before `Application startup failed` (see `docker compose logs`).

```bash
# bash
MODEL=qwen2.5:7b docker compose up -d --build
```

```powershell
# PowerShell
$env:MODEL="qwen2.5:7b"; docker compose up -d --build
```

The service listens on `http://localhost:8000`. Compose reads `MODEL` for every command, so `docker compose down` also needs `MODEL` set (any pinned tag).

Other settings (optional): `OLLAMA_URL` (compose sets `http://host.docker.internal:11434`), `DB_PATH` (default `/data/tickets.db`), `LOG_PATH` (default `/logs/requests.jsonl`).

## Switch model

Run one model at a time. Stored tickets belong to the model that classified them, so reset storage when you switch:

```bash
MODEL=qwen2.5:7b docker compose down -v
MODEL=llama3.2:1b docker compose up -d --build
```

In PowerShell, `$env:MODEL` stays set for the session, so `docker compose down -v` works as is; set the new value before `up`.

Then send one warm-up request (the first call loads the model) before measuring.

## Reset storage

```bash
MODEL=qwen2.5:7b docker compose down -v
```

This deletes the SQLite volume `tickets-data`. `docker compose restart` and `docker compose down` (without `-v`) keep the tickets. The log is not touched by either.

Stop or reset the service only after the load generator has finished. `docker compose stop` and `down` wait 10 s and then kill the container; a request still in flight at that point gets no reply and no log line.

## Request log

`logs/requests.jsonl` on the host (mounted at `/logs`): one JSON object per line, one line per request, written for every route including 422, 404, 502, 504 and 500. It is appended to, so it survives restarts and `down -v`. The narrative text is never logged. `ts` is the time the request finished.

| Field | Meaning |
| --- | --- |
| `ts` | UTC time, ISO-8601 with milliseconds |
| `request_id` | `X-Request-ID` header if the client sent one, otherwise generated |
| `run_id` | `X-Run-ID` header, or `null` |
| `method`, `route` | HTTP method and URL path |
| `status` | HTTP status returned |
| `total_ms` | Time inside the service: from the request reaching the logging middleware to the reply being ready. Includes any wait for a free thread, the Ollama call and the insert. Excludes writing the log line and sending the reply (a client sees about 5-20 ms more through Docker Desktop) |
| `model`, `model_digest` | Selected model tag and its pinned digest |
| `ticket_id`, `category`, `raw_output` | `/tickets` success: stored id, label, the model's raw answer |
| `model_ms`, `load_ms`, `prompt_eval_ms`, `eval_ms` | `/tickets`: Ollama call time as the service saw it, then Ollama's own load, prompt and generation times |
| `prompt_tokens`, `output_tokens`, `possibly_truncated` | `/tickets` success: token counts and the classifier's truncation flag |
| `narrative_chars` | `/tickets`: length of the narrative |
| `error` | `/tickets` Ollama failure, or an unhandled exception on any route |
| `query`, `result_count` | `/search` |

On an Ollama failure the `/tickets` line has `error`, `narrative_chars` and `model_ms` (time until the call failed) and no `ticket_id`. If storing the ticket fails after a successful classification, the reply is 500 and the line keeps the model fields plus `error`, with no `ticket_id`.

Request headers (both optional): `X-Request-ID` is echoed back in the response header (and in the JSON reply of a successful `POST /tickets`) and is stored with the ticket; `X-Run-ID` labels a test run and appears only in the log.

**Load tests must send a unique `X-Request-ID` on every request** (in JMeter, for example `${__UUID()}`). A request that times out on the client, or gets a 500, never receives a generated id, so it can only be matched to its log line by an id the client chose. The service does not reject a reused id.

## Baseline behaviour

- Classification is synchronous: the request waits for Ollama and the reply comes back when it finishes.
- One Uvicorn worker process. The endpoints are plain `def`, so they run on the default 40-thread pool. A slow classification does not block `/search` or `/stats` while fewer than 40 classifications are in flight. Once 40 are in flight, every request, including `/search` and `/stats`, waits for a free thread (measured with a stand-in Ollama: with 45 concurrent 8 s classifications, a search waited about 6.5 s; with 20 it took about 5 ms).
- No cache, no queue, no retries, no limit on `/search` results.
- The Ollama call timeout is 300 s (`request_timeout_seconds` in `eval_config.json`). After that the request returns 504.
- `OLLAMA_NUM_PARALLEL` is an environment variable of the Ollama process on the **host**, not of this service. The reported runs used 1 (see [results-record.md](../results-record.md)).
- If the client gives up early, the service does not notice: the Ollama call finishes, the ticket is stored and the log line shows status 200 with the full `total_ms`.
- Each request opens its own SQLite connection (30 s busy timeout).

## Network notes

- A load generator on another machine must reach port 8000 on this host. The service listens on all interfaces, so the host firewall must allow inbound TCP 8000.
- The container reaches Ollama through `host.docker.internal`. On Docker Desktop for Windows this worked while the host service was bound to `127.0.0.1` only (checked with a stand-in server, not real Ollama). On Linux hosts Ollama must listen on a non-loopback address (`OLLAMA_HOST=0.0.0.0`); that was not tested here.

## Tests

The tests need no running service, Ollama or dataset. They run in a throwaway container so nothing is installed on your machine and nothing is written to the repo (the container needs network once, to `pip install`). From the repo root:

```bash
# bash (in Git Bash on Windows, put MSYS_NO_PATHCONV=1 in front of the command)
docker run --rm -e PYTHONDONTWRITEBYTECODE=1 -v "$PWD":/repo -w /repo python:3.12-slim \
  sh -c "pip install -q -r service/requirements-dev.txt && pytest -p no:cacheprovider service/tests -v"
```

```powershell
# PowerShell
docker run --rm -e PYTHONDONTWRITEBYTECODE=1 -v "${PWD}:/repo" -w /repo python:3.12-slim sh -c "pip install -q -r service/requirements-dev.txt && pytest -p no:cacheprovider service/tests -v"
```

**Quicker alternative, without launching Docker:** run the tests in a Python virtual environment. Set it up once from the repo root (checked with Python 3.10):

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r service/requirements-dev.txt
```

Then run the tests whenever you need them (about two seconds):

```powershell
.venv\Scripts\python -m pytest service/tests -v
```

In Git Bash write the path as `.venv/Scripts/python`; on Linux or macOS it is `.venv/bin/python`. `.venv/` is git-ignored. The Docker command runs the tests on Python 3.12, the version the service image uses.

Every test case is listed in [tests/README.md](tests/README.md). In short:

- **Unit tests** (`test_storage.py`, `test_request_log.py`, `test_app_unit.py`) check one module each. `storage` and `request_log` run on temp files, and the logging middleware runs on a bare app with dummy routes; the HTTP layer runs with `classifier.classify`, `classifier.ollama_get` and the storage functions all replaced, so no model, network or real database is touched. The classifier's own parser has its own `--self-test` and is not tested here.
- **Copy check** (`test_classifier_copy.py`) fails if a classifier file in `service/` differs from its original in `evaluation/`.
- **Integration tests** (`test_integration.py`) run the real app, storage, request log and classifier (real prompt and parser) together, with only the Ollama HTTP calls replaced. They check that post, search and stats agree, that failures store nothing, and that every request (200, 404, 405, 422, 500, 502) produces exactly one valid log line with the right ids, real durations and no narrative text.
