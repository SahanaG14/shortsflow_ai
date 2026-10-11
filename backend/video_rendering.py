"""Local FFmpeg assembly, countdowns, voiceover and validation for a Short."""

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
from database import GeneratedDraft, GeneratedScene, GeneratedVideo, session_scope
from image_generation import HEIGHT, WIDTH, validate_scenes
from voiceover import EdgeTTSProvider, VOICE_IDS

VIDEO_DIRECTORY = Path(__file__).resolve().parent / "generated-videos"
AUDIO_DIRECTORY = Path(__file__).resolve().parent / "generated-audio"
COUNTDOWN_DIRECTORY = Path(__file__).resolve().parent / "generated-countdowns"
WINDOWS_FFMPEG = Path(r"C:\Users\Sahana\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg.Shared_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build-shared\bin\ffmpeg.exe")
WINDOWS_FFPROBE = WINDOWS_FFMPEG.with_name("ffprobe.exe")
COUNTDOWN_VALUES = (5, 4, 3, 2, 1)


class VideoRenderError(RuntimeError):
    """Safe rendering error suitable for an API response."""


def _binary(env_name: str, executable: str, fallback: Path) -> str:
    configured = os.getenv(env_name)
    if configured and Path(configured).is_file(): return configured
    if from_path := shutil.which(executable): return from_path
    if fallback.is_file(): return str(fallback)
    raise VideoRenderError(f"{executable} is unavailable. Set {env_name} to its executable path.")


def _ffmpeg() -> str: return _binary("FFMPEG_PATH", "ffmpeg", WINDOWS_FFMPEG)
def _ffprobe() -> str: return _binary("FFPROBE_PATH", "ffprobe", WINDOWS_FFPROBE)


def _background_music() -> Path | None:
    configured = os.getenv("BACKGROUND_MUSIC_PATH")
    return Path(configured) if configured and Path(configured).is_file() else None


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf"):
        if Path(path).is_file(): return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _lines(value: str, max_chars: int = 25) -> list[str]:
    words, result, current = value.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars: result.append(current); current = word
        else: current = candidate
    return result + ([current] if current else [])


def _colors(data: dict[str, object]) -> tuple[str, str, str, str]:
    theme = str(data.get("theme", "")).casefold()
    return ("#10172e", "#1e2b58", "#bba6ff", "#f8f7ff") if "dark" in theme or "navy" in theme else ("#22143e", "#3a2368", "#c5b3ff", "#ffffff")


def _rasterize_scene(scene: GeneratedScene, destination: Path) -> None:
    """Create a viewer-facing PNG without internal branding or technical footer."""
    data = dict(scene.render_data); background, panel, accent, text = _colors(data)
    image = Image.new("RGB", (WIDTH, HEIGHT), background); draw = ImageDraw.Draw(image, "RGBA")
    draw.rounded_rectangle((70, 170, 1010, 1660), radius=52, fill=panel, outline=accent, width=3)
    draw.text((110, 285), str(data.get("heading", scene.scene_type)).upper(), font=_font(58), fill=accent)
    if scene.scene_type == "options":
        for index, option in enumerate(data.get("options", [])):
            top = 440 + index * 210
            draw.rounded_rectangle((115, top, 965, top + 145), radius=28, fill=background, outline=accent, width=2)
            draw.text((155, top + 38), f"{chr(65 + index)}. {option}", font=_font(44), fill=text)
    else:
        for index, line in enumerate(_lines(str(data.get("body", "")))):
            draw.text((130, 555 + index * 94), line, font=_font(62), fill=text)
    destination.parent.mkdir(parents=True, exist_ok=True); image.save(destination, "PNG")


