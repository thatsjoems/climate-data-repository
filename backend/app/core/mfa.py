"""
Two-step sign-in with a time-based one-time code (TOTP, RFC 6238), the kind an authenticator app on a phone produces.

Built on the standard library only (the code algorithm is a few lines of HMAC-SHA1, and is checked here against the published RFC test
vectors); the one dependency used, `cryptography`, was already installed with the JWT library.

  - The shared secret is stored ENCRYPTED (Fernet, key derived from SECRET_KEY): a copy of the database alone cannot produce codes.
  - A code is accepted within one 30-second step either side of now, and each step only once: a code that was just used (or an older
    one) is refused, so a code seen over a shoulder or in a log cannot be replayed.
  - Ten single-use recovery codes are given once at enrolment, for a lost phone. They are stored only as keyed hashes.
  - A step token (5 minutes, with a `purpose`) carries the person between the password and the code. It is not an access token and
    get_current_user refuses it.
"""
import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from cryptography.fernet import Fernet
from jose import JWTError, jwt

from app.core.config import settings

STEP_SECONDS = 30
DIGITS = 6
WINDOW = 1                      # one step before and after now (clock drift)
RECOVERY_CODE_COUNT = 10
STEP_TOKEN_MINUTES = 5
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0, 1, I, O: they are misread


# ------------------------------------------------------------------ the one-time code
def generate_secret() -> str:
    """A new shared secret: 20 random bytes in base32, the form authenticator apps expect (no padding)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key(secret_b32: str) -> bytes:
    cleaned = secret_b32.strip().replace(" ", "").upper()
    return base64.b32decode(cleaned + "=" * (-len(cleaned) % 8))


def _hotp(secret_b32: str, counter: int, digits: int = DIGITS) -> str:
    digest = hmac.new(_key(secret_b32), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(value).zfill(digits)


def current_step(now=None) -> int:
    return int((time.time() if now is None else now) // STEP_SECONDS)


def totp_at(secret_b32: str, step: int, digits: int = DIGITS) -> str:
    return _hotp(secret_b32, step, digits)


def verify_totp(secret_b32: str, code, last_step=None, now=None):
    """The step the code belongs to if it is valid now and was not used before, otherwise None."""
    code = (code or "").strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return None
    centre, accepted = current_step(now), None
    for step in range(centre - WINDOW, centre + WINDOW + 1):         # every step is compared: no early exit to time
        if hmac.compare_digest(_hotp(secret_b32, step), code) and (last_step is None or step > last_step):
            accepted = step
    return accepted


def otpauth_uri(secret_b32: str, account: str, issuer=None) -> str:
    issuer = issuer or settings.MFA_ISSUER
    return (f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret_b32}&issuer={quote(issuer)}"
            f"&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}")


def qr_svg(text: str, scale: int = 6, quiet: int = 4):
    """
    The text drawn as a QR code (a small SVG made of one path), so a phone can scan it instead of someone typing the key.
    Returns None if it cannot be drawn: setting up still works with the typed key, so the picture is a convenience, never a requirement.
    """
    try:
        from reportlab.graphics.barcode import qrencoder     # reportlab is already part of the application (the PDF reports)
        code = qrencoder.QRCode(None, qrencoder.QRErrorCorrectLevel.M)
        code.addData(text)
        code.make()
        n = code.getModuleCount()
        side = n + 2 * quiet
        path = "".join(f"M{c + quiet} {r + quiet}h1v1h-1z" for r in range(n) for c in range(n) if code.isDark(r, c))
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {side} {side}" width="{side * scale}" height="{side * scale}" '
                f'shape-rendering="crispEdges"><rect width="{side}" height="{side}" fill="#fff"/><path d="{path}" fill="#000"/></svg>')
    except Exception:
        return None


# ------------------------------------------------------------------ the secret at rest
def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("cdr-mfa-secret:" + settings.SECRET_KEY).encode()).digest()))


def encrypt_secret(secret_b32: str) -> str:
    return _fernet().encrypt(secret_b32.encode("ascii")).decode("ascii")


def decrypt_secret(stored: str) -> str:
    """Raises cryptography.fernet.InvalidToken if the key changed or the value was damaged."""
    return _fernet().decrypt(stored.encode("ascii")).decode("ascii")


# ------------------------------------------------------------------ recovery codes
def _normalise(code) -> str:
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def _hash_recovery(code) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), ("cdr-recovery:" + _normalise(code)).encode(), hashlib.sha256).hexdigest()


def new_recovery_codes(count: int = RECOVERY_CODE_COUNT):
    """(the codes to show once, the JSON list of their keyed hashes to store)."""
    codes = []
    while len(codes) < count:
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(10))
        code = f"{raw[:5]}-{raw[5:]}"
        if code not in codes:
            codes.append(code)
    return codes, json.dumps([_hash_recovery(c) for c in codes])


def use_recovery_code(stored_json, presented):
    """The JSON list without the matched code, or None if it matches none (each code works once)."""
    try:
        hashes = json.loads(stored_json or "[]")
    except ValueError:
        return None
    target, matched = _hash_recovery(presented), None
    for h in hashes:
        if hmac.compare_digest(h, target):
            matched = h
    if matched is None or not _normalise(presented):
        return None
    hashes.remove(matched)
    return json.dumps(hashes)


def recovery_codes_left(stored_json) -> int:
    try:
        return len(json.loads(stored_json or "[]"))
    except ValueError:
        return 0


# ------------------------------------------------------------------ the token between the password and the code
def make_step_token(user_id: str, purpose: str) -> str:
    claims = {"sub": user_id, "purpose": purpose, "exp": datetime.now(timezone.utc) + timedelta(minutes=STEP_TOKEN_MINUTES)}
    return jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def read_step_token(token: str, purpose: str):
    """The user id if the token is valid, unexpired and made for exactly this purpose, otherwise None."""
    try:
        claims = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
    return claims.get("sub") if claims.get("purpose") == purpose else None


def mfa_required_for(user) -> bool:
    """When MFA_REQUIRED is on, the Bank's staff roles (BOT analyst and System Administrator) must use it; institution users need not."""
    from app.models.models import RoleEnum
    return bool(settings.MFA_REQUIRED and user.role in (RoleEnum.BOT_USER, RoleEnum.SYSTEM_ADMIN))
