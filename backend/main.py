import os
import secrets
import logging
import hmac
import time
import hashlib
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from youtube_oauth import (
    OAuthConfigurationError,
    OAuthTokenExchangeError,
    YouTubeAuthenticationError,
    YouTubeSyncError,
    get_authorization_url,
    get_channel_details,
    get_uploaded_videos,
    save_authorization_token,
)
from database import initialize_database
from videos_db import list_videos, upsert_videos, video_count
from duplicate_detection import check_duplicate
from content_generation import generate_short_draft, list_generated_drafts
from image_generation import ASSET_DIRECTORY, generate_scenes, list_scenes, regenerate_scene, validate_scenes
from video_rendering import VIDEO_DIRECTORY, VideoRenderError, get_video, render_video, validate_video
from ai_provider import AIProviderError
from assistant_service import chat as assistant_chat, clear_history as clear_assistant_history, get_history as get_assistant_history
from chat_preferences import (
    get_chat_history,
    get_preferences,
    reset_chat_preferences,
    save_preferences,
    send_chat_message,
)

BACKEND_DIRECTORY = Path(__file__).resolve().parent
CLIENT_SECRETS_FILE = BACKEND_DIRECTORY / "client_secret.json"
TOKEN_FILE = BACKEND_DIRECTORY / "youtube_token.json"
SESSION_SECRET_FILE = BACKEND_DIRECTORY / ".oauth_session_secret"
OAUTH_STATE_FILE = BACKEND_DIRECTORY / ".oauth_state.json"
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
OAUTH_REDIRECT_URI = os.getenv(
    "GOOGLE_OAUTH_REDIRECT_URI",
    "http://localhost:8000/api/youtube/oauth/callback",
)
OAUTH_STATE_TTL_SECONDS = 10 * 60


def load_session_secret() -> str:
    """Load a stable local signing secret without exposing it in logs or Git."""
    configured_secret = os.getenv("OAUTH_SESSION_SECRET")
    if configured_secret:
        return configured_secret
    if SESSION_SECRET_FILE.is_file():
        return SESSION_SECRET_FILE.read_text(encoding="utf-8").strip()

    session_secret = secrets.token_urlsafe(48)
    SESSION_SECRET_FILE.write_text(session_secret, encoding="utf-8")
    return session_secret


app = FastAPI()
ASSET_DIRECTORY.mkdir(parents=True, exist_ok=True)
app.mount("/generated-assets", StaticFiles(directory=ASSET_DIRECTORY), name="generated-assets")
VIDEO_DIRECTORY.mkdir(parents=True, exist_ok=True)
app.mount("/generated-videos", StaticFiles(directory=VIDEO_DIRECTORY), name="generated-videos")
LOGGER = logging.getLogger(__name__)
SESSION_SECRET = load_session_secret().encode("utf-8")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.on_event("startup")
def initialize_postgres_storage() -> None:
    """Create PostgreSQL tables before serving APIs that rely on persisted data."""
    initialize_database()


class DuplicateCheckRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    topic: str = Field(default="", max_length=1_000)


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2_000)


class GenerateDraftRequest(BaseModel):
    max_attempts: int = Field(default=5, ge=1, le=10)
    temporary_overrides: dict[str, object] = Field(default_factory=dict)


class SettingsRequest(BaseModel):
    preferences: dict[str, object] = Field(default_factory=dict)


class AssistantChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)
    session_id: str | None = Field(default=None, max_length=64)


class SceneGenerationRequest(BaseModel):
    draft_id: int = Field(gt=0)


class VideoRenderRequest(BaseModel):
    draft_id: int = Field(gt=0)

@app.get("/")
def root():
    return {"message": "ShortsFlow AI backend is running"}


def _state_digest(state: str) -> str:
    return hmac.new(SESSION_SECRET, state.encode("utf-8"), hashlib.sha256).hexdigest()


