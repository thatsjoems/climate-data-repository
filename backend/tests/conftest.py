"""
Shared pytest fixtures for the CDR backend test suite.

Uses an isolated in-memory SQLite database per test (never the real cdr.db),
so tests never touch real/demo data and can run in any order.

NOTE: the application no longer creates production tables as an import side
effect. Tests intentionally create the isolated in-memory schema directly from
SQLAlchemy metadata so each test remains independent of Alembic and real data.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.core.rate_limit import limiter
from app.core.security import hash_password
from app.models.models import User, Institution, RoleEnum, InstitutionType

# `limiter` is a module-level singleton (app/core/rate_limit.py), wired into
# `app` once at import time (main.py: `app.state.limiter = limiter`) and never
# recreated per test. Every test in the whole session shares its counters -
# with ~300 login() calls across the suite against the 10/minute login limit,
# tests later in the run got HTTP 429 instead of the response they were
# actually testing, cascading into unrelated-looking failures (KeyError on
# "access_token", then anything built on that token). No test in this suite
# asserts on 429 itself, so disabling the limiter for the whole session is
# safe and keeps this fixture set from becoming a second thing every future
# test has to remember to reset.
limiter.enabled = False

TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


@pytest.fixture()
def db_session():
    Base.metadata.create_all(bind=TEST_ENGINE)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=TEST_ENGINE)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers for building test data
# ---------------------------------------------------------------------------

DEFAULT_PASSWORD = "Passw0rd!23"


def make_institution(db, code="BANK-A", name="Bank A Ltd"):
    inst = Institution(code=code, name=name, type=InstitutionType.BANK)
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return inst


def make_user(db, role=RoleEnum.INSTITUTION_USER, institution=None, username="user1", password=DEFAULT_PASSWORD):
    # The database requires an institution user to belong to an institution (ck_users_institution_user_has_institution),
    # exactly as the API does. A test that only needs "a user" no longer has to build an institution first.
    if role == RoleEnum.INSTITUTION_USER and institution is None:
        institution = make_institution(db, code=f"T-{username}"[:20], name=f"Test institution for {username}")
    user = User(
        full_name=f"Test {username}",
        username=username,
        email=f"{username}@example.com",
        hashed_password=hash_password(password),
        role=role,
        institution_id=institution.id if institution else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login(client, username, password=DEFAULT_PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
