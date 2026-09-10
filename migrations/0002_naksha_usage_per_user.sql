-- Naksha's free-question counter was keyed on a client-supplied
-- session_id, so a page refresh (any new string) reset it. It is now
-- keyed on the verified Supabase user id. Daily counters are disposable,
-- so the old table is dropped rather than migrated.

DROP TABLE IF EXISTS naksha_usage;

CREATE TABLE naksha_usage (
    user_id     TEXT NOT NULL,
    day         TEXT NOT NULL,
    count       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);
