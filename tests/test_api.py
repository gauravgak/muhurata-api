"""End-to-end API behaviour via TestClient (SQLite backend)."""

import time

import jwt
import pytest


def _admin_token():
    return jwt.encode(
        {"sub": "admin-uid", "email": "admin@example.com", "aud": "authenticated"},
        "test-secret-not-real-000000000000000", algorithm="HS256",
    )


def _user_token():
    return jwt.encode(
        {"sub": "user-uid", "email": "nobody@example.com", "aud": "authenticated"},
        "test-secret-not-real-000000000000000", algorithm="HS256",
    )


def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["db"] == "ok"
    assert "llm" in body and "configured" in body["llm"]


def test_reading_happy_path(client, sample_reading_body):
    r = client.post("/api/reading", json=sample_reading_body)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "reading" in body and "whatsapp" in body
    assert body["ascendant"]["sign"]
    # a lead row was written
    import db
    with db.cursor() as c:
        n = c.execute("SELECT COUNT(*) AS n FROM leads").fetchone()["n"]
    assert n >= 1


def test_reading_bad_date_422(client, sample_reading_body):
    bad = {**sample_reading_body, "dob": "not-a-date"}
    assert client.post("/api/reading", json=bad).status_code == 422


def test_reading_honeypot_is_silent_noop(client, sample_reading_body):
    import db
    with db.cursor() as c:
        before = c.execute("SELECT COUNT(*) AS n FROM leads").fetchone()["n"]
    r = client.post("/api/reading", json={**sample_reading_body, "website": "http://spam"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    with db.cursor() as c:
        after = c.execute("SELECT COUNT(*) AS n FROM leads").fetchone()["n"]
    assert after == before


def test_leads_requires_admin(client):
    assert client.get("/api/leads").status_code == 401
    assert client.get(
        "/api/leads", headers={"Authorization": f"Bearer {_user_token()}"}
    ).status_code == 403
    assert client.get(
        "/api/leads", headers={"Authorization": f"Bearer {_admin_token()}"}
    ).status_code == 200


def test_naksha_requires_sign_in(client):
    r = client.post("/api/naksha/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 401


def test_webhook_rejects_bad_signature(client):
    r = client.post(
        "/api/whatsapp/webhook",
        content=b'{"entry":[]}',
        headers={"x-hub-signature-256": "sha256=deadbeef"},
    )
    assert r.status_code == 403


def test_reading_pdf_renders_with_rule_based_fallback(client, sample_reading_body):
    # No LLM configured in tests -> _pdf_sections falls back to interpret.py,
    # and the document must still render for both themes.
    for theme in ("light", "dark"):
        r = client.post(f"/api/reading/pdf?theme={theme}", json=sample_reading_body)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:5] == b"%PDF-"
        assert len(r.content) > 5000


def test_rate_limit_kicks_in(client, sample_reading_body):
    # burst=8 on the reading limiter; the 9th+ within a minute should 429
    seen_429 = False
    for _ in range(14):
        r = client.post("/api/reading", json=sample_reading_body)
        if r.status_code == 429:
            seen_429 = True
            break
        time.sleep(0.01)
    assert seen_429
