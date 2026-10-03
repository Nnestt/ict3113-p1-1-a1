# AGENTS.md

Instructions for AI coding agents working on the triage service. Paths below are relative to the repository root.

## Scope

These instructions cover the triage service only:

- `service/` (this folder): the HTTP API, SQLite storage, request logging, Docker image and tests
- `docker-compose.yml`: how the service is run
- `logs/`: the service's request log

Everything else in the repository belongs to other team members and is out of scope. Do not change it. If a task seems to need a change outside the paths above, stop and ask the person you are working for.

## What the service is

A plain baseline web service for a load-testing assignment. It classifies a financial complaint ticket into one of seven categories by calling a local Ollama model, stores the ticket, and lets a client search tickets and count them per category. It will be measured as it is, so its request log is graded evidence: every reported number must trace back to a log line.

Read `service/README.md` for how to run it and `service/DESIGN.md` for how it works and where a request spends time.

## Do not change

- **`service/classifier.py`, `service/eval_config.json`, `service/prompt_template.md`.** These are unchanged copies of frozen files owned by a teammate. Never edit them. A test fails while a copy differs from its original.
- **Log lines from measured runs in `logs/`.** Never edit, trim or delete them.

## Rules for the service

- It is a baseline to be measured, not tuned. Do not add caching, a queue, retries, background workers, extra Uvicorn workers, a reverse proxy, pagination or any other optimisation.
- Classification stays synchronous: `POST /tickets` returns only after the model has answered.
- The service starts empty and never reads the dataset CSV. Tickets enter only through `POST /tickets`.
- Every request must produce exactly one line in the request log, on every route and every status. The complaint text is never logged.
- Model inference runs on local Ollama with a pinned model. Never call a public model API.
- Keep the design simple: the simplest implementation that is complete, with one job per module (`app.py` for HTTP, `storage.py` for SQLite, `request_log.py` for logging).
- Never leave test traffic from a fake or stand-in model in `logs/`. Delete such a log file before finishing.

## Commands

Run from the repo root.

Run the tests (no Ollama needed; in Git Bash on Windows put `MSYS_NO_PATHCONV=1` in front):

```bash
docker run --rm -e PYTHONDONTWRITEBYTECODE=1 -v "$PWD":/repo -w /repo python:3.12-slim \
  sh -c "pip install -q -r service/requirements-dev.txt && pytest -p no:cacheprovider service/tests -v"
```

Quicker alternative, without launching Docker: a Python virtual environment in `.venv/` (git-ignored). Create it once, then reuse it. On Windows the interpreter is `.venv/Scripts/python`; on Linux or macOS it is `.venv/bin/python`.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r service/requirements-dev.txt
.venv/Scripts/python -m pytest service/tests -v
```

The Docker command runs the tests on Python 3.12, the version the service image uses. Use it for a final check.

Start the service with one pinned model, and reset its storage (needs Ollama running on the host with that model pulled):

```bash
MODEL=qwen2.5:7b docker compose up -d --build
MODEL=qwen2.5:7b docker compose down -v
```

## Code and test conventions

- Python, standard library where it is enough. The only added packages are FastAPI and Uvicorn, pinned in `service/requirements.txt`. Test packages go in `service/requirements-dev.txt` and never into the image.
- Match the existing style: a short header comment at the top of each file, one `#` comment above a function that needs it, no docstrings, lines up to about 120 characters.
- Unit tests check one module and replace every external dependency with a stub. Integration tests run the real modules together and stub only the Ollama HTTP calls. Tests write only to temporary directories.
- Run the tests before saying a change works, and report failures as they are.
- When behaviour changes, update `service/README.md` and `service/DESIGN.md` in the same change.
- When a test is added, changed or removed, update the test case record in `service/tests/README.md` in the same change.

## Git

- Commit only when asked. Use short messages in the existing style: `feat: ...`, `fix: ...`, `docs: ...`, `chore: ...`.
- Do not push unless asked.
