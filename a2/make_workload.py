#!/usr/bin/env python3
"""Generate the A2 speed-test row files from the team's committed design.

The row selections are the design recorded in a2_planrubrics (Design Pack),
originally produced with seed 20261123. Narratives are drawn from
load_test/data/dev_tickets.csv (the 825 dev rows outside the golden set, already
checked with assert_not_golden). Per design decision D17, line breaks inside a
narrative are replaced with spaces for the speed-test files, so JMeter's CSV
reader cannot split one ticket into two requests. Wording is unchanged and the
accuracy test still sends the original text.

Run from the repo root:  python a2/make_workload.py
Outputs: a2/{warmup,s,workload,pilot}_rows.csv  (row,narrative; UTF-8; header; quoted)
"""
import csv, os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "load_test", "data", "dev_tickets.csv")
OUT = os.path.join(REPO, "a2")

WARMUP = [1986, 1180, 1773]
S_ROWS = [1181, 1342, 1322]
WORKLOAD = [
    1520,1636,1965,1941,1488,1673,1266,1359,1482,1828,
    1720,1564,1543,1821,1050,1485,1958,1926,1867,1857,
    1375,1444,1541,1047,1692,1901,1067,1588,1060,1772,
    1378,1527,1462,1273,1163,1102,1819,1235,1383,1164,
    1117,1355,1884,1782,1171,1497,1239,1514,1409,1796,
    1878,1611,1336,1311,1888,1770,1302,1048,1477,1714,
    1004,1002,1357,1959,1452,1838,1728,1651,1814,1077,
    1556,1989,1228,1104,1523,1614,1739,1763,1672,1296,
    1921,1860,1513,1533,1044,1680,1324,1137,1468,1786,
    1393,1262,1820,1887,1934,1938,1121,1009,1528,1946,
    1250,1976,1035,1668,1170,1109,1184,1387,1570,1532,
    1436,1794,1501,1862,1303,1760,1549,1015,1013,1694,
    1932,1432,1024,1998,1798,1910,1643,1988,1297,1854,
    1557,1211,1461,1918,1450,1848,1290,1293,1863,1160,
    1600,1292,1216,1091,1241,1540,1438,1269,1460,1445,
]
PILOT = [
    1232,1049,1064,1648,1617,1267,1913,1498,1156,1435,
    1073,1281,1625,1699,1682,1602,1136,1626,1463,1490,
]

def one_line(t):
    return t.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")

def main():
    narr = {}
    with open(SRC, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            narr[int(r["row"])] = r["narrative"]
    files = {"warmup_rows": WARMUP, "s_rows": S_ROWS,
             "workload_rows": WORKLOAD, "pilot_rows": PILOT}
    seen = {}
    for name, rows in files.items():
        for rw in rows:
            assert rw in narr, f"row {rw} ({name}) not in dev_tickets.csv (missing or golden)"
            assert rw not in seen, f"row {rw} in both {name} and {seen[rw]}"
            seen[rw] = name
    assert [len(files[k]) for k in ("warmup_rows","s_rows","workload_rows","pilot_rows")] == [3,3,150,20]
    for name, rows in files.items():
        with open(os.path.join(OUT, name + ".csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, quoting=csv.QUOTE_ALL)
            w.writerow(["row", "narrative"])
            for rw in rows:
                nl = one_line(narr[rw])
                assert "\n" not in nl and "\r" not in nl
                w.writerow([rw, nl])
    def stats(rows):
        L = sorted(len(one_line(narr[r])) for r in rows)
        n = len(L); med = L[n//2] if n % 2 else (L[n//2-1] + L[n//2]) // 2
        return f"{n:3} rows | len {L[0]}-{L[-1]}, median {med} | long(>1600): {sum(x>1600 for x in L)}"
    for name in ("warmup_rows","s_rows","workload_rows","pilot_rows"):
        print(f"  {name:14} {stats(files[name])}")
    print(f"  total distinct rows used: {len(seen)}")

if __name__ == "__main__":
    main()
