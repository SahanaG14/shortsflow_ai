"""Local SQLite storage for the connected channel's uploaded videos."""

import sqlite3
from pathlib import Path


def initialize_database(database_file: Path) -> None:
    with sqlite3.connect(database_file) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                youtube_video_id TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                published_at TEXT NOT NULL,
                thumbnail_url TEXT NOT NULL DEFAULT '',
                synced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def upsert_videos(database_file: Path, videos: list[dict[str, str]]) -> tuple[int, int]:
    """Insert new videos and refresh metadata for already-stored videos."""
    inserted = 0
    updated = 0
    with sqlite3.connect(database_file) as connection:
        for video in videos:
            existing = connection.execute(
                "SELECT 1 FROM videos WHERE youtube_video_id = ?",
                (video["youtube_video_id"],),
            ).fetchone()
            if existing:
                connection.execute(
                    """
                    UPDATE videos
                    SET title = ?, description = ?, published_at = ?, thumbnail_url = ?,
                        synced_at = CURRENT_TIMESTAMP
                    WHERE youtube_video_id = ?
                    """,
                    (
                        video["title"],
                        video["description"],
                        video["published_at"],
                        video["thumbnail_url"],
                        video["youtube_video_id"],
                    ),
                )
                updated += 1
            else:
                connection.execute(
                    """
                    INSERT INTO videos (youtube_video_id, title, description, published_at, thumbnail_url)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        video["youtube_video_id"],
                        video["title"],
                        video["description"],
                        video["published_at"],
                        video["thumbnail_url"],
                    ),
                )
                inserted += 1
    return inserted, updated


def list_videos(database_file: Path) -> list[dict[str, str]]:
    with sqlite3.connect(database_file) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT youtube_video_id, title, description, published_at, thumbnail_url
            FROM videos
            ORDER BY published_at DESC, id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def video_count(database_file: Path) -> int:
    with sqlite3.connect(database_file) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM videos").fetchone()[0])
