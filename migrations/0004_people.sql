-- People a signed-in user has entered birth details for (themselves,
-- partners in a match, someone they asked Naksha about). Lets every form
-- offer a "pick a saved person" dropdown. person_id is a hash of the
-- details so re-entering the same person doesn't duplicate.

CREATE TABLE IF NOT EXISTS people (
    user_id     TEXT NOT NULL,
    person_id   TEXT NOT NULL,
    name        TEXT,
    dob         TEXT,
    tob         TEXT,
    place       TEXT,
    updated_at  DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (user_id, person_id)
);
