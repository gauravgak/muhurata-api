"""
db.py — the one place that knows whether we're talking to Postgres or
SQLite, so every other module just calls these functions and never
touches a connection string or a placeholder style directly.

Backends
--------
  - Production: Postgres (Supabase). Connections come from a process-wide
    pool (psycopg 3 + psycopg_pool). The pool points at Supabase's
    *transaction* pooler (Supavisor, port 6543), so prepared statements
    are disabled and every `with cursor()` borrows a connection for the
    duration of one transaction and returns it on exit.
  - Local dev / tests: SQLite at ./muhurata.db, opened per call (a local
    file, so pooling buys nothing). Selected automatically when
    DATABASE_URL is empty.

Calling code writes plain SQL with "?" placeholders always; this module
translates "?" -> "%s" when the active backend is Postgres.

Schema lives in migrations/ (see migrate.py) — it is NOT created here at
import time any more. A DB outage must never crash the process on boot.
"""

import os
import re
import sqlite3

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
IS_POSTGRES = DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")

SQLITE_PATH = os.environ.get("SQLITE_PATH", "muhurata.db")

POOL_MAX = int(os.environ.get("DB_POOL_MAX", "8"))
POOL_TIMEOUT = float(os.environ.get("DB_POOL_TIMEOUT", "5"))
STATEMENT_TIMEOUT_MS = int(os.environ.get("DB_STATEMENT_TIMEOUT_MS", "8000"))

if IS_POSTGRES:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    # Errors that mean "the database is not reachable right now" rather
    # than "your query was wrong". app.py turns DBUnavailable into a
    # clean 503 instead of a hung 500.
    from psycopg_pool import PoolTimeout as _PoolTimeout

    _TRANSIENT = (psycopg.OperationalError, psycopg.InterfaceError, _PoolTimeout)
else:
    _TRANSIENT = ()


class DBUnavailable(RuntimeError):
    """Raised when the pool cannot hand back a working connection."""


# ---------------------------------------------------------------- pool

_pool = None


def _dsn() -> str:
    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def init_pool():
    """Idempotent. Safe to call from a FastAPI lifespan handler. Returns
    the pool, or None on SQLite."""
    global _pool
    if not IS_POSTGRES or _pool is not None:
        return _pool

    _pool = ConnectionPool(
        conninfo=_dsn(),
        min_size=1,
        max_size=POOL_MAX,
        timeout=POOL_TIMEOUT,
        max_lifetime=1800,          # recycle every 30 min; Supavisor drops idle conns
        max_idle=300,
        kwargs={
            "prepare_threshold": None,   # REQUIRED for Supavisor transaction mode
            "connect_timeout": 5,
            "options": f"-c statement_timeout={STATEMENT_TIMEOUT_MS}",
            "row_factory": dict_row,
        },
        open=False,
    )
    _pool.open()
    return _pool


def close_pool():
    global _pool
    if _pool is not None:
        try:
            _pool.close()
        finally:
            _pool = None


def healthcheck() -> bool:
    """True if a trivial round-trip to the DB succeeds right now."""
    try:
        with cursor() as c:
            c.execute("SELECT 1")
            c.fetchone()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- translate

def _translate(sql: str) -> str:
    """SQLite '?' placeholders -> Postgres '%s'. No-op on SQLite. None of
    this codebase's SQL has a literal '?' inside a string, so a plain
    positional replace is safe."""
    if not IS_POSTGRES:
        return sql
    return sql.replace("?", "%s")


# ---------------------------------------------------------------- cursor

class Cursor:
    """`with db.cursor() as cur: cur.execute(sql, params)` works the same
    on both backends. On Postgres the connection is borrowed from the
    pool and returned on __exit__ (commit on success, rollback on error).
    On SQLite a fresh connection is opened and closed per block."""

    def __init__(self):
        if IS_POSTGRES:
            self._conn_cm = None
            try:
                pool = init_pool()
                self._conn_cm = pool.connection()      # context manager
                self.conn = self._conn_cm.__enter__()  # psycopg Connection
                self.cur = self.conn.cursor()
            except _TRANSIENT as e:
                if self._conn_cm is not None:
                    # entered but cursor() failed — return the conn to the pool
                    try:
                        self._conn_cm.__exit__(type(e), e, e.__traceback__)
                    except Exception:
                        pass
                raise DBUnavailable(str(e)) from e
            self._sqlite = False
        else:
            self._conn_cm = None
            self.conn = sqlite3.connect(SQLITE_PATH)
            self.conn.row_factory = sqlite3.Row
            self.cur = self.conn.cursor()
            self._sqlite = True

    def execute(self, sql, params=()):
        try:
            self.cur.execute(_translate(sql), params)
        except _TRANSIENT as e:
            raise DBUnavailable(str(e)) from e
        return self  # so chained .fetchone()/.fetchall() go through the
                     # dict-normalising methods below on BOTH backends

    def executescript(self, sql):
        """SQLite's executescript runs many ';'-separated statements at
        once; psycopg needs them split. '--' line comments are stripped
        first so a ';' inside a comment can't split a statement."""
        sql = re.sub(r"--[^\n]*", "", sql)
        for stmt in (s.strip() for s in sql.split(";")):
            if stmt:
                self.execute(stmt)

    def fetchone(self):
        row = self.cur.fetchone()
        if row is None:
            return None
        return row if isinstance(row, dict) else dict(row)

    def fetchall(self):
        return [r if isinstance(r, dict) else dict(r) for r in self.cur.fetchall()]

    @property
    def lastrowid(self):
        if IS_POSTGRES:
            # No universal lastrowid on Postgres — INSERTs that need the
            # new id use "RETURNING id" and read it via fetchone().
            return None
        return self.cur.lastrowid

    def commit(self):
        self.conn.commit()

    def close(self):
        if self._sqlite:
            self.conn.close()
        # Postgres: the pool's context manager (exited in __exit__) both
        # commits/rolls back and returns the connection.

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._sqlite:
            try:
                if exc_type is None:
                    self.conn.commit()
                else:
                    self.conn.rollback()
            finally:
                self.conn.close()
            return False
        # Postgres: delegate commit/rollback + return-to-pool to psycopg.
        try:
            suppress = self._conn_cm.__exit__(exc_type, exc_val, exc_tb)
        except _TRANSIENT as e:
            if exc_type is None:
                raise DBUnavailable(str(e)) from e
            return False
        return bool(suppress)


def cursor():
    return Cursor()


def autoincrement_pk() -> str:
    """The one schema token that differs between backends. migrate.py
    substitutes {{PK}} in .sql files with this."""
    return "SERIAL PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"


def backend_name() -> str:
    return "postgres" if IS_POSTGRES else "sqlite"
