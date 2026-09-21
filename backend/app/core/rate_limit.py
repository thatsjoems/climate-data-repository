"""
Shared slowapi Limiter instance.

Kept in its own module (not defined inline in main.py) so that endpoint
modules needing a tighter, per-route limit - e.g. login - can import the
same Limiter without a circular import back to main.py, which is what
wires this instance into the FastAPI app itself.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
