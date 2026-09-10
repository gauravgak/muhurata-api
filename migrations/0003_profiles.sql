-- Saved birth details per signed-in user, so forms prefill and nobody
-- has to type their DOB twice. Keyed on the Supabase user id.

CREATE TABLE IF NOT EXISTS profiles (
    user_id     TEXT PRIMARY KEY,
    name        TEXT,
    dob         TEXT,
    tob         TEXT,
    place       TEXT,
    phone       TEXT,
    updated_at  DOUBLE PRECISION NOT NULL
);
