# Unit tests for app.py (the HTTP layer). classifier.classify, classifier.ollama_get and the storage
# functions are all replaced, so no model, network or real database is touched.

import asyncio
import urllib.error
from types import SimpleNamespace

import pytest

import app

PINS = {"qwen2.5:1.5b": "digest-a", "qwen2.5:7b": "digest-b"}


def tags(*pairs):
    return lambda: {"models": [{"name": name, "digest": digest} for name, digest in pairs]}


# Replaces classify and the storage functions; calls records what the app asked of them
@pytest.fixture
def stubbed(app_mod, monkeypatch, classify_result):
    calls = {"classify": [], "insert": []}
    state = {"result": classify_result(), "error": None}

    def fake_classify(narrative, model):
        calls["classify"].append((narrative, model))
        if state["error"]:
            raise state["error"]
        return state["result"]

    def fake_insert(db_path, narrative, category, model, request_id):
        calls["insert"].append((narrative, category, model, request_id))
        return 7

    monkeypatch.setattr(app_mod.classifier, "classify", fake_classify)
    monkeypatch.setattr(app_mod.storage, "insert_ticket", fake_insert)
    return SimpleNamespace(classify=calls["classify"], insert=calls["insert"], state=state)


def post(client, narrative):
    return client.post("/tickets", json={"narrative": narrative})


def test_post_tickets_returns_id_category_and_request_id(client, stubbed):
    response = post(client, "my card was charged twice")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 7 and body["category"] == "Credit card"
    assert body["request_id"] == response.headers["X-Request-ID"]


def test_post_tickets_classifies_once_and_inserts_the_label_once(client, stubbed):
    response = post(client, "my card was charged twice")

    assert stubbed.classify == [("my card was charged twice", "qwen2.5:1.5b")]
    assert len(stubbed.insert) == 1
    narrative, category, model, request_id = stubbed.insert[0]
    assert (narrative, category, model) == ("my card was charged twice", "Credit card", "qwen2.5:1.5b")
    assert request_id == response.json()["request_id"]


def test_invalid_label_is_stored_and_returned(client, stubbed, classify_result):
    stubbed.state["result"] = classify_result("INVALID", "I cannot tell")

    response = post(client, "some ticket")

    assert response.status_code == 200 and response.json()["category"] == "INVALID"
    assert stubbed.insert[0][1] == "INVALID"


def test_connection_error_gives_502_and_nothing_is_stored(client, stubbed):
    stubbed.state["error"] = urllib.error.URLError(ConnectionRefusedError(111, "refused"))

    response = post(client, "some ticket")

    assert response.status_code == 502
    assert stubbed.insert == []


def test_read_timeout_gives_504_and_nothing_is_stored(client, stubbed):
    stubbed.state["error"] = TimeoutError("timed out")

    response = post(client, "some ticket")

    assert response.status_code == 504
    assert stubbed.insert == []


def test_connect_timeout_wrapped_in_urlerror_gives_504(client, stubbed):
    stubbed.state["error"] = urllib.error.URLError(TimeoutError("timed out"))

    assert post(client, "some ticket").status_code == 504


@pytest.mark.parametrize("body", [{"narrative": ""}, {"narrative": "  \n\t "}, {}, {"narrative": 5}])
def test_bad_narrative_gives_422_and_classify_is_not_called(client, stubbed, body):
    response = client.post("/tickets", json=body)

    assert response.status_code == 422
    assert stubbed.classify == [] and stubbed.insert == []


@pytest.mark.parametrize("url", ["/search", "/search?q="])
def test_search_without_q_gives_422(client, app_mod, monkeypatch, url):
    monkeypatch.setattr(app_mod.storage, "search_tickets", lambda db_path, q: pytest.fail("storage was called"))

    assert client.get(url).status_code == 422


def test_search_returns_what_storage_returns(client, app_mod, monkeypatch):
    rows = [{"id": 1, "narrative": "bank", "category": "Mortgage", "model": "m", "created_at": "t"}]
    seen = []
    monkeypatch.setattr(app_mod.storage, "search_tickets", lambda db_path, q: seen.append(q) or rows)

    response = client.get("/search", params={"q": "ban"})

    assert response.json() == {"query": "ban", "count": 1, "tickets": rows}
    assert seen == ["ban"]


def test_stats_returns_storage_counts_with_all_eight_categories(client, app_mod, monkeypatch):
    def fake_counts(db_path, categories):
        assert len(categories) == 8 and categories[-1] == "INVALID"
        return {c: (2 if c == "Mortgage" else 0) for c in categories}
    monkeypatch.setattr(app_mod.storage, "count_by_category", fake_counts)

    body = client.get("/stats").json()

    assert body["total"] == 2 and body["by_category"]["Mortgage"] == 2 and len(body["by_category"]) == 8


def test_check_model_passes_when_the_digest_matches():
    app.check_model("qwen2.5:1.5b", PINS, tags(("qwen2.5:1.5b", "digest-a"), ("other", "x")))


def test_check_model_only_checks_the_selected_model():
    app.check_model("qwen2.5:1.5b", PINS, tags(("qwen2.5:1.5b", "digest-a")))  # qwen2.5:7b is not pulled: fine


def test_check_model_rejects_an_unknown_model():
    with pytest.raises(ValueError, match="not a pinned model"):
        app.check_model("llama3:8b", PINS, tags())


def test_check_model_rejects_a_model_that_is_not_pulled():
    with pytest.raises(ValueError, match="not pulled"):
        app.check_model("qwen2.5:1.5b", PINS, tags(("qwen2.5:7b", "digest-b")))


def test_check_model_rejects_a_digest_mismatch():
    with pytest.raises(ValueError, match="digest"):
        app.check_model("qwen2.5:1.5b", PINS, tags(("qwen2.5:1.5b", "digest-WRONG")))


def test_check_model_reports_unreachable_ollama():
    def down():
        raise ConnectionRefusedError("refused")

    with pytest.raises(ValueError, match="cannot reach Ollama"):
        app.check_model("qwen2.5:1.5b", PINS, down)


def run_startup(app_mod):
    async def enter():
        async with app_mod.lifespan(app_mod.app):
            pass
    asyncio.run(enter())


def test_startup_exits_with_a_clear_message_when_the_check_fails(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod.classifier, "ollama_get", lambda path: {"models": []})

    with pytest.raises(SystemExit) as exc:
        run_startup(app_mod)

    assert str(exc.value).startswith("STARTUP ERROR:") and "not pulled" in str(exc.value)


def test_startup_creates_the_table_when_the_check_passes(app_mod, monkeypatch):
    digest = app_mod.classifier.MODELS["qwen2.5:1.5b"]
    monkeypatch.setattr(app_mod.classifier, "ollama_get", lambda path: {"models": [
        {"name": "qwen2.5:1.5b", "digest": digest}]})
    inits = []
    monkeypatch.setattr(app_mod.storage, "init_db", inits.append)

    run_startup(app_mod)

    assert inits == [app_mod.DB_PATH]
