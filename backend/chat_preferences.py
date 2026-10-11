"""Local chat history and rule-based preference extraction for Shorts planning."""

import re
from collections.abc import Mapping

from sqlalchemy import delete, select

from database import ChannelPreferences, ChatMessage as ChatMessageRecord, session_scope


PREFERENCE_FIELDS = (
    "content_categories",
    "video_type",
    "video_duration_seconds",
    "aspect_ratio",
    "theme",
    "options_count",
    "thinking_timer_seconds",
    "explanation_enabled",
    "voiceover_enabled",
    "background_music_enabled",
    "logo_enabled",
    "logo_position",
    "language",
    "videos_per_day",
    "duplicate_prevention_enabled",
    "generate_title_enabled", "generate_description_enabled", "generate_hashtags_enabled",
    "manual_approval_enabled", "auto_upload_enabled", "upload_schedule_times", "timezone",
)


def get_chat_history() -> list[dict[str, str]]:
    with session_scope() as session:
        messages = session.scalars(select(ChatMessageRecord).order_by(ChatMessageRecord.id)).all()
        return [
            {
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at.isoformat(),
            }
            for message in messages
        ]


def get_preferences() -> dict[str, object]:
    """Return the permanent Settings-owned defaults."""
    with session_scope() as session:
        record = session.get(ChannelPreferences, 1)
        return dict(record.preferences) if record else {}


def save_preferences(preferences: Mapping[str, object]) -> dict[str, object]:
    """Replace permanent Settings defaults in the single preferences record."""
    sanitized = {
        field: value for field, value in preferences.items() if field in PREFERENCE_FIELDS
    }
    with session_scope() as session:
        record = session.get(ChannelPreferences, 1)
        if record:
            record.preferences = dict(sanitized)
        else:
            session.add(ChannelPreferences(id=1, preferences=dict(sanitized)))
    return sanitized


def _append_message(role: str, content: str) -> None:
    with session_scope() as session:
        session.add(ChatMessageRecord(role=role, content=content))


def _set_boolean(text: str, label: str) -> bool | None:
    if not re.search(rf"\b{label}\b", text):
        return None
    if re.search(rf"\b(no|without|disable|disabled|off|turn off)\s+{label}\b", text):
        return False
    if re.search(rf"\b(enable|enabled|with|use|show|on|turn on)\s+{label}\b", text):
        return True
    return True


def extract_preferences(message: str, existing: Mapping[str, object]) -> tuple[dict[str, object], list[str]]:
    """Apply compact, predictable local rules while retaining prior values."""
    text = message.casefold()
    preferences = dict(existing)
    changed: list[str] = []

    def update(key: str, value: object) -> None:
        if preferences.get(key) != value:
            preferences[key] = value
            changed.append(key)

    category_rules = {
        "CS": (r"\bcs\b", r"computer science", r"programming", r"software"),
        "aptitude": (r"\baptitude\b", r"reasoning", r"placement"),
        "DSA": (r"\bdsa\b", r"data structures", r"algorithms?"),
        "Java": (r"\bjava\b",),
        "SQL": (r"\bsql\b", r"database"),
    }
    found_categories = [
        name for name, patterns in category_rules.items() if any(re.search(pattern, text) for pattern in patterns)
    ]
    if found_categories:
        prior = preferences.get("content_categories", [])
        prior_categories = prior if isinstance(prior, list) else []
        update("content_categories", list(dict.fromkeys([*prior_categories, *found_categories])))

    for video_type, pattern in {
        "quiz": r"\bquiz\b|\bmcq\b|multiple choice",
        "puzzle": r"\bpuzzle\b|brain teaser",
        "explainer": r"\bexplain(?:er|ed)?\b|tutorial",
    }.items():
        if re.search(pattern, text):
            update("video_type", video_type)
            break

    for key, pattern in {
        "video_duration_seconds": r"(?:make (?:them|it)|duration(?: of| is)?|length(?: of| is)?)\s*(\d+)\s*(?:seconds?|secs?|s)\b|\b(\d+)[ -]?second(?:s)?\s+(?:shorts?|videos?)\b|(?<!timer )(?<!timer is )(?<!timer to )\b(\d+)\s*(?:seconds?|secs?|s)\b(?!\s*(?:thinking )?timer)",
        "thinking_timer_seconds": r"(\d+)\s*(?:seconds?|secs?|s)\s*(?:thinking )?timer|(?:thinking )?timer\s*(?:of|is|to)?\s*(\d+)\s*(?:seconds?|secs?|s)\b",
        "options_count": r"\b(\d+)\s*(?:options?|choices?)\b",
        "videos_per_day": r"\b(\d+)\s*videos?\s*(?:per|a)\s*day\b",
    }.items():
        match = re.search(pattern, text)
        if match:
            value = next(int(part) for part in match.groups() if part is not None)
            update(key, value)

    theme_match = re.search(r"\b(dark navy|dark|light|minimal(?:ist)?|neon|pastel)\s+theme\b", text)
    if theme_match:
        update("theme", theme_match.group(1))
    elif "theme" in text:
        generic_theme = re.search(r"\btheme\s*(?:is|to|of)?\s*([a-z][a-z -]{1,30})", text)
        if generic_theme:
            update("theme", generic_theme.group(1).strip())

    if re.search(r"\b9\s*[:x]\s*16\b|\bvertical\b|\bportrait\b", text):
        update("aspect_ratio", "9:16")
    elif re.search(r"\b16\s*[:x]\s*9\b|\blandscape\b", text):
        update("aspect_ratio", "16:9")

    for key, label in {
        "voiceover_enabled": "voiceover",
        "background_music_enabled": "background music",
        "explanation_enabled": "(?:answer )?explanation",
        "duplicate_prevention_enabled": "duplicate prevention",
    }.items():
        value = _set_boolean(text, label)
        if value is not None:
            update(key, value)

    logo_value = _set_boolean(text, "logo")
    if logo_value is not None:
        update("logo_enabled", logo_value)
    position_match = re.search(r"\b(?:logo )?(top left|top right|bottom left|bottom right|center)\b", text)
    if position_match and ("logo" in text or "position" in text):
        update("logo_position", position_match.group(1))

    language_match = re.search(r"\b(?:in|language(?: is|:)?)(?:\s+)(english|hindi|tamil|telugu|spanish|french)\b", text)
    if language_match:
        update("language", language_match.group(1).title())

    return preferences, changed


def send_chat_message(message: str) -> dict[str, object]:
    """Store chat context and return temporary overrides without changing Settings."""
    cleaned_message = message.strip()
    settings = get_preferences()
    proposed_preferences, changed = extract_preferences(cleaned_message, settings)
    overrides = {
        field: proposed_preferences[field]
        for field in changed
        if proposed_preferences.get(field) != settings.get(field)
    }
    _append_message("user", cleaned_message)
    if overrides:
        readable_changes = ", ".join(field.replace("_", " ") for field in overrides)
        assistant_message = f"Temporary draft override noted: {readable_changes}. Your saved Settings remain unchanged."
    else:
        assistant_message = "I saved your message as draft context. Your permanent Settings remain unchanged."
    _append_message("assistant", assistant_message)
    return {
        "assistant_message": assistant_message,
        "settings": settings,
        "overrides": overrides,
        "changed_fields": list(overrides),
    }


def reset_chat_preferences() -> None:
    """Clear conversation history without deleting permanent Settings."""
    with session_scope() as session:
        session.execute(delete(ChatMessageRecord))
