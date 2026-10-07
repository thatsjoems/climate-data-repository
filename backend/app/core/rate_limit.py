"""
Shared slowapi Limiter instance.

Kept in its own module (not defined inline in main.py) so that endpoint
modules needing a tighter, per-route limit - e.g. login - can import the
same Limiter without a circular import back to main.py, which is what
wires this instance into the FastAPI app itself.
"""
from slowapi import Limiter
from app.core.client_ip import client_ip, validate_trusted_proxies

validate_trusted_proxies()   # a mistake in TRUSTED_PROXIES stops the application at start-up

# The bucket of a request is the REAL caller's address (behind the production proxy the connection address is always the proxy's).
limiter = Limiter(key_func=client_ip, default_limits=["200/minute"])
