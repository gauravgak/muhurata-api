"""upi.py: the deep link + QR for the manual UPI-via-WhatsApp pay flow."""

import upi


def test_pay_link_shape(monkeypatch):
    monkeypatch.setattr(upi, "UPI_VPA", "muhurata@okhdfcbank")
    link = upi.pay_link(51, note="pdf")
    assert link.startswith("upi://pay?")
    assert "pa=muhurata%40okhdfcbank" in link
    assert "am=51.00" in link
    assert "cu=INR" in link


def test_pay_link_requires_vpa(monkeypatch):
    monkeypatch.setattr(upi, "UPI_VPA", "")
    try:
        upi.pay_link(51)
        assert False, "should have raised"
    except RuntimeError:
        pass


def test_qr_svg_is_valid_svg():
    svg = upi.qr_svg("upi://pay?pa=test@upi&am=51.00&cu=INR")
    assert svg.strip().startswith("<svg")
    assert "</svg>" in svg


def test_pay_qr_endpoint(client, monkeypatch):
    monkeypatch.setattr(upi, "UPI_VPA", "muhurata@okhdfcbank")
    r = client.get("/api/pay/qr", params={"amount": 51, "note": "pdf"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert b"<svg" in r.content


def test_pay_qr_endpoint_rejects_bad_amount(client, monkeypatch):
    monkeypatch.setattr(upi, "UPI_VPA", "muhurata@okhdfcbank")
    assert client.get("/api/pay/qr", params={"amount": 0}).status_code == 422
    assert client.get("/api/pay/qr", params={"amount": 99999}).status_code == 422


def test_pay_qr_endpoint_unconfigured(client, monkeypatch):
    monkeypatch.setattr(upi, "UPI_VPA", "")
    assert client.get("/api/pay/qr", params={"amount": 51}).status_code == 503


def test_pay_link_endpoint(client, monkeypatch):
    monkeypatch.setattr(upi, "UPI_VPA", "muhurata@okhdfcbank")
    r = client.get("/api/pay/link", params={"amount": 51, "note": "pdf"})
    assert r.status_code == 200
    body = r.json()
    assert body["vpa"] == "muhurata@okhdfcbank"
    assert body["link"].startswith("upi://pay?")
