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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    UPLOAD_DIR: str = "uploads"

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
