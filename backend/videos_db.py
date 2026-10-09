"""PostgreSQL storage operations for the connected channel's uploaded videos."""

from sqlalchemy import func, select

from database import Video, session_scope


def upsert_videos(videos: list[dict[str, str]]) -> tuple[int, int]:
    """Insert new videos and refresh metadata for already-stored videos."""
    inserted = 0
    updated = 0
    with session_scope() as session:
        for video in videos:
            existing = session.scalar(
                select(Video).where(Video.youtube_video_id == video["youtube_video_id"])
            )
            if existing:
                existing.title = video["title"]
                existing.description = video["description"]
                existing.published_at = video["published_at"]
                existing.thumbnail_url = video["thumbnail_url"]
                updated += 1
            else:
                session.add(Video(**video))
                # Make newly inserted IDs visible to later entries in this same
                # YouTube playlist response, which can contain repeated videos.
                session.flush()
                inserted += 1
    return inserted, updated


def list_videos() -> list[dict[str, str]]:
    with session_scope() as session:
        videos = session.scalars(
            select(Video).order_by(Video.published_at.desc(), Video.id.desc())
        ).all()
        return [
            {
                "youtube_video_id": video.youtube_video_id,
                "title": video.title,
                "description": video.description,
                "published_at": video.published_at,
                "thumbnail_url": video.thumbnail_url,
            }
            for video in videos
        ]


def video_count() -> int:
    with session_scope() as session:
        return int(session.scalar(select(func.count()).select_from(Video)) or 0)
