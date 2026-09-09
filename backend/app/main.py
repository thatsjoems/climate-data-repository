"""
Climate Data Repository (CDR) - Bank of Tanzania
Backend entry point (FastAPI application).

Run: uvicorn app.main:app --reload
"""
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.database import Base, engine, SessionLocal
from app.models import models  # noqa: F401 - ensures all tables are registered on Base
from app.api import auth, users, institutions, templates, submissions, analytics, audit, notifications, password_reset, risk_advisories, reports

# ---- Secret management: refuse to start in production with the default secret ----
# (Module: secure authentication). Development/training use is unaffected - this
# only fires when ENVIRONMENT=production is explicitly set, e.g. in a real deployment.
if settings.ENVIRONMENT == "production" and settings.SECRET_KEY == "change-me":
    sys.exit(
        "FATAL: SECRET_KEY is still the insecure default ('change-me') while "
        "ENVIRONMENT=production. Set a long, unique SECRET_KEY in your environment "
        "before starting the server. Refusing to start."
    )

# Create database tables if they do not already exist (quick-start for SQLite/dev).
# For real production use, use migrations instead of this.
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="CDR prototype system - built as part of the EASTC 8-Week Practical Training Programme",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
