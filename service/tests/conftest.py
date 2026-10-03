# Shared test setup. Tests need no Docker, Ollama, dataset or network, and write only under tmp_path.

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "service"), str(ROOT / "evaluation")]

import app as app_module  # noqa: E402  (importing app has no side effects)

TEST_MODEL = "qwen2.5:1.5b"


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "tickets.db")


@pytest.fixture
def log_path(tmp_path):
    return str(tmp_path / "requests.jsonl")


# The app module pointed at temp files and a pinned test model
@pytest.fixture
def app_mod(monkeypatch, db_path, log_path):
    monkeypatch.setattr(app_module, "MODEL", TEST_MODEL)
    monkeypatch.setattr(app_module, "DB_PATH", db_path)
    monkeypatch.setattr(app_module, "LOG_PATH", log_path)
    return app_module


# Test client without lifespan: startup is not run unless a test uses "with TestClient(...)"
@pytest.fixture
def client(app_mod):
    return TestClient(app_mod.app)


# A classifier.classify() result as the real classifier returns it
@pytest.fixture
def classify_result():
    def make(label="Credit card", raw_output=None):
        return {"label": label, "raw_output": raw_output or label, "wall_ms": 12.3, "load_ms": 1.0,
                "prompt_eval_ms": 2.0, "eval_ms": 3.0, "prompt_tokens": 50, "output_tokens": 3,
                "possibly_truncated": False}
    return make


# Returns the parsed lines of the log file; fails if any line is not valid JSON
@pytest.fixture
def read_log(log_path):
    def read():
        with open(log_path, encoding="utf-8") as f:
            return [json.loads(line) for line in f.read().split("\n") if line]
    return read
