"""
migrate.py — apply pending SQL migrations, once, before the app starts.

Run locally:        python migrate.py
Run on Render:      set this as the service's Pre-Deploy Command.

Migrations live in migrations/*.sql, applied in filename order. Each file
runs in its own transaction; a file that has already been applied (its
name is in the schema_migrations table) is skipped. Applying twice is a
no-op, so it is safe to run on every deploy.

Backend selection mirrors db.py:
  - Postgres if DIRECT_URL or DATABASE_URL points at postgres. DIRECT_URL
    (Supabase direct connection, port 5432) is preferred here because DDL
    should not go through the transaction pooler.
  - SQLite otherwise (./muhurata.db).

Dialect: write portable SQL. The single token {{PK}} is substituted with
"SERIAL PRIMARY KEY" (Postgres) or "INTEGER PRIMARY KEY AUTOINCREMENT"
(SQLite).
"""

import glob
import os
import re
import sqlite3
import sys

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")

_URL = (os.environ.get("DIRECT_URL") or os.environ.get("DATABASE_URL") or "").strip()
IS_POSTGRES = _URL.startswith("postgres://") or _URL.startswith("postgresql://")
SQLITE_PATH = os.environ.get("SQLITE_PATH", "muhurata.db")


def _pk() -> str:
    return "SERIAL PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"


def _connect():
    if IS_POSTGRES:
        import psycopg
        url = _URL
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        return psycopg.connect(url, autocommit=False, connect_timeout=10)
    return sqlite3.connect(SQLITE_PATH)


def _placeholder() -> str:
    return "%s" if IS_POSTGRES else "?"


def _applied(conn) -> set:
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " filename TEXT PRIMARY KEY,"
        " applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.commit()
    cur.execute("SELECT filename FROM schema_migrations")
    return {r[0] for r in cur.fetchall()}


def main() -> int:
    if not os.path.isdir(MIGRATIONS_DIR):
        print(f"no migrations dir at {MIGRATIONS_DIR}", file=sys.stderr)
        return 1

    files = sorted(glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql")))
    if not files:
        print("no migration files found")
        return 0

    conn = _connect()
    try:
        done = _applied(conn)
        ran = 0
        for path in files:
            name = os.path.basename(path)
            if name in done:
                continue
            with open(path, "r", encoding="utf-8") as fh:
                sql = fh.read().replace("{{PK}}", _pk())

            # Strip "--" line comments before splitting on ";" — our DDL
            # never puts "--" or ";" inside a string literal, and a ";"
            # inside a comment would otherwise split a statement in two.
            sql = re.sub(r"--[^\n]*", "", sql)

            cur = conn.cursor()
            try:
                # SQLite's driver rejects multiple statements in one
                # execute(); split. Postgres is fine either way but the
                # split keeps behaviour identical.
                for stmt in (s.strip() for s in sql.split(";")):
                    if stmt:
                        cur.execute(stmt)
                cur.execute(
                    f"INSERT INTO schema_migrations (filename) VALUES ({_placeholder()})",
                    (name,),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                print(f"FAILED on {name}", file=sys.stderr)
                raise
            print(f"applied {name}")
            ran += 1

        print(f"up to date ({ran} applied, {len(files) - ran} already present)")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
