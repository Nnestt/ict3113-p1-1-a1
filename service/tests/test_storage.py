# Unit tests for storage.py. A temp SQLite file stands in for the real volume.

import sqlite3

import storage

CATEGORIES = ["Credit reporting", "Debt collection", "Mortgage", "Credit card", "Bank account or service",
              "Consumer loan", "Money transfer or service", "INVALID"]


def add(db_path, narrative, category="Credit card"):
    return storage.insert_ticket(db_path, narrative, category, "qwen2.5:1.5b", "req-1")


def test_init_db_creates_the_tickets_table(db_path):
    storage.init_db(db_path)

    conn = sqlite3.connect(db_path)
    columns = [row[1] for row in conn.execute("PRAGMA table_info(tickets)")]
    conn.close()
    assert columns == ["id", "narrative", "category", "model", "request_id", "created_at"]


def test_init_db_twice_keeps_existing_tickets(db_path):
    storage.init_db(db_path)
    add(db_path, "first")

    storage.init_db(db_path)

    assert len(storage.search_tickets(db_path, "first")) == 1


def test_insert_returns_increasing_ids(db_path):
    storage.init_db(db_path)

    ids = [add(db_path, "a"), add(db_path, "b"), add(db_path, "c")]

    assert ids == [1, 2, 3]


def test_insert_stores_all_fields(db_path):
    storage.init_db(db_path)

    ticket_id = storage.insert_ticket(db_path, "my card was charged twice", "Credit card", "qwen2.5:7b", "req-42")

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT id, narrative, category, model, request_id, created_at FROM tickets").fetchone()
    conn.close()
    assert row[:5] == (ticket_id, "my card was charged twice", "Credit card", "qwen2.5:7b", "req-42")
    assert row[5].endswith("+00:00") and "T" in row[5]


def test_search_is_a_case_insensitive_substring_match(db_path):
    storage.init_db(db_path)
    add(db_path, "My Bank froze my account")

    found = storage.search_tickets(db_path, "bANk FRO")

    assert [t["narrative"] for t in found] == ["My Bank froze my account"]


def test_search_returns_the_documented_fields(db_path):
    storage.init_db(db_path)
    add(db_path, "hello", "Mortgage")

    ticket = storage.search_tickets(db_path, "hello")[0]

    assert set(ticket) == {"id", "narrative", "category", "model", "created_at"}
    assert ticket["category"] == "Mortgage"


def test_search_orders_by_id(db_path):
    storage.init_db(db_path)
    for text in ["loan one", "loan two", "loan three"]:
        add(db_path, text)

    found = storage.search_tickets(db_path, "loan")

    assert [t["id"] for t in found] == [1, 2, 3]


def test_search_treats_percent_and_underscore_literally(db_path):
    storage.init_db(db_path)
    add(db_path, "charged 100% extra")
    add(db_path, "snake_case name")
    add(db_path, "plain text")

    assert [t["id"] for t in storage.search_tickets(db_path, "%")] == [1]
    assert [t["id"] for t in storage.search_tickets(db_path, "_")] == [2]


def test_search_returns_empty_list_when_nothing_matches(db_path):
    storage.init_db(db_path)
    add(db_path, "something")

    assert storage.search_tickets(db_path, "absent") == []


def test_counts_include_every_category_with_zeros(db_path):
    storage.init_db(db_path)

    counts = storage.count_by_category(db_path, CATEGORIES)

    assert counts == {c: 0 for c in CATEGORIES}


def test_counts_are_correct_after_inserts(db_path):
    storage.init_db(db_path)
    add(db_path, "a", "Mortgage")
    add(db_path, "b", "Mortgage")
    add(db_path, "c", "INVALID")

    counts = storage.count_by_category(db_path, CATEGORIES)

    assert counts["Mortgage"] == 2 and counts["INVALID"] == 1
    assert sum(counts.values()) == 3 and len(counts) == 8
