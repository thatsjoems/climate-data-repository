"""
Database connection (SQLAlchemy engine + session).
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    # SQLite needs this to work correctly with FastAPI (multi-threaded)
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency that provides a database session per request and closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
