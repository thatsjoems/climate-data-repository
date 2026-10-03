"""
Start-up safety checks (KG-13).

The original production guard rejected only the literal "change-me". The values a
Docker deployment actually runs with - the fallback in docker-compose.yml and the
sample in .env.docker.example - are different strings, so ENVIRONMENT=production
started normally with a signing key that is public in the repository. These tests
pin the fix, including against the values really shipped in the repository so the
guard cannot silently drift out of step with them again.
"""
import re
from pathlib import Path

import pytest

from app.core.startup_checks import (
    MIN_SECRET_KEY_LENGTH,
    enforce_production_secret,
    insecure_database_url_reason,
    insecure_secret_key_reason,
    is_production,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
A_GOOD_KEY = "d41d8cd98f00b204e9800998ecf8427e5f2b9c1a7e3d6f8b0a4c2e1d9f7b3a56"   # 64 hex characters


@pytest.mark.parametrize("value", [
    "change-me",
    "CHANGE-ME",
    "change-this-to-a-long-unique-secret-before-production-use",    # docker-compose.yml fallback
    "change-me-to-a-long-random-secret",                            # .env.docker.example sample
    "prefix-change-me-suffix-padded-out-to-a-safe-length-0123456789",
    "",
    "   ",
    None,
])
def test_placeholder_or_empty_keys_are_rejected(value):
    assert insecure_secret_key_reason(value) is not None


def test_short_keys_are_rejected_even_when_not_a_placeholder():
    assert insecure_secret_key_reason("x" * (MIN_SECRET_KEY_LENGTH - 1)) is not None
    assert insecure_secret_key_reason("x" * MIN_SECRET_KEY_LENGTH) is None


def test_a_long_random_key_is_accepted():
    assert insecure_secret_key_reason(A_GOOD_KEY) is None


# ---- DATABASE_URL guard (item 2 of the external review) --------------------

GOOD_DB_URL = "postgresql://cdr_app:8f3a1c9d7e2b4f6a0c1d8e9f2a3b4c5d@10.20.30.40:5432/cdr_prod"


@pytest.mark.parametrize("url", [
    "postgresql://postgres:cdr_dev_only_change_me@db:5432/climate_data_repository",  # docker-compose.yml default
    "sqlite:///./cdr.db",
    "sqlite:///:memory:",
    "",
    None,
    "postgresql://postgres:change-me@db:5432/x",
    "postgresql://postgres:secret@localhost:5432/x",
])
def test_insecure_database_urls_are_rejected(url):
    assert insecure_database_url_reason(url) is not None


def test_a_real_production_database_url_is_accepted():
    assert insecure_database_url_reason(GOOD_DB_URL) is None


def test_production_refuses_to_start_with_the_shipped_database_default():
    with pytest.raises(SystemExit) as exc:
        enforce_production_secret("production", A_GOOD_KEY, "postgresql://postgres:cdr_dev_only_change_me@db:5432/climate_data_repository")
    assert "DATABASE_URL" in str(exc.value)


def test_production_starts_with_a_good_key_and_a_good_database_url():
    assert enforce_production_secret("production", A_GOOD_KEY, GOOD_DB_URL) is None


def test_database_url_check_is_skipped_when_not_supplied():
    """Callers that only care about the signing key (or predate this check) still work unmodified."""
    assert enforce_production_secret("production", A_GOOD_KEY) is None


def test_the_shipped_docker_compose_default_is_rejected_directly():
    """Guards specifically against the literal default in docker-compose.yml, read from the repository when available."""
    compose = REPO_ROOT / "docker-compose.yml"
    if not compose.exists():
        pytest.skip("repository root files are not available here (for example inside the backend image)")
    import re
    m = re.search(r"POSTGRES_PASSWORD:\s*\$\{POSTGRES_PASSWORD:-([^}]+)\}", compose.read_text(encoding="utf-8"))
    assert m, "could not find the POSTGRES_PASSWORD default in docker-compose.yml"
    shipped_password = m.group(1).strip()
    url_with_shipped_password = f"postgresql://postgres:{shipped_password}@db:5432/climate_data_repository"
    assert insecure_database_url_reason(url_with_shipped_password) is not None


def test_production_refuses_to_start_with_an_unacceptable_key():
    with pytest.raises(SystemExit) as exc:
        enforce_production_secret("production", "change-me")
    assert "SECRET_KEY" in str(exc.value)


def test_production_starts_with_an_acceptable_key():
    assert enforce_production_secret("production", A_GOOD_KEY) is None


def test_other_environments_are_not_affected():
    assert enforce_production_secret("development", "change-me") is None
    assert enforce_production_secret(None, "change-me") is None


@pytest.mark.parametrize("environment", ["Production", " PRODUCTION ", "production\n"])
def test_the_environment_name_is_case_and_whitespace_insensitive(environment):
    assert is_production(environment)
    with pytest.raises(SystemExit):
        enforce_production_secret(environment, "change-me")


def _shipped_secret_placeholders():
    """The SECRET_KEY values that ship in the repository (skipped if the files are not present)."""
    found = {}
    compose = REPO_ROOT / "docker-compose.yml"
    if compose.exists():
        m = re.search(r"SECRET_KEY:\s*\$\{SECRET_KEY:-([^}]+)\}", compose.read_text(encoding="utf-8"))
        if m:
            found["docker-compose.yml fallback"] = m.group(1).strip()
    sample = REPO_ROOT / ".env.docker.example"
    if sample.exists():
        m = re.search(r"^SECRET_KEY=(.+)$", sample.read_text(encoding="utf-8"), re.MULTILINE)
        if m:
            found[".env.docker.example"] = m.group(1).strip()
    return found


def test_every_secret_placeholder_shipped_in_the_repository_is_rejected_in_production():
    shipped = _shipped_secret_placeholders()
    if not shipped:
        pytest.skip("repository root files are not available here (for example inside the backend image)")
    for name, value in shipped.items():
        assert insecure_secret_key_reason(value) is not None, f"{name} would start in production"
        with pytest.raises(SystemExit):
            enforce_production_secret("production", value)


def test_the_application_default_secret_is_rejected_in_production():
    from app.core.config import Settings
    default = Settings.model_fields["SECRET_KEY"].default
    with pytest.raises(SystemExit):
        enforce_production_secret("production", default)
