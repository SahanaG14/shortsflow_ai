"""Controlled, read-only ShortsFlow data tools for the local assistant."""

from pathlib import Path
from typing import Any, Callable

from chat_preferences import get_preferences
from content_generation import list_generated_drafts
from duplicate_detection import check_duplicate, normalize_title
from videos_db import list_videos
from youtube_oauth import YouTubeAuthenticationError, get_channel_details


BACKEND_DIRECTORY = Path(__file__).resolve().parent
CLIENT_SECRETS_FILE = BACKEND_DIRECTORY / "client_secret.json"
TOKEN_FILE = BACKEND_DIRECTORY / "youtube_token.json"
DEFAULT_SCHEDULE_TIMES = ("09:00", "18:00", "21:00")


def get_channel_stats() -> dict[str, Any]:
    """Read current channel statistics through the existing OAuth service."""
    try:
        return get_channel_details(CLIENT_SECRETS_FILE, TOKEN_FILE)
    except YouTubeAuthenticationError:
        return {"available": False, "message": "No connected YouTube channel is available."}


def get_settings() -> dict[str, Any]:
    return get_preferences()


def get_recent_videos(limit: int = 5) -> list[dict[str, str]]:
    return list_videos()[: max(1, min(limit, 20))]


def search_existing_videos(query: str) -> list[dict[str, str]]:
    normalized_query = normalize_title(query)
    query_terms = set(normalized_query.split())
    matches: list[dict[str, str]] = []
    for video in list_videos():
        searchable = normalize_title(f"{video['title']} {video['description']}")
        if normalized_query and (normalized_query in searchable or query_terms & set(searchable.split())):
            matches.append(video)
    return matches[:10]


def check_duplicate_topic(query: str) -> dict[str, object]:
    return check_duplicate(query, query, list_videos())


def get_generated_drafts(limit: int = 5) -> list[dict[str, object]]:
    return list_generated_drafts()[: max(1, min(limit, 20))]


def get_latest_draft() -> dict[str, object] | None:
    drafts = list_generated_drafts()
    return drafts[0] if drafts else None


def get_upload_schedule() -> dict[str, object]:
    settings = get_preferences()
    configured = settings.get("videos_per_day", 1)
    count = configured if isinstance(configured, int) and configured > 0 else 1
    slots = [
        DEFAULT_SCHEDULE_TIMES[index] if index < len(DEFAULT_SCHEDULE_TIMES) else f"{(9 + index * 3) % 24:02d}:00"
        for index in range(count)
    ]
    return {"videos_per_day": count, "slots": slots, "source": "Settings UI placeholder"}


TOOL_HANDLERS: dict[str, Callable[..., object]] = {
    "get_channel_stats": get_channel_stats,
    "get_settings": get_settings,
    "get_recent_videos": get_recent_videos,
    "search_existing_videos": search_existing_videos,
    "check_duplicate": check_duplicate_topic,
    "get_generated_drafts": get_generated_drafts,
    "get_latest_draft": get_latest_draft,
    "get_upload_schedule": get_upload_schedule,
}


TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "get_channel_stats", "description": "Get current connected YouTube channel statistics.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_settings", "description": "Get permanent ShortsFlow Settings defaults.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_recent_videos", "description": "List recently synced channel videos.", "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 20}}}}},
    {"type": "function", "function": {"name": "search_existing_videos", "description": "Search existing synced videos by topic or title.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "check_duplicate", "description": "Run local duplicate detection for a proposed topic or title.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_generated_drafts", "description": "List recent generated Shorts drafts.", "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 20}}}}},
    {"type": "function", "function": {"name": "get_latest_draft", "description": "Get the newest generated Shorts draft.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_upload_schedule", "description": "Get the configured daily upload slot placeholders.", "parameters": {"type": "object", "properties": {}}}},
]


def call_tool(name: str, arguments: dict[str, object] | None = None) -> object:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        raise ValueError(f"Unknown assistant tool: {name}")
    return handler(**(arguments or {}))
