"""
Shared slowapi Limiter instance.

Kept in its own module (not defined inline in main.py) so that endpoint
modules needing a tighter, per-route limit - e.g. login - can import the
same Limiter without a circular import back to main.py, which is what
wires this instance into the FastAPI app itself.
"""
import logging

from fastapi import HTTPException, Request
from limits import parse
from limits.strategies import FixedWindowRateLimiter
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


# ---- The general limit ----
# slowapi's own middleware used to apply GENERAL_LIMIT to every route. It finds a route's handler by walking the application's route list, and FastAPI 0.143
# (Starlette 1.x) keeps included routers as one object without an `endpoint`, so the middleware found no handler and silently applied NOTHING (only the limits
# written on a route with @limiter.limit still worked). The general limit is therefore applied here, as a dependency of the whole application: it runs after FastAPI
# has chosen the route, so the route is known for certain. tests/test_rate_limit_per_user.py would fail if it ever stopped working.
_general_item = parse(GENERAL_LIMIT)
_general_strategy = FixedWindowRateLimiter(limiter._storage)      # the same storage as the route limits, so the test helper that resets the limiter resets this too


def _route_name(request: Request) -> str:
    route = request.scope.get("route")
    endpoint = getattr(route, "endpoint", None)
    return f"{endpoint.__module__}.{endpoint.__name__}" if endpoint is not None else ""


async def enforce_general_limit(request: Request) -> None:
    if not limiter.enabled:
        return
    name = _route_name(request)
    if name and (name in limiter._route_limits or name in limiter._exempt_routes):
        return                                                      # a route with its own limit (or none on purpose) is handled by slowapi's decorator
    if not _general_strategy.hit(_general_item, "general", caller_key(request)):
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded: {GENERAL_LIMIT.replace('/', ' per 1 ')}", headers={"Retry-After": "60"})

