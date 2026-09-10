"""db.py: the cursor API and the migration runner, on SQLite."""

import db


def test_migrations_created_tables():
    with db.cursor() as c:
        rows = c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    names = {r["name"] for r in rows}
    assert {"charts", "leads", "predictions", "claims", "naksha_usage"} <= names


def test_naksha_usage_is_per_user():
    with db.cursor() as c:
        cols = c.execute("PRAGMA table_info(naksha_usage)").fetchall()
    colnames = {row["name"] for row in cols}
    assert "user_id" in colnames
    assert "session_id" not in colnames


def test_cursor_roundtrip_and_commit():
    with db.cursor() as c:
        c.execute("INSERT INTO charts (key, payload, created_at) VALUES (?,?,?)",
                  ("k1", '{"a":1}', 1.0))
    # separate connection sees the committed row
    with db.cursor() as c:
        row = c.execute("SELECT payload FROM charts WHERE key=?", ("k1",)).fetchone()
    assert row["payload"] == '{"a":1}'


def test_cursor_rolls_back_on_error():
    try:
        with db.cursor() as c:
            c.execute("INSERT INTO charts (key, payload, created_at) VALUES (?,?,?)",
                      ("k2", "{}", 1.0))
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    with db.cursor() as c:
        row = c.execute("SELECT 1 AS one FROM charts WHERE key=?", ("k2",)).fetchone()
    assert row is None


def test_healthcheck_true_on_sqlite():
    assert db.healthcheck() is True
