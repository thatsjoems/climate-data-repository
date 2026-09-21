"""
Climate Data Repository (CDR) - Bank of Tanzania
Backend entry point (FastAPI application).

Run: uvicorn app.main:app --reload
"""
import logging
import sys
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.rate_limit import limiter
from app.core.logging_config import configure_logging

configure_logging()
logger = logging.getLogger("cdr.request")
from app.models import models  # noqa: F401 - ensures all tables are registered on Base
from app.api import auth, users, institutions, templates, submissions, analytics, audit, notifications, password_reset, risk_advisories, reports, climate_data

# ---- Secret management: refuse to start in production with the default secret ----
# (Module: secure authentication). Development/training use is unaffected - this
# only fires when ENVIRONMENT=production is explicitly set, e.g. in a real deployment.
if settings.ENVIRONMENT == "production" and settings.SECRET_KEY == "change-me":
    sys.exit(
        "FATAL: SECRET_KEY is still the insecure default ('change-me') while "
        "ENVIRONMENT=production. Set a long, unique SECRET_KEY in your environment "
        "before starting the server. Refusing to start."
    )

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="CDR prototype system - built as part of the EASTC 8-Week Practical Training Programme",
    version="0.1.0",
)

# ---- Rate limiting (Module: secure authentication / API hardening) ----
# Per-account lockout (see auth.py) already stops repeated guesses against ONE
# username. This adds a per-IP ceiling on top - the gap a lockout alone can't
# close, since a single IP trying many different usernames never trips any one
# account's lockout. In-memory storage is enough at this deployment's scale;
# a shared store (e.g. Redis) would only be needed across multiple backend
# replicas, which this project does not run.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers_middleware(request, call_next):
    """
    Baseline security headers (Section 14/17). Kept minimal and safe for an
    API-only backend behind a separate frontend origin - no CSP is set here
    since this backend serves JSON, not HTML, and a wrong CSP could break the
    Swagger UI at /docs.
    """
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


@app.middleware("http")
async def request_logging_middleware(request, call_next):
    """
    One structured log line per request (Module: observability) - method,
    path, status, and duration. Never logs the request body (avoids ever
    writing a password or file contents to logs); the audit log remains the
    place for "who did what to which record", this is "how did the API
    itself behave".
    """
    started = time.monotonic()
    response = await call_next(request)
    duration_ms = round((time.monotonic() - started) * 1000, 1)
    logger.info(
        "request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response

app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(users.router, prefix=settings.API_V1_PREFIX)
app.include_router(institutions.router, prefix=settings.API_V1_PREFIX)
app.include_router(templates.router, prefix=settings.API_V1_PREFIX)
app.include_router(submissions.router, prefix=settings.API_V1_PREFIX)
app.include_router(analytics.router, prefix=settings.API_V1_PREFIX)
app.include_router(audit.router, prefix=settings.API_V1_PREFIX)
app.include_router(notifications.router, prefix=settings.API_V1_PREFIX)
app.include_router(password_reset.router, prefix=settings.API_V1_PREFIX)
app.include_router(risk_advisories.router, prefix=settings.API_V1_PREFIX)
app.include_router(reports.router, prefix=settings.API_V1_PREFIX)
app.include_router(climate_data.router, prefix=settings.API_V1_PREFIX)


@app.get("/")
def root():
    return {
        "project": settings.PROJECT_NAME,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/api/health")
def health_check():
    """
    Reports 'ok' only if the database is actually reachable - a bare 200 with
    no dependency check would be misleading during an outage.
    """
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            db_status = "ok"
        finally:
            db.close()
    except Exception as exc:
        db_status = f"unreachable: {exc}"

    overall = "ok" if db_status == "ok" else "degraded"
    return {"status": overall, "database": db_status}
