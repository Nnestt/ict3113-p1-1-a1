# Unit tests for request_log.py. The writer and record builder use a fake request object and a temp file.
# The middleware runs on a bare app with two dummy routes: no storage, no classifier, no real server.

import json
import time
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import request_log


def fake_request(headers=None, extra=None):
    return SimpleNamespace(headers=headers or {}, method="POST", url=SimpleNamespace(path="/tickets"),
                           state=SimpleNamespace(request_id="req-1", extra=extra or {}))


def test_write_log_line_appends_one_line_per_call(log_path):
    request_log.write_log_line(log_path, {"a": 1})
    request_log.write_log_line(log_path, {"a": 2})

    lines = open(log_path, encoding="utf-8").read().splitlines()
    assert [json.loads(line) for line in lines] == [{"a": 1}, {"a": 2}]


def test_write_log_line_keeps_non_ascii_text(log_path):
    request_log.write_log_line(log_path, {"text": "café 你好"})

    raw = open(log_path, encoding="utf-8").read()
    assert "café 你好" in raw
    assert json.loads(raw)["text"] == "café 你好"


def test_write_log_line_escapes_newlines_and_quotes(log_path):
    request_log.write_log_line(log_path, {"raw_output": 'line one\nline "two"\r\n'})

    raw = open(log_path, encoding="utf-8").read()
    assert raw.count("\n") == 1 and raw.endswith("\n")
    assert json.loads(raw)["raw_output"] == 'line one\nline "two"\r\n'


def test_build_record_has_all_required_fields():
    started = time.perf_counter()

    record = request_log.build_record(fake_request({"X-Run-ID": "run-9"}), 200, started, "qwen2.5:7b", "digest-1")

    assert list(record)[:9] == ["ts", "request_id", "run_id", "method", "route", "status", "total_ms", "model",
                                "model_digest"]
    assert (record["request_id"], record["run_id"], record["method"], record["route"], record["status"]) == (
        "req-1", "run-9", "POST", "/tickets", 200)
    assert (record["model"], record["model_digest"]) == ("qwen2.5:7b", "digest-1")
    assert record["ts"].endswith("+00:00") and record["total_ms"] >= 0


def test_build_record_run_id_is_null_without_header():
    record = request_log.build_record(fake_request(), 404, time.perf_counter(), "m", "d")

    assert record["run_id"] is None


def test_build_record_appends_the_endpoint_extras():
    request = fake_request(extra={"query": "bank", "result_count": 3})

    record = request_log.build_record(request, 200, time.perf_counter(), "m", "d")

    assert record["query"] == "bank" and record["result_count"] == 3


# A bare app with only the logging middleware installed
def logged_client(log_path):
    app = FastAPI()
    request_log.add_request_logging(app, lambda: (log_path, "m", "d"))

    @app.get("/ok")
    def ok(request: Request):
        request.state.extra["note"] = "from the endpoint"
        time.sleep(0.05)
        return {}

    @app.get("/boom")
    def boom():
        raise RuntimeError("kaput")

    return TestClient(app, raise_server_exceptions=False)


def test_middleware_logs_one_line_with_status_extras_and_duration(log_path, read_log):
    response = logged_client(log_path).get("/ok")

    assert response.status_code == 200
    (line,) = read_log()
    assert (line["status"], line["route"], line["note"]) == (200, "/ok", "from the endpoint")
    assert line["total_ms"] >= 50  # the endpoint slept 50 ms


def test_middleware_uses_and_echoes_the_client_request_id(log_path, read_log):
    response = logged_client(log_path).get("/ok", headers={"X-Request-ID": "abc-1"})

    assert response.headers["X-Request-ID"] == "abc-1"
    assert read_log()[0]["request_id"] == "abc-1"


def test_middleware_generates_a_request_id_when_none_is_sent(log_path, read_log):
    response = logged_client(log_path).get("/ok")

    generated = response.headers["X-Request-ID"]
    assert len(generated) == 32 and read_log()[0]["request_id"] == generated


def test_middleware_logs_an_unhandled_exception_as_500_with_the_error(log_path, read_log):
    response = logged_client(log_path).get("/boom")

    assert response.status_code == 500
    (line,) = read_log()
    assert line["status"] == 500 and "kaput" in line["error"]


def test_middleware_logs_unknown_route_and_wrong_method(log_path, read_log):
    client = logged_client(log_path)

    client.get("/nope")
    client.post("/ok")

    assert [(line["status"], line["method"], line["route"]) for line in read_log()] == [
        (404, "GET", "/nope"), (405, "POST", "/ok")]
