# AGENTS.md

Instructions for AI coding agents working in this repository.

## What this repo is

ICT3113 Assignment 1, Team 1. We build a plain baseline ticket triage service, measure it, and recommend a model to a client. The client has CPU-only servers and allows no public model API. The service classifies financial complaint tickets into seven categories with a local Ollama model.

The grade depends on evidence. Every number we report must trace back to a log line or a JMeter result file in this repo, and the commit history must show that the golden set and the predictions were committed before any measurement.

## Layout and owners

| Path | Contents | Owner |
| --- | --- | --- |
| `golden_set/` | 175 labelled tickets, labelling protocol, both label sheets, resolutions, agreement statistic | Ernest |
| `evaluation/` | Pinned models, the classification prompt, generation settings, answer parser, smoke tests | Izzul |
| `service/` | The triage service: HTTP API, SQLite storage, request logging, Docker image, tests | YP |
| `docker-compose.yml`, `logs/` | How the service is run, and its request log | YP |
| `performance-requirements.md`, `prediction-record.md` | Requirements and the frozen predictions | Mikhail |
| JMeter test plans and `.jtl` result files | Load and stress tests | Lutfi |

Read the README in a folder before changing anything in it. `service/DESIGN.md` explains how the service works and where a request spends time.

## Do not change

- **`golden_set/`.** The label sheets, final labels and agreement statistic are frozen.
- **`prediction-record.md`.** The predictions cannot be revised after measurement started.
- **`evaluation/prompt_template.md`, `evaluation/eval_config.json`, and the parser and classify logic in `evaluation/classifier.py`.** Every accuracy and load result depends on them.
- **`service/classifier.py`, `service/eval_config.json`, `service/prompt_template.md`.** These are unchanged copies of the files in `evaluation/`. Never edit the copies. If the originals change, copy them again. A test fails while a copy differs.
- **Log lines and `.jtl` files from measured runs.** Never edit, trim or delete them.
- **Commit history.** Never rebase, amend or force-push commits that are already shared. The history is the proof of what was frozen when.

If a task seems to need one of these changes, stop and ask the person you are working for.

## Rules for the service

- It is a baseline to be measured, not tuned. Do not add caching, a queue, retries, background workers, extra Uvicorn workers, a reverse proxy, pagination or any other optimisation. That work belongs to Assignment 2.
- Classification stays synchronous: `POST /tickets` returns only after the model has answered.
- The service starts empty and never reads the dataset CSV. Tickets enter only through `POST /tickets`.
- Every request must produce exactly one line in the request log, on every route and every status.
- Model inference runs on local Ollama, CPU only, with the pinned models. Never call a public model API.
- Keep the design simple: the simplest implementation that is complete, with one job per module. See the scope table in `service/README.md` for what the service owns.

## Rules for data and evidence

- Golden-set tickets go through a model only in the accuracy test, through `POST /tickets`. Use non-golden team rows (1000 to 1999) for anything else.
- `golden_set/ict3113_tickets.csv` is git-ignored. Do not commit it or copy complaint text into other files.
- Never invent, estimate or round a measurement into a result. If a number is not in a log or a `.jtl` file, it does not exist.
- Never leave test traffic from a fake or stand-in model in `logs/`. Delete such a log file before finishing.

## Commands

Run from the repo root.

Run the service tests (no Ollama needed; in Git Bash on Windows put `MSYS_NO_PATHCONV=1` in front):

```bash
docker run --rm -e PYTHONDONTWRITEBYTECODE=1 -v "$PWD":/repo -w /repo python:3.12-slim \
  sh -c "pip install -q -r service/requirements-dev.txt && pytest -p no:cacheprovider service/tests -v"
```

Check the parser and the pinned model digests (needs Ollama running with the models pulled):

```bash
cd evaluation
python classifier.py --self-test
```

Start the service with one pinned model, and reset its storage:

```bash
MODEL=qwen2.5:7b docker compose up -d --build
MODEL=qwen2.5:7b docker compose down -v
```

## Code and test conventions

- Python, standard library where it is enough. The service adds only FastAPI and Uvicorn, pinned in `service/requirements.txt`.
- Match the existing style: a short header comment at the top of each file, one `#` comment above a function that needs it, no docstrings, lines up to about 120 characters.
- Unit tests check one module and replace every external dependency with a stub. Integration tests run the real modules together and stub only the Ollama HTTP calls. Tests write only to temporary directories.
- Run the tests before saying a change works, and report failures as they are.

## Git

- Commit only when asked. Use short messages in the existing style: `feat: ...`, `fix: ...`, `docs: ...`, `chore: ...`.
- Do not push unless asked.
