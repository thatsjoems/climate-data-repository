"""
The QR code offered at enrolment. It is a convenience: setting up must work without it (the typed key), and when it is there it must be a
real QR code of the address the authenticator app needs (checked by decoding the drawn picture with a QR reader when this was written).
"""
import re

from app.core import mfa
from tests.conftest import login
from tests.test_mfa_login import _bot, clock, required  # noqa: F401  (fixtures)


def test_the_qr_is_a_small_svg_with_the_size_of_a_real_qr_code():
    svg = mfa.qr_svg(mfa.otpauth_uri("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", "admin"))
    assert svg.startswith("<svg") and "<script" not in svg.lower() and len(svg) < 60_000
    modules = int(re.search(r'viewBox="0 0 (\d+) ', svg).group(1)) - 8        # minus the 4-module quiet zone on each side
    assert 21 <= modules <= 177 and (modules - 17) % 4 == 0                    # QR sizes are 17 + 4 x version


def test_a_qr_that_cannot_be_drawn_is_none_not_an_error(monkeypatch):
    from reportlab.graphics.barcode import qrencoder

    def broken(*args, **kwargs):
        raise RuntimeError("cannot draw")

    monkeypatch.setattr(qrencoder, "QRCode", broken)
    assert mfa.qr_svg("anything") is None


def test_enrolment_offers_the_typed_key_and_the_picture(client, db_session, required, clock):
    _bot(db_session)
    token = login(client, "analyst1").json()["mfa_token"]
    body = client.post("/api/auth/mfa/setup/begin", json={"mfa_token": token}).json()
    assert body["secret"] and body["otpauth_uri"].startswith("otpauth://totp/")
    assert body["qr_svg"] is None or body["qr_svg"].startswith("<svg")
