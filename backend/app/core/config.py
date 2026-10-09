"""
Application configuration.
All sensitive values are read from the .env file - never hardcoded here.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Climate Data Repository (CDR) - Bank of Tanzania"
    API_V1_PREFIX: str = "/api"

    DATABASE_URL: str = "sqlite:///./cdr.db"

    SECRET_KEY: str = "change-me"
    ALGORITHM: str = "HS256"
    # Short-lived on purpose (Module: session security). A stolen access token
    # is now only useful for a small window; long-lived sessions are handled
    # by the refresh token below instead, which can be revoked server-side -
    # something a stateless JWT alone can never support.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    UPLOAD_DIR: str = "uploads"

    # File upload hardening (Module F: Data Quality & Validation) - prevents a
    # single oversized/malformed file from exhausting server memory or CPU.
    MAX_UPLOAD_SIZE_MB: int = 20
    MAX_UPLOAD_ROWS: int = 100000

    # Login brute-force protection (Module A: secure authentication).
    MAX_FAILED_LOGIN_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15
    # Networks of the reverse proxy in front of the backend (comma-separated). Only a request that comes from one of them has
    # its X-Forwarded-For believed (see app/core/client_ip.py). Empty = no proxy: the connection address is used.
    TRUSTED_PROXIES: str = ""
    # The rate limits (sign-in and the general ceiling). Only staging switches them off, for load tests: the production checker refuses it there.
    RATE_LIMIT_ENABLED: bool = True
    # Monitoring (see docs/MONITORING.md). 0 = the background monitor is off (development and the tests); production runs it every 10 minutes.
    MONITOR_INTERVAL_MINUTES: int = 0
    BACKUP_STATUS_DIR: str = "/backup-status"        # where the backup task leaves its result (mounted read-only into the backend)
    BACKUP_MAX_AGE_HOURS: float = 26
    BACKUP_MONITORING: bool = True                   # False for staging, which has no backup task
    ALERT_SIGNIN_FAILURES_WARN: int = 10             # failed sign-in steps in the last hour
    ALERT_SIGNIN_FAILURES_CRITICAL: int = 30
    ALERT_DISK_FREE_WARN_PERCENT: int = 20
    ALERT_DISK_FREE_CRITICAL_PERCENT: int = 10
    # Two-step sign-in (a code from an authenticator app). When on, BOT analysts and System Administrators must enrol at their next sign-in;
    # anyone who has enrolled uses it regardless. Off by default (development, demonstration, tests); the production Compose file turns it on.
    MFA_REQUIRED: bool = False
    MFA_ISSUER: str = "Climate Data Repository (BOT)"   # the name the authenticator app shows

    # Bank internal systems (see docs/INTEGRATION_ACCESS.md, "RTIS and BSIS"). Empty base URL = not connected. The Bank's ICT
    # department supplies the address, the credential and the health-check path of each system; nothing else is assumed here.
    RTIS_BASE_URL: str = ""
    RTIS_API_KEY: str = ""
    RTIS_HEALTH_PATH: str = "/health"
    BSIS_BASE_URL: str = ""
    BSIS_API_KEY: str = ""
    BSIS_HEALTH_PATH: str = "/health"
    EXTERNAL_SYSTEM_TIMEOUT_SECONDS: float = 5.0

    # Set to "production" to make the app refuse to start with an insecure
    # default SECRET_KEY - see main.py startup check.
    ENVIRONMENT: str = "development"

    # Optional SMTP configuration for automatically emailing approved credentials.
    # If SMTP_HOST is left empty, the system falls back to showing the credentials
    # once to the approving Admin, who relays them manually (no crash, no silent data loss).
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_USE_TLS: bool = True

    # Allow the frontend (Vite dev server) to talk to this backend during development
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
