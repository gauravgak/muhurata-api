-- Baseline schema. Uses CREATE TABLE IF NOT EXISTS so it is a no-op when
-- run on top of a database restored from the old Render Postgres dump,
-- and creates everything from scratch on a fresh database.
--
-- Portable across Postgres and SQLite. {{PK}} is substituted by migrate.py.
-- DOUBLE PRECISION is used for epoch-second timestamps (time.time()); it
-- maps to REAL affinity on SQLite and to float8 on Postgres.

CREATE TABLE IF NOT EXISTS charts (
    key         TEXT PRIMARY KEY,
    payload     TEXT NOT NULL,
    created_at  DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS leads (
    id               {{PK}},
    name             TEXT,
    dob              TEXT,
    tob              TEXT,
    place            TEXT,
    phone            TEXT,
    whatsapp_opt_in  INTEGER,
    chart_key        TEXT,
    created_at       DOUBLE PRECISION,
    sent_at          DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS leads_phone ON leads(phone);
CREATE INDEX IF NOT EXISTS leads_unsent ON leads(id) WHERE sent_at IS NULL;

CREATE TABLE IF NOT EXISTS predictions (
    chart_key   TEXT NOT NULL,
    section     TEXT NOT NULL,
    text        TEXT NOT NULL,
    created_at  DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (chart_key, section)
);

CREATE TABLE IF NOT EXISTS claims (
    code        TEXT PRIMARY KEY,
    message     TEXT NOT NULL,
    name        TEXT,
    lead_id     INTEGER,
    created_at  DOUBLE PRECISION NOT NULL,
    claimed_at  DOUBLE PRECISION
);
