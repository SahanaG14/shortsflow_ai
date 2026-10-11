"""Local Shorts draft generation with duplicate-safe acceptance and PostgreSQL storage."""

from collections.abc import Mapping
from typing import Protocol

from sqlalchemy import select

from chat_preferences import get_preferences
from database import GeneratedDraft, session_scope
from duplicate_detection import check_duplicate
from videos_db import list_videos


DEFAULT_DURATION_SECONDS = 59
DEFAULT_OPTIONS_COUNT = 4
DEFAULT_MAX_ATTEMPTS = 5


class ContentProvider(Protocol):
    """A future LLM provider only needs to implement this candidate contract."""

    def create_candidate(self, preferences: Mapping[str, object], attempt: int) -> dict[str, object]: ...


class LocalTemplateContentProvider:
    """Dependency-free provider used until an LLM provider is intentionally added."""

    _templates = {
        "CS": (
            {
                "topic": "Modular arithmetic remainder patterns",
                "title": "Can You Predict the Remainder? | Modular Arithmetic Sprint",
                "hook": "This three-second pattern can save you a long calculation.",
                "question": "What is the remainder when 47 is divided by 6?",
                "options": ["4", "5", "6", "7"],
                "answer": "5",
                "explanation": "Six goes into 47 seven times for 42, leaving a remainder of 5.",
            },
            {
                "topic": "Boolean logic evaluation",
                "title": "Can You Trace This Boolean Expression? | Logic Sprint",
                "hook": "One operator changes the whole answer—can you spot it?",
                "question": "If A is true and B is false, what is A AND (NOT B)?",
                "options": ["true", "false", "undefined", "It depends"],
                "answer": "true",
                "explanation": "NOT B is true, and true AND true evaluates to true.",
            },
        ),
        "aptitude": (
            {
                "topic": "Ratio simplification",
                "title": "Can You Simplify This Ratio? | 10-Second Aptitude Sprint",
                "hook": "A fast ratio trick turns this into an easy answer.",
                "question": "Simplify the ratio 18:24.",
                "options": ["2:3", "3:4", "4:5", "5:6"],
                "answer": "3:4",
                "explanation": "Divide both terms by their greatest common divisor, 6: 18:24 becomes 3:4.",
            },
            {
                "topic": "Average speed reasoning",
                "title": "Can You Find the Average Speed? | Aptitude Sprint",
                "hook": "Don’t average the numbers before checking the distances.",
                "question": "A car travels 60 km in 2 hours. What is its average speed?",
                "options": ["20 km/h", "30 km/h", "40 km/h", "120 km/h"],
                "answer": "30 km/h",
                "explanation": "Average speed equals total distance divided by total time: 60 divided by 2 is 30 km/h.",
            },
        ),
    }

    def create_candidate(self, preferences: Mapping[str, object], attempt: int) -> dict[str, object]:
        categories = preferences.get("content_categories")
        category_list = categories if isinstance(categories, list) and categories else ["CS"]
        category = str(category_list[(attempt - 1) % len(category_list)])
        templates = self._templates.get(category, self._templates["CS"])
        template = templates[(attempt - 1) % len(templates)]
        options_count = _preference_int(preferences, "options_count", DEFAULT_OPTIONS_COUNT)
        options = _sized_options(list(template["options"]), options_count)
        duration = _preference_int(preferences, "video_duration_seconds", DEFAULT_DURATION_SECONDS)
        explanation_enabled = bool(preferences.get("explanation_enabled", True))
        thinking_timer = _preference_int(preferences, "thinking_timer_seconds", 8)
        return {
            "topic": template["topic"],
            "title": template["title"],
            "hook": template["hook"],
            "question": template["question"],
            "options": options,
            "correct_answer": template["answer"],
            "explanation": template["explanation"] if explanation_enabled else None,
            "scene_script": (
                f"Hook: {template['hook']}\n"
                f"Question: {template['question']}\n"
                f"Thinking timer: {thinking_timer} seconds.\n"
                f"Answer reveal: {template['answer']}."
            ),
            "target_duration_seconds": duration,
            "metadata": {
                "provider": "local_template",
                "category": category,
                "language": preferences.get("language", "English"),
                "aspect_ratio": preferences.get("aspect_ratio", "9:16"),
                "theme": preferences.get("theme", "default"),
                "thinking_timer_seconds": thinking_timer,
                "voiceover_enabled": bool(preferences.get("voiceover_enabled", False)),
                "background_music_enabled": bool(preferences.get("background_music_enabled", False)),
                "thumbnail_prompt": None,
                "hashtags": [],
            },
        }


def _preference_int(preferences: Mapping[str, object], key: str, default: int) -> int:
    value = preferences.get(key, default)
    return value if isinstance(value, int) and value > 0 else default


def _sized_options(options: list[str], count: int) -> list[str]:
    count = max(0, count)
    expanded = list(options)
    while len(expanded) < count:
        expanded.append(f"Option {len(expanded) + 1}")
    return expanded[:count]


def _duplicate_history_entry(attempt: int, candidate: Mapping[str, object], result: Mapping[str, object]) -> dict[str, object]:
    return {
        "attempt": attempt,
        "candidate_title": candidate["title"],
        "accepted": not bool(result["is_duplicate"]),
        "duplicate_type": result["duplicate_type"],
        "similarity_score": result["similarity_score"],
        "matched_title": result["matched_title"],
        "reason": result["reason"],
    }


def _persist_draft(draft: Mapping[str, object]) -> dict[str, object]:
    with session_scope() as session:
        record = GeneratedDraft(
            topic=str(draft["topic"]),
            title=str(draft["title"]),
            content=dict(draft),
        )
        session.add(record)
        session.flush()
        persisted = dict(draft)
        persisted["id"] = record.id
        persisted["created_at"] = record.created_at.isoformat() if record.created_at else None
        return persisted


def generate_short_draft(
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    temporary_overrides: Mapping[str, object] | None = None,
    provider: ContentProvider | None = None,
) -> dict[str, object]:
    """Generate from permanent Settings plus per-draft chat overrides."""
    preferences = {**get_preferences(), **(dict(temporary_overrides) if temporary_overrides else {})}
    videos = list_videos()
    candidate_provider = provider or LocalTemplateContentProvider()
    duplicate_checks: list[dict[str, object]] = []

    for attempt in range(1, max_attempts + 1):
        candidate = candidate_provider.create_candidate(preferences, attempt)
        duplicate_result = check_duplicate(
            str(candidate["title"]), str(candidate["topic"]), videos
        )
        duplicate_checks.append(_duplicate_history_entry(attempt, candidate, duplicate_result))
        if not duplicate_result["is_duplicate"]:
            metadata = candidate.get("metadata")
            if isinstance(metadata, dict):
                metadata["temporary_overrides"] = dict(temporary_overrides or {})
            return {
                "accepted": True,
                "attempt_count": attempt,
                "duplicate_checks": duplicate_checks,
                "draft": _persist_draft(candidate),
            }

    return {
        "accepted": False,
        "attempt_count": max_attempts,
        "duplicate_checks": duplicate_checks,
        "detail": "No non-duplicate Short draft could be generated within the retry limit.",
    }


def list_generated_drafts() -> list[dict[str, object]]:
    with session_scope() as session:
        records = session.scalars(select(GeneratedDraft).order_by(GeneratedDraft.id.desc())).all()
        return [
            {
                "id": record.id,
                "created_at": record.created_at.isoformat(),
                **record.content,
            }
            for record in records
        ]
