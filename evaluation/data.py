# Loads the team rows, the golden IDs and the non-golden development rows.

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "golden_set" / "ict3113_tickets.csv"
GOLD = ROOT / "golden_set" / "gold_labels.csv"
TEAM_ROWS = range(1000, 2000)


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# {row_id: gold_label} for the 175 frozen golden tickets
def load_golden():
    return {int(r["row"]): r["gold_label"] for r in read_csv(GOLD)}


def load_team_rows():
    if not SOURCE.is_file():
        raise FileNotFoundError(f"Place the course extract at {SOURCE}")
    team = [r for r in read_csv(SOURCE) if int(r["row"]) in TEAM_ROWS]
    assert len(team) == len(TEAM_ROWS), f"expected {len(TEAM_ROWS)} team rows, found {len(team)}"
    return team


# Team rows outside the golden set; only these go to a model before the evaluation freeze
def load_dev_rows(team=None):
    team = team if team is not None else load_team_rows()
    golden_ids = set(load_golden())
    team_ids = {int(r["row"]) for r in team}
    assert golden_ids <= team_ids, "every golden ID must come from the team rows"
    return [r for r in team if int(r["row"]) not in golden_ids]


def assert_not_golden(rows):
    clash = set(load_golden()) & {int(r["row"]) for r in rows}
    assert not clash, f"golden rows must not be sent to a model before the freeze: {sorted(clash)}"