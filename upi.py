"""
upi.py — UPI deep links + QR codes for the manual pay-then-screenshot
flow (see the monetisation plan). No payment gateway, no KYC: the buyer
pays your UPI ID directly, then sends a screenshot on WhatsApp. This
module only builds the tap-to-pay link and its QR code — it never
verifies a payment, that part is manual by design.

Set UPI_VPA (your own UPI ID, e.g. "you@okhdfcbank") as an env var.
"""

import os
import io
import urllib.parse

import segno

UPI_VPA = os.environ.get("UPI_VPA", "")
PAYEE_NAME = "Muhurata"


def configured() -> bool:
    return bool(UPI_VPA)


def pay_link(amount_rupees: float, note: str = "") -> str:
    """A upi://pay deep link with the amount pre-filled. Tapped on a
    phone, this opens whichever UPI app is installed with the payee and
    amount already set — nothing for the buyer to type or get wrong."""
    if not UPI_VPA:
        raise RuntimeError("UPI_VPA is not set")
    params = {
        "pa": UPI_VPA,
        "pn": PAYEE_NAME,
        "am": f"{amount_rupees:.2f}",
        "cu": "INR",
    }
    if note:
        params["tn"] = note[:50]
    return "upi://pay?" + urllib.parse.urlencode(params)


def qr_svg(payload: str, dark: str = "#1c130a", light: str = "#ffffff") -> str:
    """Renders any short text (here, a upi://pay link) as a scannable QR
    code, as an SVG string. Pure Python (segno), no external QR service
    ever sees the payload."""
    qr = segno.make(payload, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=6, dark=dark, light=light,
             xmldecl=False, svgns=True, border=2)
    return buf.getvalue().decode()