def _countdown_frame(value: int, data: dict[str, object], destination: Path) -> None:
    background, panel, accent, text = _colors(data)
    image = Image.new("RGB", (WIDTH, HEIGHT), background); draw = ImageDraw.Draw(image, "RGBA")
    draw.rounded_rectangle((70, 170, 1010, 1660), radius=52, fill=panel, outline=accent, width=3)
    draw.text((540, 315), "GET READY", font=_font(62), fill=accent, anchor="ma")
    draw.ellipse((220, 560, 860, 1200), outline=accent, width=28)
    draw.text((540, 875), str(value), font=_font(330), fill=text, anchor="mm")
    draw.text((540, 1400), "THINK FAST", font=_font(58), fill=accent, anchor="ma")
    destination.parent.mkdir(parents=True, exist_ok=True); image.save(destination, "PNG")


def _target_duration(settings: dict[str, object]) -> float:
    value = settings.get("video_duration_seconds", 59)
    return float(value) if isinstance(value, int | float) and value > 0 else 59.0


def _timeline(scenes: list[GeneratedScene], target: float) -> list[dict[str, object]]:
    timer = next((scene for scene in scenes if scene.scene_type == "thinking"), None)
    countdown_seconds = min(float(len(COUNTDOWN_VALUES)), target * 0.45) if timer else 0.0
    non_timer = [scene for scene in scenes if scene is not timer]
    each = max(0.25, (target - countdown_seconds) / max(len(non_timer), 1))
    timeline: list[dict[str, object]] = []
    for scene in scenes:
        if scene is timer:
            for offset, value in enumerate(COUNTDOWN_VALUES):
                timeline.append({"scene_id": f"countdown-{value}", "scene_number": scene.scene_number + offset / 10, "scene_type": "countdown", "countdown_value": value, "duration_seconds": 1.0, "source_scene_id": scene.scene_id})
        else:
            timeline.append({"scene_id": scene.scene_id, "scene_number": scene.scene_number, "scene_type": scene.scene_type, "duration_seconds": round(each, 3)})
    timeline[-1]["duration_seconds"] = round(target - sum(float(item["duration_seconds"]) for item in timeline[:-1]), 3)
    return timeline


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        detail = (result.stderr or result.stdout).splitlines()[-1:] or ["Unknown FFmpeg error."]
        raise VideoRenderError("FFmpeg render failed: " + detail[0][:400])


def _probe(path: Path) -> dict[str, object]:
    result = subprocess.run([_ffprobe(), "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", str(path)], capture_output=True, text=True, check=False)
    if result.returncode: raise VideoRenderError("FFprobe could not read the rendered media.")
    return json.loads(result.stdout)


def _audio_duration(path: Path) -> float: return float(_probe(path).get("format", {}).get("duration", 0))


def _narration(draft: GeneratedDraft) -> str:
    content = dict(draft.content); parts = [str(content.get("hook", "")), str(content.get("question", ""))]
    options = content.get("options", [])
    if isinstance(options, list) and options: parts.append("Your options are " + ", ".join(str(value) for value in options) + ".")
    parts.append("The answer is " + str(content.get("correct_answer", "")) + ".")
    if content.get("explanation"): parts.append(str(content["explanation"]))
    return " ".join(part.strip() for part in parts if part and part.strip())


def _video_dict(record: GeneratedVideo) -> dict[str, object]:
    return {"id": record.id, "draft_id": record.draft_id, "render_status": record.render_status, "video_path": record.video_path, "duration_seconds": record.duration_seconds, "width": record.width, "height": record.height, "file_size_bytes": record.file_size_bytes, "validation_status": record.validation_status, "timeline": record.timeline, "audio_expected": record.audio_expected, "audio_note": record.audio_note, "voiceover_enabled": record.voiceover_enabled, "voice_provider": record.voice_provider, "voice_gender": record.voice_gender, "voice_id": record.voice_id, "audio_path": record.audio_path, "audio_duration_seconds": record.audio_duration_seconds, "countdown_length": record.countdown_length, "rendered_at": record.rendered_at.isoformat() if record.rendered_at else None}


def _scenes(draft_id: int) -> list[GeneratedScene]:
    with session_scope() as session: return list(session.scalars(select(GeneratedScene).where(GeneratedScene.draft_id == draft_id).order_by(GeneratedScene.scene_number)).all())


