"""Central PostgreSQL configuration and SQLAlchemy models for ShortsFlow AI."""

import os
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, create_engine, func, text
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


class GeneratedDraft(Base):
    __tablename__ = "generated_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    content: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GeneratedScene(Base):
    """Metadata for deterministic visual scenes rendered for an accepted draft."""

    __tablename__ = "generated_scenes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scene_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    draft_id: Mapped[int] = mapped_column(Integer, index=True)
    scene_number: Mapped[int] = mapped_column(Integer)
    scene_type: Mapped[str] = mapped_column(String(40))
    image_path: Mapped[str] = mapped_column(Text)
    generation_status: Mapped[str] = mapped_column(String(24), default="generated")
    validation_status: Mapped[str] = mapped_column(String(24), default="pending")
    render_data: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GeneratedVideo(Base):
    """Rendered local MP4 metadata for an accepted Short draft."""

    __tablename__ = "generated_videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    render_status: Mapped[str] = mapped_column(String(24), default="pending")
    video_path: Mapped[str] = mapped_column(Text, default="")
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    validation_status: Mapped[str] = mapped_column(String(24), default="pending")
    timeline: Mapped[list[object]] = mapped_column(JSONB, default=list)
    audio_expected: Mapped[bool] = mapped_column(Boolean, default=False)
    audio_note: Mapped[str] = mapped_column(Text, default="")
    voiceover_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    voice_provider: Mapped[str] = mapped_column(String(64), default="")
    voice_gender: Mapped[str] = mapped_column(String(16), default="")
    voice_id: Mapped[str] = mapped_column(String(96), default="")
    audio_path: Mapped[str] = mapped_column(Text, default="")
    audio_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    countdown_length: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    rendered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UploadRecord(Base):
    __tablename__ = "upload_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_render_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    draft_id: Mapped[int] = mapped_column(Integer, index=True)
    youtube_video_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    hashtags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    privacy_status: Mapped[str] = mapped_column(String(24), default="private")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    upload_state: Mapped[str] = mapped_column(String(24), default="ready")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AssistantConversation(Base):
    """A separate persisted conversation stream for the read-only AI assistant."""

    __tablename__ = "assistant_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AssistantMessage(Base):
    """Conversation messages and the non-sensitive tool names used to answer them."""

    __tablename__ = "assistant_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(Integer, index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    tools_used: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
    # This project intentionally keeps local-development schema setup lightweight.
    # `create_all` does not add columns to an existing PostgreSQL table.
    video_columns = {
        "voiceover_enabled": "BOOLEAN NOT NULL DEFAULT FALSE",
        "voice_provider": "VARCHAR(64) NOT NULL DEFAULT ''",
        "voice_gender": "VARCHAR(16) NOT NULL DEFAULT ''",
        "voice_id": "VARCHAR(96) NOT NULL DEFAULT ''",
        "audio_path": "TEXT NOT NULL DEFAULT ''",
        "audio_duration_seconds": "DOUBLE PRECISION",
        "countdown_length": "INTEGER NOT NULL DEFAULT 0",
    }
    with get_engine().begin() as connection:
        for name, definition in video_columns.items():
            connection.execute(text(f"ALTER TABLE generated_videos ADD COLUMN IF NOT EXISTS {name} {definition}"))


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