def _save_oauth_state(state: str) -> None:
    """Persist one hashed, short-lived state record for this local app."""
    temporary_file = OAUTH_STATE_FILE.with_suffix(".tmp")
    try:
        temporary_file.write_text(
            json.dumps({"digest": _state_digest(state), "created_at": int(time.time())}),
            encoding="utf-8",
        )
        temporary_file.replace(OAUTH_STATE_FILE)
    except OSError as error:
        raise OAuthConfigurationError("Local OAuth state storage is unavailable.") from error


def _consume_oauth_state(returned_state: str | None) -> bool:
    """Validate and remove the state record so every attempt is single-use."""
    if not returned_state:
        return False
    try:
        record = json.loads(OAUTH_STATE_FILE.read_text(encoding="utf-8"))
        OAUTH_STATE_FILE.unlink(missing_ok=True)
    except (OSError, json.JSONDecodeError):
        return False
    digest = record.get("digest")
    created_at = record.get("created_at")
    return (
        isinstance(digest, str)
        and isinstance(created_at, int)
        and time.time() - created_at <= OAUTH_STATE_TTL_SECONDS
        and hmac.compare_digest(digest, _state_digest(returned_state))
    )


@app.get("/api/youtube/connect")
def connect_youtube(request: Request):
    """Start Google's browser-based OAuth consent flow."""
    state = secrets.token_urlsafe(32)
    try:
        authorization_url = get_authorization_url(CLIENT_SECRETS_FILE, OAUTH_REDIRECT_URI, state)
    except OAuthConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    _save_oauth_state(state)
    return RedirectResponse(authorization_url)


@app.get("/api/youtube/oauth/callback", name="youtube_oauth_callback")
def youtube_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """Persist an approved token, then return the browser to the frontend."""
    if not _consume_oauth_state(state):
        return JSONResponse(status_code=400, content={"detail": "Invalid or expired OAuth state."})
    if error:
        return RedirectResponse(f"{FRONTEND_URL}/?youtube=denied")
    try:
        save_authorization_token(
            CLIENT_SECRETS_FILE, TOKEN_FILE, OAUTH_REDIRECT_URI, str(request.url), state
        )
    except OAuthConfigurationError as oauth_error:
        raise HTTPException(status_code=503, detail=str(oauth_error)) from oauth_error
    except OAuthTokenExchangeError as exchange_error:
        LOGGER.warning(
            "Google token exchange reported error=%s, error_description=%s, status=%s.",
            exchange_error.error_code,
            exchange_error.error_description,
            exchange_error.http_status or "unavailable",
        )
        return RedirectResponse(f"{FRONTEND_URL}/?youtube=exchange_failed&reason={exchange_error.error_code}")
    except YouTubeAuthenticationError:
        return RedirectResponse(f"{FRONTEND_URL}/?youtube=failed")
    return RedirectResponse(f"{FRONTEND_URL}/?youtube=connected")


@app.get("/api/youtube/channel")
def youtube_channel():
    """Return the authenticated user's YouTube channel statistics."""
    try:
        return get_channel_details(CLIENT_SECRETS_FILE, TOKEN_FILE)
    except OAuthConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except YouTubeAuthenticationError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error


@app.post("/api/youtube/videos/sync")
def sync_youtube_videos():
    """Fetch all channel uploads and upsert them into the local video cache."""
    try:
        videos = get_uploaded_videos(CLIENT_SECRETS_FILE, TOKEN_FILE)
        inserted_count, updated_count = upsert_videos(videos)
        return {
            "fetched_count": len(videos),
            "inserted_count": inserted_count,
            "updated_count": updated_count,
            "total_stored_count": video_count(),
        }
    except OAuthConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except YouTubeAuthenticationError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except YouTubeSyncError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.get("/api/youtube/videos")
def stored_youtube_videos():
    """List locally cached channel videos without calling YouTube again."""
    return {"videos": list_videos()}


@app.post("/api/videos/check-duplicate")
def check_video_duplicate(proposal: DuplicateCheckRequest):
    """Compare a proposed title/topic with locally synced video metadata."""
    return check_duplicate(proposal.title, proposal.topic, list_videos())


