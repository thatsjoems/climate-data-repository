"""
Shared pytest fixtures for the CDR backend test suite.

Uses an isolated in-memory SQLite database per test (never the real cdr.db),
so tests never touch real/demo data and can run in any order.

NOTE: importing app.main also triggers its own Base.metadata.create_all()
against whatever DATABASE_URL is configured for the app (SQLite by default) -
that is a harmless side effect (an empty/unused table set) and is unrelated to
the isolated in-memory database these fixtures actually test against.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.models.models import User, Institution, RoleEnum, InstitutionType

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
