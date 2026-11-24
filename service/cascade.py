# Model routing for POST /tickets (Assignment 2). Single mode: one model answers. Cascade mode: the small
# model answers first; its label is kept when it is in the setting's accept list, otherwise the ticket is
# escalated to the large model, whose label is final. The rule is documented in a2/escalation_rule.md and
# the log fields in a2/CONTRACTS.md. Pure logic: the model call is passed in, so tests need no Ollama.

import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / "cascade_config.json"

NOT_ACCEPTED = "not_accepted"  # small label is valid but not in the accept list
INVALID_OUTPUT = "invalid"     # small output could not be parsed into a category
SMALL_ERROR = "small_error"    # small-model call failed; the large model still answers


# Returns {setting_name: frozenset(accept labels)}; raises ValueError on an unknown label
def load_settings(labels, path=CONFIG_PATH):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    settings = {}
    for name, setting in config["settings"].items():
        unknown = [label for label in setting["accept"] if label not in labels]
        if unknown:
            raise ValueError(f"cascade setting {name}: unknown accept labels {unknown}")
        settings[name] = frozenset(setting["accept"])
    return settings


def _stage(prefix, result):
    return {f"{prefix}_label": result["label"], f"{prefix}_raw_output": result["raw_output"],
            f"{prefix}_ms": result["wall_ms"], f"{prefix}_load_ms": result["load_ms"]}


def _final(result):
    return {key: result[key] for key in ("raw_output", "load_ms", "prompt_eval_ms", "eval_ms", "prompt_tokens",
                                         "output_tokens", "possibly_truncated")}


EMPTY_SMALL = {"small_label": None, "small_raw_output": None, "small_ms": None, "small_load_ms": None,
               "small_error": None}
EMPTY_LARGE = {"large_label": None, "large_raw_output": None, "large_ms": None, "large_load_ms": None}


# Classifies one narrative and returns (category, final_model). classify(narrative, model) is
# classifier.classify and invalid is its INVALID label. Log fields are written into `log` as the stages run,
# so a failure of the deciding call (raised to the caller) still leaves the earlier stages in the log.
def route(narrative, log, mode, classify, invalid, model=None, small=None, large=None, accept=frozenset()):
    log.update({**EMPTY_SMALL, **EMPTY_LARGE, "escalated": False, "escalation_reason": None})
    if mode == "single":
        result = classify(narrative, model)
        log.update({"model_ms": result["wall_ms"], **_final(result)})
        return result["label"], model

    if mode != "cascade":
        raise ValueError(f"unknown TRIAGE_MODE {mode!r}")

    small_ms = 0.0
    try:
        first = classify(narrative, small)
    except Exception as exc:  # the large model still answers; the error stays visible in the log
        log["small_error"] = repr(exc)
        reason = SMALL_ERROR
    else:
        log.update(_stage("small", first))
        small_ms = first["wall_ms"]
        if first["label"] in accept:
            log.update({"model_ms": small_ms, **_final(first)})
            return first["label"], small
        reason = INVALID_OUTPUT if first["label"] == invalid else NOT_ACCEPTED

    log.update({"escalated": True, "escalation_reason": reason})
    second = classify(narrative, large)
    log.update({**_stage("large", second), "model_ms": round(small_ms + second["wall_ms"], 1), **_final(second)})
    return second["label"], large
