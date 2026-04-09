from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from briefing.config import AppConfig


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def init_db(config: AppConfig) -> None:
    """Initialize the database engine and create all tables."""
    global _engine, _SessionLocal

    db_path_str = config.database.path
    if db_path_str == ":memory:":
        _engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        db_path = Path(db_path_str)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
    _SessionLocal = sessionmaker(bind=_engine)

    # Import models to register them, then create tables
    import briefing.models  # noqa: F401
    Base.metadata.create_all(bind=_engine)


def get_session() -> Session:
    """Get a new database session."""
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _SessionLocal()
