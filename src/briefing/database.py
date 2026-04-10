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

    # Migrate existing tables — add columns that may be missing
    _migrate(_engine)


def _migrate(engine) -> None:
    """Add columns that may be missing from older databases."""
    import logging
    from sqlalchemy import text, inspect

    logger = logging.getLogger(__name__)
    inspector = inspect(engine)

    migrations = [
        ("news_articles", "related_tickers", 'ALTER TABLE news_articles ADD COLUMN related_tickers TEXT DEFAULT "[]"'),
        ("news_articles", "collected_at", "ALTER TABLE news_articles ADD COLUMN collected_at DATETIME DEFAULT CURRENT_TIMESTAMP"),
    ]

    with engine.connect() as conn:
        for table, column, sql in migrations:
            if table not in inspector.get_table_names():
                continue
            existing = [c["name"] for c in inspector.get_columns(table)]
            if column not in existing:
                logger.info("Migrating: adding %s.%s", table, column)
                conn.execute(text(sql))
        conn.commit()


def get_session() -> Session:
    """Get a new database session."""
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _SessionLocal()
