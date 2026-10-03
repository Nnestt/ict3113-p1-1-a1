# Integration tests: real app, real storage on a temp db, real request_log on a temp file and the real
# classifier (prompt building and parsing). Only the Ollama HTTP boundary is replaced.

import sqlite3
import time
import urllib.error

import pytest
from fastapi.testclient import TestClient

import classifier
import storage

SECRET = "ZX-SECRET-NARRATIVE-9431"
REQUIRED = ["ts", "request_id", "run_id", "method", "route", "status", "total_ms", "model", "model_digest"]


# Ollama stand-in at the HTTP boundary: the reply text, delay and error can be changed per test
@pytest.fixture
def ollama(monkeypatch):
    state = {"reply": "Credit card", "error": None, "delay": 0, "prompts": []}

    def fake_post(path, payload, timeout=None):
        if state["error"]:
            raise state["error"]
        state["prompts"].append(payload["prompt"])
        time.sleep(state["delay"])
        return {"response": state["reply"], "load_duration": 1_000_000, "prompt_eval_duration": 2_000_000,
                "eval_duration": 3_000_000, "prompt_eval_count": 50, "eval_count": 3}

    def fake_get(path, timeout=30):
        assert path == "/api/tags"
        return {"models": [{"name": m, "digest": d} for m, d in classifier.MODELS.items()]}

    monkeypatch.setattr(classifier, "ollama_post", fake_post)
    monkeypatch.setattr(classifier, "ollama_get", fake_get)
    return state


@pytest.fixture
def api(app_mod, ollama, db_path):
    storage.init_db(db_path)
    return TestClient(app_mod.app)


def post(api, narrative, **headers):
    return api.post("/tickets", json={"narrative": narrative}, headers=headers)


def test_post_then_search_then_stats_agree(api):
    created = post(api, "My bank froze my account").json()

    found = api.get("/search", params={"q": "BANK"}).json()
    stats = api.get("/stats").json()

    assert created["category"] == "Credit card"
    assert found["count"] == 1 and found["tickets"][0]["id"] == created["id"]
    assert found["tickets"][0]["narrative"] == "My bank froze my account"
    assert stats["total"] == 1 and stats["by_category"]["Credit card"] == 1


def test_real_prompt_is_built_from_the_narrative(api, ollama):
    post(api, "unique-words-here")

    assert "unique-words-here" in ollama["prompts"][0]


def test_unparseable_answer_is_stored_and_counted_as_invalid(api, ollama):
    ollama["reply"] = "I cannot determine this."

    created = post(api, "odd ticket").json()

    assert created["category"] == "INVALID"
    assert api.get("/search", params={"q": "odd"}).json()["tickets"][0]["category"] == "INVALID"
    assert api.get("/stats").json()["by_category"]["INVALID"] == 1


def test_ollama_failure_returns_502_and_stores_nothing(api, ollama, db_path):
    ollama["error"] = urllib.error.URLError(ConnectionRefusedError(111, "refused"))

    response = post(api, "will fail")

    assert response.status_code == 502
    assert api.get("/stats").json()["total"] == 0
    assert sqlite3.connect(db_path).execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 0


def test_ollama_timeout_returns_504(api, ollama):
    ollama["error"] = TimeoutError("timed out")

    assert post(api, "slow").status_code == 504


def test_request_and_run_ids_are_echoed_and_logged(api, read_log):
    response = post(api, "hello", **{"X-Request-ID": "my-req-1", "X-Run-ID": "run-A"})

    assert response.headers["X-Request-ID"] == "my-req-1" and response.json()["request_id"] == "my-req-1"
    line = read_log()[0]
    assert line["request_id"] == "my-req-1" and line["run_id"] == "run-A"


def test_ids_are_generated_when_headers_are_absent(api, read_log):
    first, second = post(api, "one"), post(api, "two")

    ids = [first.json()["request_id"], second.json()["request_id"]]
    assert ids[0] != ids[1] and all(len(i) == 32 for i in ids)
    assert [line["request_id"] for line in read_log()] == ids
    assert read_log()[0]["run_id"] is None