@app.post("/api/content/generate")
def generate_content_draft(request: GenerateDraftRequest):
    """Create a duplicate-safe draft from Settings plus transient chat overrides."""
    result = generate_short_draft(request.max_attempts, request.temporary_overrides)
    if not result["accepted"]:
        return JSONResponse(status_code=409, content=result)
    return result


@app.get("/api/content/drafts")
def generated_content_drafts():
    """List locally persisted accepted Short drafts."""
    return {"drafts": list_generated_drafts()}


@app.post("/api/images/scenes/generate")
def generate_draft_scenes(request: SceneGenerationRequest):
    """Render the complete deterministic 9:16 scene sequence for one accepted draft."""
    try:
        scenes = generate_scenes(request.draft_id)
        return {"draft_id": request.draft_id, "scenes": scenes}
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/images/scenes/{draft_id}")
def generated_draft_scenes(draft_id: int):
    """List previously generated scenes for a draft in playback order."""
    return {"draft_id": draft_id, "scenes": list_scenes(draft_id)}


@app.post("/api/images/scenes/{draft_id}/validate")
def validate_draft_scenes(draft_id: int):
    """Validate resolution, required scene sequence, and text render instructions."""
    try:
        return validate_scenes(draft_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/images/scenes/{draft_id}/{scene_id}/regenerate")
def regenerate_draft_scene(draft_id: int, scene_id: str):
    """Regenerate exactly one failed or selected scene without touching others."""
    try:
        return {"scene": regenerate_scene(draft_id, scene_id)}
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/video-rendering/render")
def render_short_video(request: VideoRenderRequest):
    """Assemble validated scenes into a local 9:16 MP4 using FFmpeg."""
    try:
        return {"video": render_video(request.draft_id)}
    except VideoRenderError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/video-rendering/{draft_id}")
def rendered_short_video(draft_id: int):
    return {"draft_id": draft_id, "video": get_video(draft_id), "scenes": list_scenes(draft_id)}


@app.post("/api/video-rendering/{draft_id}/validate")
def validate_rendered_short_video(draft_id: int):
    try:
        return validate_video(draft_id)
    except VideoRenderError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/video-rendering/{draft_id}/rerender")
def rerender_short_video(draft_id: int):
    """Rebuild the MP4 only; existing validated images are retained."""
    try:
        return {"video": render_video(draft_id)}
    except VideoRenderError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/chat/messages")
def send_chat_preference_message(chat_message: ChatMessageRequest):
    """Store a local planning message and return extracted Shorts preferences."""
    return send_chat_message(chat_message.message)


@app.get("/api/chat/messages")
def chat_history():
    """Return the locally persisted planning conversation."""
    return {"messages": get_chat_history()}


@app.get("/api/chat/preferences")
def chat_preferences():
    """Compatibility endpoint for permanent Settings defaults."""
    return {"preferences": get_preferences()}


@app.get("/api/settings")
def settings():
    """Return the permanent channel/content defaults owned by Settings."""
    return {"preferences": get_preferences()}


@app.put("/api/settings")
def update_settings(request: SettingsRequest):
    """Persist the permanent channel/content defaults configured in Settings."""
    return {"preferences": save_preferences(request.preferences)}


@app.post("/api/chat/reset")
def reset_chat():
    """Clear chat history and current draft context, retaining Settings."""
    reset_chat_preferences()
    return {"messages": [], "preferences": get_preferences()}


@app.post("/api/assistant/chat")
def chat_with_assistant(request: AssistantChatRequest):
    """Answer with the local Ollama provider and controlled read-only tools only."""
    try:
        return assistant_chat(request.message, request.session_id)
    except AIProviderError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/api/assistant/conversations/{session_id}")
def assistant_conversation_history(session_id: str):
    return {"messages": get_assistant_history(session_id)}


@app.post("/api/assistant/conversations/{session_id}/clear")
def clear_assistant_conversation(session_id: str):
    clear_assistant_history(session_id)
    return {"messages": []}
