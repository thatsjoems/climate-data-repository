"""
Mipangilio mikuu ya mfumo (Configuration).
Thamani zote nyeti (siri) zinasomwa kutoka faili ya .env - HAZIWEKWI hapa moja kwa moja.
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

    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