def render_video(draft_id: int) -> dict[str, object]:
    if not validate_scenes(draft_id)["valid"]: raise VideoRenderError("Scene validation failed. Regenerate only the failed scene before rendering video.")
    scenes = _scenes(draft_id)
    if not scenes: raise VideoRenderError("No validated scenes exist for this draft.")
    settings = get_preferences(); target = _target_duration(settings); timeline = _timeline(scenes, target); render_id = uuid4().hex
    work_dir = VIDEO_DIRECTORY / f"draft-{draft_id}" / render_id; work_dir.mkdir(parents=True, exist_ok=True)
    by_id = {scene.scene_id: scene for scene in scenes}; timer = next((scene for scene in scenes if scene.scene_type == "thinking"), None); segment_paths: list[Path] = []
    for index, item in enumerate(timeline, start=1):
        image_path, segment = work_dir / f"{index:02d}.png", work_dir / f"{index:02d}.mp4"
        if item["scene_type"] == "countdown":
            _countdown_frame(int(item["countdown_value"]), dict(timer.render_data if timer else {}), image_path)
            copy = COUNTDOWN_DIRECTORY / f"draft-{draft_id}" / render_id / image_path.name; copy.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(image_path, copy)
        else: _rasterize_scene(by_id[str(item["scene_id"])], image_path)
        duration = float(item["duration_seconds"]); fade = min(0.2, duration / 4)
        _run([_ffmpeg(), "-y", "-loop", "1", "-framerate", "24", "-t", f"{duration:.3f}", "-i", str(image_path), "-vf", f"fade=t=in:st=0:d={fade:.3f},fade=t=out:st={max(0, duration-fade):.3f}:d={fade:.3f},format=yuv420p", "-r", "24", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "25", str(segment)])
        segment_paths.append(segment)
    manifest = work_dir / "timeline.txt"; manifest.write_text("".join(f"file '{path.as_posix()}'\n" for path in segment_paths), encoding="utf-8")
    voiceover_enabled = bool(settings.get("voiceover_enabled", False)); gender = str(settings.get("voice_gender", "male")).casefold()
    if gender not in VOICE_IDS: gender = "male"
    audio_file: Path | None = None; audio_duration: float | None = None; provider = voice = ""
    if voiceover_enabled:
        with session_scope() as session: draft = session.get(GeneratedDraft, draft_id)
        if not draft: raise VideoRenderError("Accepted draft was not found.")
        audio_file = AUDIO_DIRECTORY / f"draft-{draft_id}" / render_id / "voiceover.mp3"
        try:
            metadata = EdgeTTSProvider().synthesize(_narration(draft), gender, audio_file); provider, voice, audio_duration = metadata["provider"], metadata["voice"], _audio_duration(audio_file)
        except Exception as error: raise VideoRenderError("Voiceover synthesis failed. Check edge-tts connectivity and try again.") from error
        if audio_duration > target: raise VideoRenderError("Voiceover narration exceeds the configured video duration. Shorten the draft before rendering.")
    music_requested, music = bool(settings.get("background_music_enabled", False)), _background_music(); output = work_dir / "short.mp4"; command = [_ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(manifest)]
    if audio_file:
        command.extend(["-i", str(audio_file)])
        if music: command.extend(["-stream_loop", "-1", "-i", str(music), "-filter_complex", f"[1:a]apad=pad_dur={target}[voice];[2:a]volume=0.16,apad=pad_dur={target}[music];[voice][music]amix=inputs=2:duration=first[a]", "-map", "0:v:0", "-map", "[a]"])
        else: command.extend(["-filter_complex", f"[1:a]apad=pad_dur={target}[a]", "-map", "0:v:0", "-map", "[a]"])
    elif music: command.extend(["-stream_loop", "-1", "-i", str(music), "-map", "0:v:0", "-map", "1:a:0"])
    command.extend(["-t", f"{target:.3f}", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "25", "-c:a", "aac", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)])
    _run(command)
    probe = _probe(output); streams = probe.get("streams", []); video_stream = next((s for s in streams if s.get("codec_type") == "video"), {}); duration = float(probe.get("format", {}).get("duration", 0))
    notes = [f"Voiceover: {voice}." if voiceover_enabled else ""]
    if music_requested and not music: notes.append("No local royalty-free background music asset is configured.")
    if not voiceover_enabled and not music: notes.append("Rendered without audio.")
    public_path = f"/generated-videos/draft-{draft_id}/{render_id}/short.mp4"
    with session_scope() as session:
        record = session.scalar(select(GeneratedVideo).where(GeneratedVideo.draft_id == draft_id)) or GeneratedVideo(draft_id=draft_id); session.add(record)
        record.render_status, record.video_path = "rendered", public_path; record.duration_seconds, record.width, record.height, record.file_size_bytes = duration, int(video_stream.get("width", 0)), int(video_stream.get("height", 0)), output.stat().st_size
        record.timeline, record.audio_expected, record.audio_note, record.validation_status = timeline, bool(audio_file or music), " ".join(note for note in notes if note), "pending"
        record.voiceover_enabled, record.voice_provider, record.voice_gender, record.voice_id = voiceover_enabled, provider, gender if voiceover_enabled else "", voice
        record.audio_path, record.audio_duration_seconds, record.countdown_length = str(audio_file) if audio_file else "", audio_duration, len(COUNTDOWN_VALUES) if timer else 0
        session.flush(); return _video_dict(record)


