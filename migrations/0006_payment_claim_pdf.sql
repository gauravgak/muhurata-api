-- Stores the LLM-generated PDF for a payment claim right in the
-- database, not on the server's disk. Render's filesystem is wiped on
-- every deploy/restart, so anything saved "locally" there is gone by
-- the next deploy; the pooled Postgres (or SQLite locally) already
-- survives that, so the PDF lives here instead — generated on demand
-- from the admin claims page, then downloaded or sent by hand.

ALTER TABLE payment_claims ADD COLUMN pdf_bytes {{BLOB}};
ALTER TABLE payment_claims ADD COLUMN pdf_generated_at DOUBLE PRECISION;
