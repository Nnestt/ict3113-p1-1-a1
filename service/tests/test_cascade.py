# Tests for the Assignment 2 cascade (cascade.py and its use in POST /tickets). classifier.classify is
# replaced by a fake that answers per model, so no Ollama is needed; storage and the log are real temp files.

import asyncio
import json
import urllib.error
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import cascade
import classifier
import storage

SMALL, LARGE = "qwen2.5:1.5b", "qwen2.5:7b"
ACCEPT = frozenset({"Credit reporting", "Mortgage"})


# App in cascade mode; answers[model] is the label (or an exception) that model returns
@pytest.fixture
def cascade_app(app_mod, monkeypatch, classify_result, db_path):
    monkeypatch.setattr(app_mod, "MODE", "cascade")
    monkeypatch.setattr(app_mod, "SMALL_MODEL", SMALL)
    monkeypatch.setattr(app_mod, "LARGE_MODEL", LARGE)
    monkeypatch.setattr(app_mod, "SETTING", "S1")
    monkeypatch.setattr(app_mod, "CONFIG_NAME", "cascade-S1")
    monkeypatch.setattr(app_mod, "ACCEPT", ACCEPT)
    state = SimpleNamespace(answers={SMALL: "Credit reporting", LARGE: "Debt collection"}, calls=[])

    def fake_classify(narrative, model):
        state.calls.append(model)
        answer = state.answers[model]
        if isinstance(answer, Exception):
            raise answer
        result = classify_result(answer)
        result["wall_ms"] = 100.0 if model == SMALL else 400.0
        return result

    monkeypatch.setattr(app_mod.classifier, "classify", fake_classify)
    storage.init_db(db_path)
    state.client = TestClient(app_mod.app)
    return state


def post(state, narrative="My complaint"):
    return state.client.post("/tickets", json={"narrative": narrative})


def stored_models(db_path):
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        return [row[0] for row in conn.execute("SELECT model FROM tickets ORDER BY id")]


def test_accepted_label_is_answered_by_the_small_model_only(cascade_app, read_log, db_path):
    resp = post(cascade_app)

    assert resp.status_code == 200 and resp.json()["category"] == "Credit reporting"
    assert cascade_app.calls == [SMALL]
    line = read_log()[-1]
    assert line["escalated"] is False and line["escalation_reason"] is None
    assert line["model"] == line["final_model"] == SMALL
    assert line["model_digest"] == classifier.MODELS[SMALL]
    assert line["small_label"] == "Credit reporting" and line["large_label"] is None
    assert line["model_ms"] == 100.0 and line["config"] == "cascade-S1"
    assert stored_models(db_path) == [SMALL]


def test_label_outside_the_accept_list_is_escalated_and_the_large_label_is_final(cascade_app, read_log, db_path):
    cascade_app.answers[SMALL] = "Credit card"

    resp = post(cascade_app)

    assert resp.json()["category"] == "Debt collection"
    assert cascade_app.calls == [SMALL, LARGE]
    line = read_log()[-1]
    assert line["escalated"] is True and line["escalation_reason"] == cascade.NOT_ACCEPTED
    assert line["model"] == line["final_model"] == LARGE
    assert line["model_digest"] == classifier.MODELS[LARGE]
    assert line["small_label"] == "Credit card" and line["large_label"] == "Debt collection"
    assert line["small_ms"] == 100.0 and line["large_ms"] == 400.0 and line["model_ms"] == 500.0
    assert line["category"] == "Debt collection"
    assert stored_models(db_path) == [LARGE]


def test_invalid_small_output_is_escalated(cascade_app, read_log):
    cascade_app.answers[SMALL] = classifier.INVALID

    resp = post(cascade_app)

    assert resp.json()["category"] == "Debt collection"
    assert read_log()[-1]["escalation_reason"] == cascade.INVALID_OUTPUT


def test_small_model_error_is_escalated_and_logged(cascade_app, read_log):
    cascade_app.answers[SMALL] = urllib.error.URLError(ConnectionRefusedError())

    resp = post(cascade_app)

    assert resp.status_code == 200 and resp.json()["category"] == "Debt collection"
    line = read_log()[-1]
    assert line["escalated"] is True and line["escalation_reason"] == cascade.SMALL_ERROR
    assert "URLError" in line["small_error"] and line["small_label"] is None
    assert line["model_ms"] == 400.0


