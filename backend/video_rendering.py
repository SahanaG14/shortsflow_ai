"""Local FFmpeg assembly, validation and re-rendering for a Short draft."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select

from chat_preferences import get_preferences
from database import GeneratedScene, GeneratedVideo, session_scope
from image_generation import ASSET_DIRECTORY, HEIGHT, WIDTH, validate_scenes


VIDEO_DIRECTORY = Path(__file__).resolve().parent / "generated-videos"
WINDOWS_FFMPEG = Path(r"C:\Users\Sahana\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg.Shared_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build-shared\bin\ffmpeg.exe")
WINDOWS_FFPROBE = WINDOWS_FFMPEG.with_name("ffprobe.exe")


class VideoRenderError(RuntimeError):
    """Safe rendering error suitable for an API response."""


def _binary(env_name: str, executable: str, fallback: Path) -> str:
    configured = os.getenv(env_name)
    if configured and Path(configured).is_file():
        return configured
    from_path = shutil.which(executable)
    if from_path:
        return from_path
    if fallback.is_file():
        return str(fallback)
    raise VideoRenderError(f"{executable} is unavailable. Set {env_name} to its executable path.")


def _ffmpeg() -> str:
    return _binary("FFMPEG_PATH", "ffmpeg", WINDOWS_FFMPEG)


def _ffprobe() -> str:
    return _binary("FFPROBE_PATH", "ffprobe", WINDOWS_FFPROBE)


def _background_music() -> Path | None:
    configured = os.getenv("BACKGROUND_MUSIC_PATH")
    return Path(configured) if configured and Path(configured).is_file() else None


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf"):
        if Path(path).is_file():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _lines(value: str, max_chars: int = 28) -> list[str]:
    words, result, current = value.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars:
            result.append(current); current = word
        else:
            current = candidate
    return result + ([current] if current else [])


def _rasterize_scene(scene: GeneratedScene, destination: Path) -> None:
    """Create an FFmpeg-friendly PNG from already validated scene render data."""
    data = scene.render_data
    theme = str(data.get("theme", "")).casefold()
    dark = "dark" in theme or "navy" in theme
    background, panel, accent, text = ("#10172e", "#1e2b58", "#bba6ff", "#f8f7ff") if dark else ("#22143e", "#3a2368", "#c5b3ff", "#ffffff")
    image = Image.new("RGB", (WIDTH, HEIGHT), background)
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rounded_rectangle((70, 230, 1010, 1500), radius=52, fill=panel, outline=accent, width=3)
    draw.text((90, 88), str(data.get("branding", "ShortsFlow AI")), font=_font(38), fill=accent)
    draw.text((110, 330), str(data.get("heading", scene.scene_type)).upper(), font=_font(42), fill=accent)
    if scene.scene_type == "options":
        for index, option in enumerate(data.get("options", [])):
            top = 470 + index * 190
            draw.rounded_rectangle((115, top, 965, top + 135), radius=28, fill=background, outline=accent, width=2)
            draw.text((155, top + 38), f"{chr(65 + index)}. {option}", font=_font(44), fill=text)
    else:
        body = str(data.get("body", ""))
        start = 760 if scene.scene_type == "thinking" else 535
        if scene.scene_type == "thinking":
            draw.ellipse((370, 440, 710, 780), outline=accent, width=20)
        for index, line in enumerate(_lines(body, 24)):
            draw.text((130, start + index * 88), line, font=_font(56), fill=text)
    draw.text((390, 1710), f"9:16 • {data.get('language', 'English')}", font=_font(30), fill=text)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, "PNG")


def _target_duration(settings: dict[str, object]) -> float:
    value = settings.get("video_duration_seconds", 59)
    return float(value) if isinstance(value, int | float) and value > 0 else 59.0


def _timeline(scenes: list[GeneratedScene], target: float) -> list[dict[str, object]]:
    timer_scene = next((scene for scene in scenes if scene.scene_type == "thinking"), None)
    timer = float(timer_scene.render_data.get("timer_seconds", 0)) if timer_scene else 0.0
    timer = min(timer, target * 0.45)
    remainder = max(0.0, target - timer)
    other_count = len(scenes) - (1 if timer_scene else 0)
    each = remainder / max(other_count, 1)
    timeline: list[dict[str, object]] = []
    for scene in scenes:
        duration = timer if timer_scene and scene.id == timer_scene.id else each
        timeline.append({"scene_id": scene.scene_id, "scene_number": scene.scene_number, "scene_type": scene.scene_type, "duration_seconds": round(duration, 3)})
    # Preserve the target exactly after floating-point rounding.
    timeline[-1]["duration_seconds"] = round(target - sum(float(item["duration_seconds"]) for item in timeline[:-1]), 3)
    return timeline


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        detail = (result.stderr or result.stdout).splitlines()[-1:] or ["Unknown FFmpeg error."]
        raise VideoRenderError("FFmpeg render failed: " + detail[0][:400])


def _probe(path: Path) -> dict[str, object]:
    result = subprocess.run([_ffprobe(), "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", str(path)], capture_output=True, text=True, check=False)
    if result.returncode:
        raise VideoRenderError("FFprobe could not read the rendered MP4.")
    return json.loads(result.stdout)


def _video_dict(record: GeneratedVideo) -> dict[str, object]:
    return {"id": record.id, "draft_id": record.draft_id, "render_status": record.render_status, "video_path": record.video_path, "duration_seconds": record.duration_seconds, "width": record.width, "height": record.height, "file_size_bytes": record.file_size_bytes, "validation_status": record.validation_status, "timeline": record.timeline, "audio_expected": record.audio_expected, "audio_note": record.audio_note, "rendered_at": record.rendered_at.isoformat() if record.rendered_at else None}


def _scenes(draft_id: int) -> list[GeneratedScene]:
    with session_scope() as session:
        return list(session.scalars(select(GeneratedScene).where(GeneratedScene.draft_id == draft_id).order_by(GeneratedScene.scene_number)).all())


def render_video(draft_id: int) -> dict[str, object]:
    image_validation = validate_scenes(draft_id)
    if not image_validation["valid"]:
        raise VideoRenderError("Scene validation failed. Regenerate only the failed scene before rendering video.")
    scenes = _scenes(draft_id)
    if not scenes:
        raise VideoRenderError("No validated scenes exist for this draft.")
    settings = get_preferences()
    target = _target_duration(settings)
    timeline = _timeline(scenes, target)
    render_id = uuid4().hex
    work_dir = VIDEO_DIRECTORY / f"draft-{draft_id}" / render_id
    work_dir.mkdir(parents=True, exist_ok=True)
    segment_paths: list[Path] = []
    for scene, item in zip(scenes, timeline, strict=True):
        image_path = work_dir / f"{scene.scene_number:02d}.png"
        segment = work_dir / f"{scene.scene_number:02d}.mp4"
        _rasterize_scene(scene, image_path)
        duration = float(item["duration_seconds"])
        fade = min(0.35, duration / 4)
        _run([_ffmpeg(), "-y", "-loop", "1", "-framerate", "24", "-t", f"{duration:.3f}", "-i", str(image_path), "-vf", f"fade=t=in:st=0:d={fade:.3f},fade=t=out:st={max(0, duration - fade):.3f}:d={fade:.3f},format=yuv420p", "-r", "24", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "25", str(segment)])
        segment_paths.append(segment)
    manifest = work_dir / "timeline.txt"
    manifest.write_text("".join(f"file '{path.as_posix()}'\n" for path in segment_paths), encoding="utf-8")
    output = work_dir / "short.mp4"
    music_requested = bool(settings.get("background_music_enabled", False))
    music = _background_music() if music_requested else None
    final_command = [_ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(manifest)]
    if music:
        final_command.extend(["-stream_loop", "-1", "-i", str(music), "-map", "0:v:0", "-map", "1:a:0", "-shortest", "-c:a", "aac"])
    final_command.extend(["-t", f"{target:.3f}", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "25", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)])
    _run(final_command)
    probe = _probe(output)
    streams = probe.get("streams", [])
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    duration = float(probe.get("format", {}).get("duration", 0))
    voiceover_requested = bool(settings.get("voiceover_enabled", False))
    notes: list[str] = []
    if music_requested and not music: notes.append("No local royalty-free background music asset is configured.")
    if voiceover_requested: notes.append("Voiceover is requested but no local voiceover provider is configured.")
    if not music: notes.append("Rendered without audio.")
    note = " ".join(notes) or "Local royalty-free background music was included."
    public_path = f"/generated-videos/draft-{draft_id}/{render_id}/short.mp4"
    with session_scope() as session:
        record = session.scalar(select(GeneratedVideo).where(GeneratedVideo.draft_id == draft_id))
        if not record:
            record = GeneratedVideo(draft_id=draft_id)
            session.add(record)
        record.render_status, record.video_path = "rendered", public_path
        record.duration_seconds, record.width, record.height = duration, int(video_stream.get("width", 0)), int(video_stream.get("height", 0))
        record.file_size_bytes, record.timeline, record.audio_expected, record.audio_note = output.stat().st_size, timeline, bool(music), note
        record.validation_status = "pending"
        session.flush()
        return _video_dict(record)


def get_video(draft_id: int) -> dict[str, object] | None:
    with session_scope() as session:
        record = session.scalar(select(GeneratedVideo).where(GeneratedVideo.draft_id == draft_id))
        return _video_dict(record) if record else None


def validate_video(draft_id: int) -> dict[str, object]:
    with session_scope() as session:
        record = session.scalar(select(GeneratedVideo).where(GeneratedVideo.draft_id == draft_id))
        if not record:
            raise VideoRenderError("No rendered video exists for this draft.")
        target = _target_duration(get_preferences())
        errors: list[str] = []
        target_path = VIDEO_DIRECTORY / record.video_path.removeprefix("/generated-videos/")
        if not target_path.is_file():
            errors.append("Rendered MP4 file is missing.")
        else:
            try:
                probe = _probe(target_path)
                streams = probe.get("streams", [])
                video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
                audio = any(stream.get("codec_type") == "audio" for stream in streams)
                duration = float(probe.get("format", {}).get("duration", 0))
                if not video: errors.append("MP4 has no video stream.")
                elif int(video.get("width", 0)) != WIDTH or int(video.get("height", 0)) != HEIGHT: errors.append("Video is not 1080 × 1920.")
                if duration > target + 0.1 or abs(duration - target) > 0.25: errors.append("Video duration does not match the configured target.")
                if record.audio_expected != audio: errors.append("Audio stream does not match the expected audio configuration.")
                required = _scenes(draft_id)
                if len(record.timeline) != len(required) or [item.get("scene_id") for item in record.timeline] != [scene.scene_id for scene in required]: errors.append("Timeline does not include every required scene in order.")
                record.duration_seconds, record.width, record.height = duration, int(video.get("width", 0)) if video else 0, int(video.get("height", 0)) if video else 0
            except (VideoRenderError, ValueError, json.JSONDecodeError) as error:
                errors.append(str(error))
        record.validation_status = "valid" if not errors else "failed"
        session.flush()
        return {"draft_id": draft_id, "valid": not errors, "errors": errors, "video": _video_dict(record)}