def get_video(draft_id: int) -> dict[str, object] | None:
    with session_scope() as session:
        record = session.scalar(select(GeneratedVideo).where(GeneratedVideo.draft_id == draft_id)); return _video_dict(record) if record else None


def validate_video(draft_id: int) -> dict[str, object]:
    with session_scope() as session:
        record = session.scalar(select(GeneratedVideo).where(GeneratedVideo.draft_id == draft_id))
        if not record: raise VideoRenderError("No rendered video exists for this draft.")
        target, errors = _target_duration(get_preferences()), []; target_path = VIDEO_DIRECTORY / record.video_path.removeprefix("/generated-videos/")
        if not target_path.is_file(): errors.append("Rendered MP4 file is missing.")
        else:
            try:
                probe = _probe(target_path); streams = probe.get("streams", []); video = next((s for s in streams if s.get("codec_type") == "video"), None); audio = any(s.get("codec_type") == "audio" for s in streams); duration = float(probe.get("format", {}).get("duration", 0))
                if not video: errors.append("MP4 has no video stream.")
                elif (int(video.get("width", 0)), int(video.get("height", 0))) != (WIDTH, HEIGHT): errors.append("Video is not 1080 × 1920.")
                if duration > target + .1 or abs(duration-target) > .25: errors.append("Video duration does not match the configured target.")
                if record.audio_expected != audio: errors.append("Audio stream does not match the expected audio configuration.")
                countdown = [item for item in record.timeline if item.get("scene_type") == "countdown"]
                if countdown and [item.get("countdown_value") for item in countdown] != list(COUNTDOWN_VALUES): errors.append("Countdown sequence is invalid.")
                if countdown and any(abs(float(item.get("duration_seconds", 0)) - 1) > .1 for item in countdown): errors.append("Countdown frames must be approximately one second each.")
                if record.voiceover_enabled:
                    if not record.audio_path or not Path(record.audio_path).is_file(): errors.append("Generated voiceover audio file is missing.")
                    if record.voice_provider != "edge-tts" or record.voice_id != VOICE_IDS.get(record.voice_gender): errors.append("Voice metadata does not match saved Settings.")
                record.duration_seconds, record.width, record.height = duration, int(video.get("width", 0)) if video else 0, int(video.get("height", 0)) if video else 0
            except (VideoRenderError, ValueError, json.JSONDecodeError) as error: errors.append(str(error))
        record.validation_status = "valid" if not errors else "failed"; session.flush()
        return {"draft_id": draft_id, "valid": not errors, "errors": errors, "video": _video_dict(record)}
