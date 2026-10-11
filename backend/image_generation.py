"""Deterministic 9:16 Short scene rendering and validation.

This module deliberately renders text-heavy scenes locally as SVG.  A later image provider
may add decorative background artwork, but it must never replace validated draft text.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from sqlalchemy import delete, select

from chat_preferences import get_preferences
from database import GeneratedDraft, GeneratedScene, session_scope


WIDTH = 1080
HEIGHT = 1920
ASSET_DIRECTORY = Path(__file__).resolve().parent / "generated-assets"


class ImageProvider(Protocol):
    """Contract for a future decorative image provider."""

    def render(self, scene: Mapping[str, object], destination: Path) -> None: ...


def _wrapped_lines(value: str, limit: int = 26) -> list[str]:
    words = value.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > limit:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def _theme_colors(theme: object) -> tuple[str, str, str, str]:
    text = str(theme or "").casefold()
    if "navy" in text or "dark" in text:
        return "#10172e", "#1e2b58", "#bba6ff", "#f8f7ff"
    if "light" in text:
        return "#f7f5ff", "#e6dfff", "#5c36ae", "#231a38"
    return "#22143e", "#3a2368", "#c5b3ff", "#ffffff"


def _scene_definitions(draft: Mapping[str, object], settings: Mapping[str, object]) -> list[dict[str, object]]:
    metadata = draft.get("metadata") if isinstance(draft.get("metadata"), dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    overrides = metadata.get("temporary_overrides") if isinstance(metadata.get("temporary_overrides"), dict) else {}
    context = {**settings, **metadata, **overrides}
    options = draft.get("options") if isinstance(draft.get("options"), list) else []
    timer = int(context.get("thinking_timer_seconds", 0) or 0)
    branding = str(context.get("channel_branding") or context.get("channel_name") or "ShortsFlow AI")
    common = {"theme": context.get("theme", "purple"), "language": context.get("language", "English"), "branding": branding}
    scenes: list[dict[str, object]] = [
        {**common, "scene_type": "hook", "heading": "QUICK CHALLENGE", "body": str(draft.get("hook", ""))},
        {**common, "scene_type": "question", "heading": "QUESTION", "body": str(draft.get("question", ""))},
    ]
    if options:
        scenes.append({**common, "scene_type": "options", "heading": "CHOOSE ONE", "options": [str(item) for item in options]})
    if timer > 0:
        scenes.append({**common, "scene_type": "thinking", "heading": "THINK FAST", "body": f"{timer} seconds", "timer_seconds": timer})
    scenes.append({**common, "scene_type": "answer", "heading": "ANSWER", "body": str(draft.get("correct_answer", ""))})
    explanation = draft.get("explanation")
    if explanation:
        scenes.append({**common, "scene_type": "explanation", "heading": "WHY IT WORKS", "body": str(explanation)})
    scenes.append({**common, "scene_type": "ending", "heading": "KEEP LEARNING", "body": "Follow for the next quick challenge."})
    for index, scene in enumerate(scenes, start=1):
        scene["scene_number"] = index
    return scenes


class DeterministicSceneRenderer:
    """Dependency-free SVG renderer for exact text, option and answer fidelity."""

    def render(self, scene: Mapping[str, object], destination: Path) -> None:
        background, panel, accent, text = _theme_colors(scene.get("theme"))
        heading = escape(str(scene.get("heading", "")))
        body = str(scene.get("body", ""))
        scene_type = str(scene.get("scene_type", ""))
        lines = _wrapped_lines(body, 20 if scene_type in {"question", "explanation"} else 24)
        content: list[str] = [
            f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{background}"/>',
            f'<rect x="48" y="120" width="984" height="1640" rx="64" fill="{panel}" stroke="{accent}" stroke-width="4"/>',
            f'<rect x="48" y="120" width="984" height="18" rx="9" fill="{accent}"/>',
            f'<text x="96" y="225" fill="{accent}" font-family="Arial, sans-serif" font-size="46" font-weight="700">{escape(str(scene.get("branding", "ShortsFlow AI")))}</text>',
            f'<text x="96" y="345" fill="{accent}" font-family="Arial, sans-serif" font-size="54" font-weight="700">{heading}</text>',
        ]
        if scene_type == "options":
            for index, option in enumerate(scene.get("options", [])):
                top = 470 + index * 250
                content.extend([
                    f'<rect x="96" y="{top}" width="888" height="184" rx="34" fill="{background}" stroke="{accent}" stroke-width="3"/>',
                    f'<text x="142" y="{top + 112}" fill="{text}" font-family="Arial, sans-serif" font-size="56" font-weight="600">{escape(chr(65 + index) + ". " + str(option))}</text>',
                ])
        else:
            start = 610 if scene_type != "thinking" else 920
            font_size = 78 if scene_type in {"question", "answer"} else 64
            if scene_type == "thinking":
                content.extend([f'<circle cx="540" cy="675" r="245" fill="none" stroke="{accent}" stroke-width="28"/>', f'<circle cx="540" cy="675" r="196" fill="{background}"/>'])
            for index, line in enumerate(lines):
                content.append(f'<text x="104" y="{start + index * (font_size + 34)}" fill="{text}" font-family="Arial, sans-serif" font-size="{font_size}" font-weight="600">{escape(line)}</text>')
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1920" viewBox="0 0 1080 1920">' + ''.join(content) + '</svg>', encoding="utf-8")


def _draft(draft_id: int) -> dict[str, object]:
    with session_scope() as session:
        record = session.get(GeneratedDraft, draft_id)
        if not record:
            raise ValueError("Accepted draft was not found.")
        return {"id": record.id, **record.content}


def _record_to_dict(record: GeneratedScene) -> dict[str, object]:
    return {"id": record.id, "scene_id": record.scene_id, "draft_id": record.draft_id, "scene_number": record.scene_number, "scene_type": record.scene_type, "image_path": record.image_path, "generation_status": record.generation_status, "validation_status": record.validation_status, "render_data": record.render_data}


def _asset_path(draft_id: int, scene_id: str) -> tuple[Path, str]:
    relative = f"draft-{draft_id}/{scene_id}.svg"
    return ASSET_DIRECTORY / relative, f"/generated-assets/{relative}"


def generate_scenes(draft_id: int, renderer: ImageProvider | None = None) -> list[dict[str, object]]:
    draft = _draft(draft_id)
    definitions = _scene_definitions(draft, get_preferences())
    scene_renderer = renderer or DeterministicSceneRenderer()
    with session_scope() as session:
        session.execute(delete(GeneratedScene).where(GeneratedScene.draft_id == draft_id))
        records: list[GeneratedScene] = []
        for definition in definitions:
            scene_id = uuid4().hex
            destination, public_path = _asset_path(draft_id, scene_id)
            scene_renderer.render(definition, destination)
            record = GeneratedScene(scene_id=scene_id, draft_id=draft_id, scene_number=int(definition["scene_number"]), scene_type=str(definition["scene_type"]), image_path=public_path, generation_status="generated", validation_status="pending", render_data=definition)
            session.add(record)
            records.append(record)
        session.flush()
        return [_record_to_dict(record) for record in records]


def list_scenes(draft_id: int) -> list[dict[str, object]]:
    with session_scope() as session:
        records = session.scalars(select(GeneratedScene).where(GeneratedScene.draft_id == draft_id).order_by(GeneratedScene.scene_number)).all()
        return [_record_to_dict(record) for record in records]


def _validate_scene(record: GeneratedScene) -> list[str]:
    errors: list[str] = []
    relative = record.image_path.removeprefix("/generated-assets/")
    target = ASSET_DIRECTORY / relative
    if not target.is_file():
        return ["Rendered image file is missing."]
    source = target.read_text(encoding="utf-8")
    if 'width="1080"' not in source or 'height="1920"' not in source:
        errors.append("Image is not exactly 1080 × 1920.")
    data = record.render_data
    expected = [str(data.get("heading", "")), str(data.get("branding", ""))]
    expected.extend(str(value) for value in data.get("options", []) if value)
    if data.get("body"):
        limit = 20 if record.scene_type in {"question", "explanation"} else 24
        expected.extend(_wrapped_lines(str(data["body"]), limit))
    for value in expected:
        if value and escape(value) not in source:
            errors.append(f"Required rendered text is missing: {value}")
    return errors


def validate_scenes(draft_id: int) -> dict[str, object]:
    expected = _scene_definitions(_draft(draft_id), get_preferences())
    with session_scope() as session:
        records = session.scalars(select(GeneratedScene).where(GeneratedScene.draft_id == draft_id).order_by(GeneratedScene.scene_number)).all()
        errors: list[dict[str, object]] = []
        if len(records) != len(expected):
            errors.append({"scene_id": None, "errors": ["Expected scene count does not match generated scene count."]})
        for number, expected_scene in enumerate(expected, start=1):
            if number > len(records) or records[number - 1].scene_type != expected_scene["scene_type"]:
                errors.append({"scene_id": records[number - 1].scene_id if number <= len(records) else None, "errors": ["Scene order or required scene type is invalid."]})
        for record in records:
            scene_errors = _validate_scene(record)
            record.validation_status = "valid" if not scene_errors else "failed"
            if scene_errors:
                errors.append({"scene_id": record.scene_id, "errors": scene_errors})
        return {"draft_id": draft_id, "valid": not errors, "expected_scene_count": len(expected), "generated_scene_count": len(records), "errors": errors, "scenes": [_record_to_dict(record) for record in records]}


def regenerate_scene(draft_id: int, scene_id: str, renderer: ImageProvider | None = None) -> dict[str, object]:
    definitions = _scene_definitions(_draft(draft_id), get_preferences())
    scene_renderer = renderer or DeterministicSceneRenderer()
    with session_scope() as session:
        record = session.scalar(select(GeneratedScene).where(GeneratedScene.draft_id == draft_id, GeneratedScene.scene_id == scene_id))
        if not record:
            raise ValueError("Scene was not found for this draft.")
        definition = next((item for item in definitions if item["scene_number"] == record.scene_number), None)
        if not definition:
            raise ValueError("Scene definition is no longer available.")
        destination, public_path = _asset_path(draft_id, record.scene_id)
        scene_renderer.render(definition, destination)
        record.image_path = public_path
        record.generation_status = "generated"
        record.validation_status = "pending"
        record.render_data = definition
        session.flush()
        return _record_to_dict(record)
