"""
Start-up safety checks (KG-13).

The original guard refused to start in production only when SECRET_KEY was the
literal string "change-me". But the values a Docker deployment actually runs
with are different: the fallback in docker-compose.yml and the sample in
.env.docker.example. Neither equals "change-me", so ENVIRONMENT=production
started normally with a signing key that is public in the repository - anyone
who knew it could forge access tokens. This module closes that gap.

Kept free of framework imports so it can be unit-tested in isolation.
"""
from typing import Optional

# Fragments that identify a placeholder rather than a real secret. A substring test
# (not an exact match) is used so that the shipped values and any lightly edited
# copy of them are all caught.
PLACEHOLDER_FRAGMENTS = ("change-me", "change-this", "changeme", "your-secret", "example", "secret-key-here")

# Signing keys shorter than this are refused in production. 32 characters is the
# minimum for an HS256 key; `secrets.token_hex(32)` (as .env.docker.example
# suggests) yields 64.
MIN_SECRET_KEY_LENGTH = 32


def insecure_secret_key_reason(secret_key: Optional[str]) -> Optional[str]:
    """Why this SECRET_KEY must not be used in production, or None if it is acceptable."""
    if secret_key is None or not secret_key.strip():
        return "SECRET_KEY is empty"
    lowered = secret_key.strip().lower()
    for fragment in PLACEHOLDER_FRAGMENTS:
        if fragment in lowered:
            return f"SECRET_KEY is a placeholder value (it contains '{fragment}')"
    if len(secret_key.strip()) < MIN_SECRET_KEY_LENGTH:
        return f"SECRET_KEY is shorter than {MIN_SECRET_KEY_LENGTH} characters"
    return None


def is_production(environment: Optional[str]) -> bool:
    """Case- and whitespace-insensitive, so 'Production ' cannot bypass the checks."""
    return (environment or "").strip().lower() == "production"


def insecure_database_url_reason(database_url: Optional[str]) -> Optional[str]:
    """
    Why this DATABASE_URL must not be used in production, or None if it is
    acceptable. A database credential is as much a production secret as the
    JWT signing key - this exists because the original production guard
    checked SECRET_KEY only, so an operator who set a real signing key but
    left POSTGRES_PASSWORD at its docker-compose.yml default
    ("cdr_dev_only_change_me") would still start in production with a
    publicly known database password.
    """
    if not database_url or not database_url.strip():
        return "DATABASE_URL is empty"
    lowered = database_url.lower()
    if "sqlite" in lowered:
        return "DATABASE_URL points at SQLite, not a production-grade database"
    for fragment in PLACEHOLDER_FRAGMENTS + ("dev_only", "devonly", "localhost", "127.0.0.1"):
        if fragment.replace("-", "_") in lowered.replace("-", "_"):
            return f"DATABASE_URL contains a placeholder or local-development marker ('{fragment}')"
    return None


def enforce_production_secret(environment: Optional[str], secret_key: Optional[str], database_url: Optional[str] = None) -> None:
    """Exit the process (SystemExit) if running in production with an unacceptable key or database URL."""
    if not is_production(environment):
        return
    reason = insecure_secret_key_reason(secret_key)
    if reason:
        raise SystemExit(
            f"FATAL: {reason} while ENVIRONMENT=production. Set a long, unique SECRET_KEY in your "
            f"environment (for example: python -c \"import secrets; print(secrets.token_hex(32))\") "
            f"before starting the server. Refusing to start."
        )
    if database_url is not None:
        db_reason = insecure_database_url_reason(database_url)
        if db_reason:
            raise SystemExit(
                f"FATAL: {db_reason} while ENVIRONMENT=production. Set a unique DATABASE_URL "
                f"(including a strong POSTGRES_PASSWORD, never the docker-compose.yml default) "
                f"before starting the server. Refusing to start."
            )
