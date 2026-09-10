"""
whatsapp.py — WhatsApp Cloud API integration.

Meta's rule: you cannot message a user first without a pre-approved template,
and approval takes days. But once a user messages YOU, a 24-hour service
window opens in which you can send whatever you like.

So the flow is inverted deliberately:

    1. User submits the form. Chart is computed and shown on the page instantly.
    2. Page shows "Send it to my WhatsApp" -> opens wa.me with a prefilled
       message containing a short claim code.
    3. User taps send. That message hits /api/whatsapp/webhook.
    4. We look up the code, and reply with the full reading. Free, instant,
       no template approval.

Set these env vars:
    WA_TOKEN            permanent access token from Meta
    WA_PHONE_ID         phone number ID (not the phone number)
    WA_VERIFY_TOKEN     any string you choose; must match Meta's webhook config
    WA_BUSINESS_NUMBER  your number in international format, e.g. 919876543210
"""

import hashlib
import hmac
import os
import urllib.parse
import urllib.request
import json

WA_TOKEN = os.environ.get("WA_TOKEN", "")
WA_PHONE_ID = os.environ.get("WA_PHONE_ID", "")
# No default: an unset verify token must fail webhook verification, not
# fall back to a guessable string.
WA_VERIFY_TOKEN = os.environ.get("WA_VERIFY_TOKEN", "")
# Meta app secret — used to verify X-Hub-Signature-256 on inbound POSTs.
WA_APP_SECRET = os.environ.get("WA_APP_SECRET", "")
WA_BUSINESS_NUMBER = os.environ.get("WA_BUSINESS_NUMBER", "")

GRAPH = "https://graph.facebook.com/v21.0"


def configured() -> bool:
    return bool(WA_TOKEN and WA_PHONE_ID)


def verify_signature(raw_body: bytes, header: str) -> bool:
    """True iff `header` (the X-Hub-Signature-256 value) is a valid
    HMAC-SHA256 of the raw request body under the Meta app secret.
    Fails closed when WA_APP_SECRET is unset."""
    if not WA_APP_SECRET:
        return False
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(WA_APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1])


def claim_link(code: str) -> str:
    """wa.me link the user taps. Their message opens the 24h service window."""
    if not WA_BUSINESS_NUMBER:
        return ""
    text = f"Send me my reading. Code: {code}"
    return f"https://wa.me/{WA_BUSINESS_NUMBER}?text={urllib.parse.quote(text)}"


def send_text(to: str, body: str) -> dict:
    """Send a free-form message. Only valid inside an open 24h window."""
    if not configured():
        return {"skipped": "WhatsApp not configured"}

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": body[:4000]},
    }
    req = urllib.request.Request(
        f"{GRAPH}/{WA_PHONE_ID}/messages",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {WA_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def send_template(to: str, template: str, lang: str = "en") -> dict:
    """Business-initiated message. Requires an approved template in Meta.
    Use this only once you have one approved and want to message people
    outside the 24h window."""
    if not configured():
        return {"skipped": "WhatsApp not configured"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {"name": template, "language": {"code": lang}},
    }
    req = urllib.request.Request(
        f"{GRAPH}/{WA_PHONE_ID}/messages",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {WA_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def parse_incoming(body: dict):
    """Pull (from_number, text) out of a Cloud API webhook payload.
    Returns (None, None) for delivery receipts and other non-message events."""
    try:
        change = body["entry"][0]["changes"][0]["value"]
        msgs = change.get("messages")
        if not msgs:
            return None, None
        m = msgs[0]
        if m.get("type") != "text":
            return m.get("from"), ""
        return m["from"], m["text"]["body"]
    except (KeyError, IndexError, TypeError):
        return None, None


def upload_media(pdf_bytes: bytes, filename: str = "reading.pdf") -> str:
    """Uploads a document to Meta's media endpoint, returns a media ID.
    That ID is what a document message references - WhatsApp does not
    accept raw file bytes in the message call itself."""
    if not configured():
        raise RuntimeError("WhatsApp not configured")

    boundary = "muhurata-boundary-x7f3"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="messaging_product"\r\n\r\n'
        f"whatsapp\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode() + pdf_bytes + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{GRAPH}/{WA_PHONE_ID}/media",
        data=body,
        headers={
            "Authorization": f"Bearer {WA_TOKEN}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        result = json.loads(r.read())
    if "id" not in result:
        raise RuntimeError(f"Media upload failed: {result}")
    return result["id"]


def send_document(to: str, media_id: str, filename: str, caption: str = "") -> dict:
    """Send a previously-uploaded document by its media ID."""
    if not configured():
        return {"skipped": "WhatsApp not configured"}
    payload = {
        "messaging_product": "whatsapp", "recipient_type": "individual", "to": to,
        "type": "document",
        "document": {"id": media_id, "filename": filename, "caption": caption[:1024]},
    }
    req = urllib.request.Request(
        f"{GRAPH}/{WA_PHONE_ID}/messages",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {WA_TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def send_reading_pdf(to: str, pdf_bytes: bytes, caption: str,
                     filename: str = "muhurata-reading.pdf") -> dict:
    """The whole hop in one call: upload, then send. Returns the send
    result; raises only if the upload itself fails, since a failed
    upload means there is nothing to send."""
    media_id = upload_media(pdf_bytes, filename)
    return send_document(to, media_id, filename, caption)


def send_template_with_document(to: str, template_name: str, media_id: str,
                                filename: str, body_params: list, lang: str = "en") -> dict:
    """Business-initiated send using an approved template with a
    document header. This is the one way to reach someone who has
    never messaged you - Meta reviews the template text once, and
    after approval every send using it is allowed, no open 24h
    window required. See CATCHUP_TEMPLATE below for what to submit."""
    if not configured():
        return {"skipped": "WhatsApp not configured"}
    payload = {
        "messaging_product": "whatsapp", "to": to, "type": "template",
        "template": {
            "name": template_name, "language": {"code": lang},
            "components": [
                {"type": "header", "parameters": [
                    {"type": "document", "document": {"id": media_id, "filename": filename}}]},
                {"type": "body", "parameters": [{"type": "text", "text": p} for p in body_params]},
            ],
        },
    }
    req = urllib.request.Request(
        f"{GRAPH}/{WA_PHONE_ID}/messages",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {WA_TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------
# Submit this exact text in Meta Business Manager > WhatsApp > Message
# Templates > Create Template, before send_template_with_document will
# work for anyone who hasn't messaged you first. Category: UTILITY
# (not MARKETING - this is fulfilling an existing request, not an ad,
# and utility templates review faster and don't need opt-in marketing
# consent). Typical review time is minutes to a couple of days.
#
#   Header:  Document
#   Body:    Hey {{1}}, we might have missed your request earlier —
#            the moon is up now. Here is your reading!
#   Footer:  Muhurata · muhurata.com
#
# {{1}} is filled with the person's first name at send time.
CATCHUP_TEMPLATE_NAME = "muhurata_catchup_reading"
