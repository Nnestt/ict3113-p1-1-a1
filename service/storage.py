# SQLite storage for the triage service. Knows nothing about HTTP or the classifier.
# Every function takes db_path and opens its own short-lived connection.

import sqlite3
from datetime import datetime, timezone


# Opens a new connection, runs one statement, commits, closes. Returns (rows, lastrowid).
def run_sql(db_path, sql, args=()):
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        with conn:
            cur = conn.execute(sql, args)
            return cur.fetchall(), cur.lastrowid
    finally:
        conn.close()


# Creates the tickets table if it does not exist yet
def init_db(db_path):
    run_sql(db_path, "CREATE TABLE IF NOT EXISTS tickets (id INTEGER PRIMARY KEY AUTOINCREMENT, narrative TEXT NOT NULL, "
                     "category TEXT NOT NULL, model TEXT NOT NULL, request_id TEXT NOT NULL, created_at TEXT NOT NULL)")


# Stores one ticket and returns its id
def insert_ticket(db_path, narrative, category, model, request_id):
    created_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    _, ticket_id = run_sql(db_path, "INSERT INTO tickets (narrative, category, model, request_id, created_at) "
                                    "VALUES (?, ?, ?, ?, ?)", (narrative, category, model, request_id, created_at))
    return ticket_id


# Every ticket whose narrative contains q (case-insensitive, % and _ are literal), ordered by id, no limit
def search_tickets(db_path, q):
    rows, _ = run_sql(db_path, "SELECT id, narrative, category, model, created_at FROM tickets "
                               "WHERE instr(lower(narrative), lower(?)) > 0 ORDER BY id", (q,))
    keys = ["id", "narrative", "category", "model", "created_at"]
    return [dict(zip(keys, row)) for row in rows]


# Ticket count per category; every name in categories is present, zeros included
def count_by_category(db_path, categories):
    rows, _ = run_sql(db_path, "SELECT category, COUNT(*) FROM tickets GROUP BY category")
    counts = {c: 0 for c in categories}
    counts.update(dict(rows))
    return counts
