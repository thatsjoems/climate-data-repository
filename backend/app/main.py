"""
Climate Data Repository (CDR) - Bank of Tanzania
Entry point ya backend (FastAPI application).

Run: uvicorn app.main:app --reload
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, engine
from app.models import models  # noqa: F401 - inahakikisha tables zote zime-register kwenye Base
from app.api import auth, users, institutions, templates, submissions, analytics, audit

# Tengeneza majedwali ya database kama hayapo bado (kwa SQLite/dev quick-start).
# Kwa uzalishaji halisi (production), tumia migrations badala ya hii.
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Prototype ya mfumo wa CDR - imejengwa kwa ajili ya EASTC 8-Week Practical Training",
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
