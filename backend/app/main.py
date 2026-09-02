"""
Climate Data Repository (CDR) - Bank of Tanzania
Backend entry point (FastAPI application).

Run: uvicorn app.main:app --reload
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, engine
from app.models import models  # noqa: F401 - ensures all tables are registered on Base
from app.api import auth, users, institutions, templates, submissions, analytics, audit

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


@app.get("/")
def root():
    return {
        "project": settings.PROJECT_NAME,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/api/health")
def health_check():
    return {"status": "ok"}
