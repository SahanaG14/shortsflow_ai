"""Central PostgreSQL configuration and SQLAlchemy models for ShortsFlow AI."""

import os
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import DateTime, Integer, String, Text, create_engine, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine, URL
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


load_dotenv(Path(__file__).resolve().parent / ".env")


class DatabaseConfigurationError(RuntimeError):
    """Raised when the required PostgreSQL connection string is not configured."""


class Base(DeclarativeBase):
    pass


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    youtube_video_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[str] = mapped_column(String(64))
    thumbnail_url: Mapped[str] = mapped_column(Text, default="")
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChannelPreferences(Base):
    __tablename__ = "channel_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    preferences: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


def database_url() -> str:
    """Build a PostgreSQL URL from environment variables without logging credentials."""
    configured_url = os.getenv("DATABASE_URL")
    if configured_url:
        if not configured_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise DatabaseConfigurationError("DATABASE_URL must use a PostgreSQL connection URL.")
        return configured_url

    settings = {
        "DATABASE_HOST": os.getenv("DATABASE_HOST"),
        "DATABASE_PORT": os.getenv("DATABASE_PORT"),
        "DATABASE_NAME": os.getenv("DATABASE_NAME"),
        "DATABASE_USER": os.getenv("DATABASE_USER"),
        "DATABASE_PASSWORD": os.getenv("DATABASE_PASSWORD"),
    }
    missing = [name for name, value in settings.items() if not value]
    if missing:
        raise DatabaseConfigurationError(
            "Missing PostgreSQL settings: " + ", ".join(missing) + "."
        )
    try:
        port = int(str(settings["DATABASE_PORT"]))
    except ValueError as error:
        raise DatabaseConfigurationError("DATABASE_PORT must be a valid integer.") from error
    return URL.create(
        "postgresql+psycopg",
        username=str(settings["DATABASE_USER"]),
        password=str(settings["DATABASE_PASSWORD"]),
        host=str(settings["DATABASE_HOST"]),
        port=port,
        database=str(settings["DATABASE_NAME"]),
    ).render_as_string(hide_password=False)


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(database_url(), pool_pre_ping=True)
    return _engine


def _session_factory_for_database() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _session_factory


def initialize_database() -> None:
    """Create the application's PostgreSQL tables when the backend starts."""
    Base.metadata.create_all(get_engine())


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Yield a transactional SQLAlchemy session and roll back on failures."""
    session = _session_factory_for_database()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