def test_every_request_gets_exactly_one_valid_log_line(api, ollama, read_log):
    sent = []
    sent.append((post(api, "fine ticket").status_code, "/tickets"))
    sent.append((api.post("/tickets", json={"narrative": "   "}).status_code, "/tickets"))
    sent.append((api.get("/search").status_code, "/search"))
    sent.append((api.get("/search", params={"q": "fine"}).status_code, "/search"))
    sent.append((api.get("/stats").status_code, "/stats"))
    sent.append((api.get("/no-such-route").status_code, "/no-such-route"))
    sent.append((api.get("/tickets").status_code, "/tickets"))
    ollama["error"] = urllib.error.URLError(ConnectionRefusedError(111, "refused"))
    sent.append((post(api, "fails").status_code, "/tickets"))

    lines = read_log()

    assert [(line["status"], line["route"]) for line in lines] == sent
    assert [s for s, _ in sent] == [200, 422, 422, 200, 200, 404, 405, 502]
    for line in lines:
        assert all(field in line for field in REQUIRED)
        assert line["model"] == "qwen2.5:1.5b" and line["model_digest"] == classifier.MODELS["qwen2.5:1.5b"]
        assert line["total_ms"] >= 0


def test_ticket_log_line_has_the_classifier_fields(api, read_log):
    created = post(api, SECRET).json()

    line = read_log()[0]
    assert line["ticket_id"] == created["id"] and line["category"] == "Credit card"
    assert line["raw_output"] == "Credit card" and line["narrative_chars"] == len(SECRET)
    for field in ["model_ms", "load_ms", "prompt_eval_ms", "eval_ms", "prompt_tokens", "output_tokens",
                  "possibly_truncated"]:
        assert field in line
    assert line["model_ms"] <= line["total_ms"]


def test_total_ms_and_model_ms_are_real_durations(api, ollama, read_log):
    ollama["delay"] = 0.05

    post(api, "slow model")

    line = read_log()[0]
    assert 50 <= line["model_ms"] <= line["total_ms"]


def test_invalid_answer_keeps_the_raw_output_in_the_log(api, ollama, read_log):
    ollama["reply"] = "I cannot determine this."

    post(api, "odd ticket")

    line = read_log()[0]
    assert line["category"] == "INVALID" and line["raw_output"] == "I cannot determine this."


def test_search_log_line_has_query_and_result_count(api, read_log):
    post(api, "alpha beta")
    api.get("/search", params={"q": "beta"})

    line = read_log()[1]
    assert line["query"] == "beta" and line["result_count"] == 1


def test_failed_ollama_call_is_logged_with_error_and_no_ticket_id(api, ollama, read_log):
    ollama["error"] = urllib.error.URLError(ConnectionRefusedError(111, "refused"))

    post(api, "will fail")

    line = read_log()[0]
    assert line["status"] == 502 and "ConnectionRefusedError" in line["error"]
    assert line["narrative_chars"] == 9 and "model_ms" in line and "ticket_id" not in line


def test_storage_failure_after_classification_is_a_500_that_keeps_the_model_fields(app_mod, ollama, monkeypatch,
                                                                                   read_log):
    def failing_insert(*args):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(storage, "insert_ticket", failing_insert)
    api = TestClient(app_mod.app, raise_server_exceptions=False)

    response = post(api, "classified but not stored")

    assert response.status_code == 500
    (line,) = read_log()
    assert line["status"] == 500 and "database is locked" in line["error"]
    assert line["category"] == "Credit card" and "model_ms" in line and "ticket_id" not in line


def test_narrative_text_never_appears_in_the_log(api, ollama, log_path):
    post(api, SECRET)
    ollama["error"] = urllib.error.URLError(ConnectionRefusedError(111, "refused"))
    post(api, SECRET)
    api.post("/tickets", json={"narrative": SECRET, "extra": 1})

    assert SECRET not in open(log_path, encoding="utf-8").read()


def test_request_id_stored_with_the_ticket_equals_the_logged_one(api, read_log, db_path):
    post(api, "link me", **{"X-Request-ID": "link-1"})

    stored = sqlite3.connect(db_path).execute("SELECT request_id FROM tickets").fetchone()[0]
    assert stored == "link-1" == read_log()[0]["request_id"]


def test_startup_check_passes_and_creates_the_table(app_mod, ollama, db_path):
    with TestClient(app_mod.app) as started:
        assert started.get("/stats").json()["total"] == 0
