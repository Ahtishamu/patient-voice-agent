"""
Database engine + session configuration.

Uses SQLite by default (file-based, zero-setup, survives restarts because the
.db file lives on disk). Swappable for Postgres by changing DATABASE_URL --
the rest of the code (SQLAlchemy ORM) does not need to change.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool

# Use in-memory DB on Railway (ephemeral), or ./patients.db locally
db_path = os.getenv("DATABASE_URL", None)
if not db_path:
    # Default: use in-memory SQLite on Railway, or local ./patients.db otherwise
    if os.getenv("RAILWAY_ENVIRONMENT_ID"):
        # In-memory database: data is lost on container restart, but that's fine for demo/Railway
        db_path = "sqlite:///:memory:"
    else:
        db_path = "sqlite:///./patients.db"

DATABASE_URL = db_path

engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
    if ":memory:" in DATABASE_URL:
        # In-memory SQLite is per-connection by default, which would give
        # every request a fresh empty DB. StaticPool forces all sessions to
        # share the single in-memory connection (used by the test suite).
        engine_kwargs["poolclass"] = StaticPool

engine = create_engine(DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables if they don't already exist. Safe to call repeatedly."""
    from app import models  # noqa: F401  (ensures models are registered on Base)
    Base.metadata.create_all(bind=engine)