def test_large_model_error_gives_502_keeps_the_small_stage_and_stores_nothing(cascade_app, read_log, db_path):
    cascade_app.answers[SMALL] = "Credit card"
    cascade_app.answers[LARGE] = urllib.error.URLError(ConnectionRefusedError())

    resp = post(cascade_app)

    assert resp.status_code == 502
    line = read_log()[-1]
    assert line["status"] == 502 and "error" in line and "ticket_id" not in line
    assert line["escalated"] is True and line["small_label"] == "Credit card"
    assert stored_models(db_path) == []


def test_large_model_timeout_gives_504(cascade_app):
    cascade_app.answers[SMALL] = "Credit card"
    cascade_app.answers[LARGE] = TimeoutError("timed out")

    assert post(cascade_app).status_code == 504


def test_response_has_the_same_keys_in_single_and_cascade_mode(cascade_app, app_mod, monkeypatch):
    cascade_keys = set(post(cascade_app).json())
    monkeypatch.setattr(app_mod, "MODE", "single")
    monkeypatch.setattr(app_mod, "MODEL", LARGE)

    single_keys = set(post(cascade_app).json())

    assert cascade_keys == single_keys == {"id", "category", "request_id"}


def test_single_mode_logs_the_same_fields_with_no_escalation(cascade_app, app_mod, monkeypatch, read_log):
    monkeypatch.setattr(app_mod, "MODE", "single")
    monkeypatch.setattr(app_mod, "MODEL", LARGE)

    post(cascade_app)

    line = read_log()[-1]
    assert cascade_app.calls == [LARGE]
    assert line["escalated"] is False and line["escalation_reason"] is None
    assert line["model"] == line["final_model"] == LARGE and line["small_label"] is None


def test_non_ticket_lines_name_the_model_pair_in_cascade_mode(cascade_app, read_log):
    cascade_app.client.get("/stats")

    line = read_log()[-1]
    assert line["model"] == f"{SMALL}>{LARGE}" and line["model_digest"] is None


def test_startup_checks_every_model_in_the_cascade(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "MODE", "cascade")
    monkeypatch.setattr(app_mod, "SMALL_MODEL", SMALL)
    monkeypatch.setattr(app_mod, "LARGE_MODEL", LARGE)
    monkeypatch.setattr(app_mod, "SETTING", "S1")
    monkeypatch.setattr(app_mod.storage, "init_db", lambda path: None)
    only_small = {"models": [{"name": SMALL, "digest": classifier.MODELS[SMALL]}]}
    monkeypatch.setattr(app_mod.classifier, "ollama_get", lambda path: only_small)

    async def start():
        async with app_mod.lifespan(app_mod.app):
            pass

    with pytest.raises(SystemExit, match=f"STARTUP ERROR: {LARGE} is not pulled"):
        asyncio.run(start())


def test_startup_loads_the_accept_list_for_the_setting(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "MODE", "cascade")
    monkeypatch.setattr(app_mod, "SMALL_MODEL", SMALL)
    monkeypatch.setattr(app_mod, "LARGE_MODEL", LARGE)
    monkeypatch.setattr(app_mod, "SETTING", "S2")
    monkeypatch.setattr(app_mod.storage, "init_db", lambda path: None)
    monkeypatch.setattr(app_mod.classifier, "ollama_get", lambda path: {
        "models": [{"name": m, "digest": d} for m, d in classifier.MODELS.items()]})

    async def start():
        async with app_mod.lifespan(app_mod.app):
            return app_mod.ACCEPT

    settings = cascade.load_settings(classifier.LABELS)
    assert asyncio.run(start()) == settings["S2"]


def test_unknown_setting_is_a_startup_error(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "MODE", "cascade")
    monkeypatch.setattr(app_mod, "SETTING", "S9")

    with pytest.raises(ValueError, match="CASCADE_SETTING='S9'"):
        app_mod.check_config()


def test_unknown_mode_is_a_startup_error(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "MODE", "both")

    with pytest.raises(ValueError, match="TRIAGE_MODE='both'"):
        app_mod.check_config()


def test_committed_cascade_config_is_valid_and_names_the_a2_pair():
    config = json.loads(cascade.CONFIG_PATH.read_text(encoding="utf-8"))
    settings = cascade.load_settings(classifier.LABELS)

    assert config["small_model"] == SMALL and config["large_model"] == LARGE
    assert set(settings) == {"S1", "S2"} and all(settings.values())


def test_an_accept_label_that_is_not_a_category_is_rejected(tmp_path):
    bad = tmp_path / "cascade_config.json"
    bad.write_text(json.dumps({"settings": {"S1": {"accept": ["Credit reporting", "Crypto"]}}}), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown accept labels \\['Crypto'\\]"):
        cascade.load_settings(classifier.LABELS, bad)
