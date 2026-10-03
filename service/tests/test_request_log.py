# Unit tests for request_log.py. No HTTP server: a fake request object and a temp file.

import json
import time
from types import SimpleNamespace

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
