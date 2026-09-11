-- Manual UPI-via-WhatsApp payments: no gateway, no auto-verification.
-- A screenshot arriving on WhatsApp logs one row here so it can't get
-- lost in the WhatsApp app; a human (admin) verifies the payment landed
-- and sends the report themselves, then marks the row resolved.

CREATE TABLE IF NOT EXISTS payment_claims (
    id             {{PK}},
    phone          TEXT NOT NULL,
    wa_message_id  TEXT,
    media_id       TEXT,
    lead_guess_id  INTEGER,        -- best-effort match against leads.id
    received_at    DOUBLE PRECISION NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending',   -- pending | done | rejected
    resolved_at    DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_payment_claims_status ON payment_claims (status, received_at);
