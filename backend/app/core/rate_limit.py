"""
Shared slowapi Limiter instance.

Kept in its own module (not defined inline in main.py) so that endpoint
modules needing a tighter, per-route limit - e.g. login - can import the
same Limiter without a circular import back to main.py, which is what
wires this instance into the FastAPI app itself.
"""
import logging

from slowapi import Limiter

from app.core.client_ip import client_ip, validate_trusted_proxies
from app.core.config import settings
from app.core.security import decode_access_token

validate_trusted_proxies()   # a mistake in TRUSTED_PROXIES stops the application at start-up

# What every route is allowed unless it has a stricter limit of its own (sign-in, two-step, password-reset requests, token refresh, the integration endpoints).
GENERAL_LIMIT = "300/minute"


def caller_key(request) -> str:
    """
    The bucket a request is counted in: the SIGNED-IN PERSON (from a valid, unexpired access token), otherwise the real caller's address.

    Why a person and not only an address. Counted by address alone, everybody in an office behind one address (the Bank's network) shared one allowance, so a
    busy minute of analysts opening dashboards (about ten requests a page) could stop all of them although none had done anything wrong. Why only a VALID
    token: the signature is checked here, so nobody can spend another person's allowance by putting that person's id in a made-up token; such a request is
    counted against the sender's own address instead. Behind the production proxy the address is the real caller's (docs/NETWORK_ACCESS.md), never the proxy's.
    """
    header = request.headers.get("authorization", "")
    if header[:7].lower() == "bearer ":
        claims = decode_access_token(header[7:].strip())
        person = claims.get("sub") if isinstance(claims, dict) else None
        if person:
            return f"user:{person}"
    return client_ip(request)


limiter = Limiter(key_func=caller_key, default_limits=[GENERAL_LIMIT], enabled=settings.RATE_LIMIT_ENABLED)
if not settings.RATE_LIMIT_ENABLED:
    logging.getLogger(__name__).warning("RATE_LIMIT_ENABLED is false: no rate limit is applied. This is for staging load tests only; production must never run like this.")
