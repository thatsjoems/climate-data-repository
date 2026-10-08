"""
API keys for external systems (QGIS, ArcGIS, TMA, PMO, BSIS, RTIS ...): read-only access to APPROVED data,
with no person signed in. Nothing here can write, and a key is accepted only by the /integration endpoints.

A key looks like  cdrk_<10 hex characters>_<43 random characters>.  The first part (the prefix) identifies the
row; the whole key is hashed with SHA-256 and compared in constant time. The key is shown once at creation and
never stored. Every refusal gives the same answer (a caller must not learn whether a prefix exists, or whether a
key is expired or revoked) while the audit log records the real reason.
"""
import hmac
import re
import secrets
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.client_ip import client_ip, ip_allowed
from app.core.database import get_db
from app.core.security import hash_refresh_token
from app.models.models import ApiClient
from app.services.audit_service import record_audit
from app.core.timeutil import utcnow

KEY_PATTERN = re.compile(r"^cdrk_([0-9a-f]{10})_([A-Za-z0-9_-]{32,})$")
LAST_USED_RESOLUTION = timedelta(seconds=60)   # "last used" is written at most once a minute per key


def generate_api_key() -> tuple[str, str, str]:
    """Returns (the key, its public prefix, its hash). Only the prefix and the hash are ever stored."""
    prefix = secrets.token_hex(5)
    key = f"cdrk_{prefix}_{secrets.token_urlsafe(32)}"
    return key, prefix, hash_refresh_token(key)


def presented_key(request: Request) -> str | None:
    """The key from `Authorization: Bearer <key>` or `X-API-Key: <key>` (some GIS tools can only send one of them)."""
    auth = request.headers.get("authorization", "")
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip() or None
    return (request.headers.get("x-api-key") or "").strip() or None


def key_rate_limit_id(request: Request) -> str:
    """Rate-limit bucket: the key prefix, so one client cannot spend another one's allowance; the address otherwise."""
    match = KEY_PATTERN.match(presented_key(request) or "")
    if match:
        return f"key:{match.group(1)}"
    return f"addr:{client_ip(request)}"


def _refuse(db: Session, request: Request, reason: str, prefix: str | None) -> None:
    record_audit(
        db, None, "INTEGRATION_AUTH_FAILED", "ApiClient", None,
        f"Refused an API key ({reason}) for {request.method} {request.url.path}",
        details_json={"reason": reason, "key_prefix": prefix, "client_address": client_ip(request)},
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid, expired or revoked API key",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_api_client(request: Request, db: Session = Depends(get_db)) -> ApiClient:
    raw = presented_key(request)
    match = KEY_PATTERN.match(raw or "")
    if not match:
        _refuse(db, request, "missing or malformed", None)
    prefix = match.group(1)
    client = db.query(ApiClient).filter(ApiClient.key_prefix == prefix).first()
    if client is None:
        _refuse(db, request, "unknown key", prefix)
    if not hmac.compare_digest(client.key_hash, hash_refresh_token(raw)):
        _refuse(db, request, "wrong secret", prefix)
    if client.revoked_at is not None:
        _refuse(db, request, "revoked", prefix)
    now = utcnow()
    if client.expires_at <= now:
        _refuse(db, request, "expired", prefix)
    if client.allowed_networks and not ip_allowed(client_ip(request), client.allowed_networks):
        _refuse(db, request, "address not allowed", prefix)
    if client.last_used_at is None or now - client.last_used_at > LAST_USED_RESOLUTION:
        client.last_used_at = now
        db.commit()
    return client


KEY_SCOPES = ("READ", "INGEST_TMA", "INGEST_PMO")

# The source label stored with climate data that a key delivers. It says HOW the data arrived (with a key that a BOT
# analyst issued for TMA or for PMO), and never that TMA or PMO itself is verified as the sender: this project's rule
# is that a "verified source" label is only truthful once the sender is independently authenticated (docs/TMA_INGESTION.md).
# The sender cannot choose the label: it follows from the key. The manual upload refuses these two values.
INGEST_SOURCES = {"INGEST_TMA": "API_KEY_TMA", "INGEST_PMO": "API_KEY_PMO"}


def require_key_scope(*allowed: str):
    """A valid key that is not allowed to do THIS thing (a sending key cannot read, a reading key cannot send)."""
    def checker(request: Request, client: ApiClient = Depends(get_api_client), db: Session = Depends(get_db)) -> ApiClient:
        if client.scope not in allowed:
            record_audit(
                db, None, "INTEGRATION_AUTH_FAILED", "ApiClient", client.id,
                f"{client.name}: refused, a {client.scope} key may not {request.method} {request.url.path}",
                details_json={"reason": "scope", "key_scope": client.scope, "key_prefix": client.key_prefix},
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This key is not allowed to do that")
        return client
    return checker


read_key = require_key_scope("READ")
ingest_key = require_key_scope("INGEST_TMA", "INGEST_PMO")


def audit_integration_read(db: Session, client: ApiClient, request: Request, rows: int | None = None) -> None:
    """Every successful read is recorded: which client, which path, which filters, how many rows. Never the key."""
    query = str(request.url.query)
    record_audit(
        db, None, "INTEGRATION_READ", "ApiClient", client.id,
        f"{client.name}: GET {request.url.path}" + (f"?{query}" if query else ""),
        details_json={"path": request.url.path, "query": query or None, "rows": rows},
    )
