# The classifier files in service/ must stay identical to the frozen originals in evaluation/.
# If this fails, copy the three files from evaluation/ into service/ again; never edit the copies.

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name", ["classifier.py", "eval_config.json", "prompt_template.md"])
def test_service_copy_is_identical_to_the_frozen_original(name):
    assert (ROOT / "service" / name).read_bytes() == (ROOT / "evaluation" / name).read_bytes()
