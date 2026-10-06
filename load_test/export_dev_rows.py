"""Exports the team's non-golden dev rows (825 tickets) to a JMeter-ready CSV.

Run from load_test/:
    python export_dev_rows.py

Output: load_test/data/dev_tickets.csv (row,narrative), for the CSV Data Set
Config in the JMeter test plan. Golden-set rows are excluded, per
evaluation/README.md's rule that golden tickets never go through a model
before the freeze commit.
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evaluation"))
import data

OUT = Path(__file__).resolve().parent / "data" / "dev_tickets.csv"


def main():
    dev_rows = data.load_dev_rows()
    data.assert_not_golden(dev_rows)

    with OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(["row", "narrative"])
        for r in dev_rows:
            writer.writerow([r["row"], r["narrative"]])

    print(f"Wrote {len(dev_rows)} rows to {OUT}")


if __name__ == "__main__":
    main()
