"""OAuth and YouTube Data API helpers kept separate from the FastAPI routes."""

import logging
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

YOUTUBE_READONLY_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
SCOPES = [YOUTUBE_READONLY_SCOPE]
LOGGER = logging.getLogger(__name__)


class OAuthConfigurationError(Exception):
    """The local Google OAuth configuration is absent or unusable."""


class YouTubeAuthenticationError(Exception):
    """The user needs to connect or reconnect their YouTube account."""


class OAuthTokenExchangeError(YouTubeAuthenticationError):
    """A safe-to-report error returned by Google's token endpoint."""

    def __init__(self, error_code: str, error_description: str, http_status: int | None):
        self.error_code = error_code
        self.error_description = error_description
        self.http_status = http_status
        super().__init__(f"Google token exchange failed: {error_code}.")


class YouTubeSyncError(Exception):
    """The connected channel's uploads could not be fetched."""


def _require_client_secrets(client_secrets_file: Path) -> None:
    if not client_secrets_file.is_file():
        raise OAuthConfigurationError("Google OAuth credentials are not configured. Add backend/client_secret.json locally.")


def _create_flow(
    client_secrets_file: Path,
    redirect_uri: str,
    state: str | None = None,
) -> Flow:
    _require_client_secrets(client_secrets_file)
    callback_host = urlparse(redirect_uri).hostname
    if callback_host in {"localhost", "127.0.0.1", "::1"}:
        # Google permits HTTP only for local development callbacks. OAuthlib
        # requires this explicit opt-in before exchanging the local code.
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
    try:
        flow = Flow.from_client_secrets_file(
            str(client_secrets_file),
            scopes=SCOPES,
            state=state,
            autogenerate_code_verifier=False,
        )
    except (OSError, ValueError) as error:
        raise OAuthConfigurationError("Google OAuth credentials could not be loaded.") from error
    flow.redirect_uri = redirect_uri
    return flow


def get_authorization_url(client_secrets_file: Path, redirect_uri: str, state: str) -> str:
    flow = _create_flow(client_secrets_file, redirect_uri, state)
    authorization_url, _ = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
    return authorization_url


def save_authorization_token(
    client_secrets_file: Path,
    token_file: Path,
    redirect_uri: str,
    authorization_response: str,
    state: str,
) -> None:
    flow = _create_flow(client_secrets_file, redirect_uri, state)
    try:
        flow.fetch_token(authorization_response=authorization_response)
        token_file.write_text(flow.credentials.to_json(), encoding="utf-8")
    except Exception as error:
        error_code = str(getattr(error, "error", "unknown_error"))
        error_description = str(getattr(error, "description", "No description returned by Google."))
        status_code = getattr(error, "status_code", None)
        safe_code = error_code if re.fullmatch(r"[a-z_]+", error_code) else "unknown_error"
        safe_description = error_description[:500]
        LOGGER.warning(
            "Google OAuth token exchange failed (type=%s, error=%s, error_description=%s, status=%s).",
            type(error).__name__,
            safe_code,
            safe_description,
            status_code if isinstance(status_code, int) else "unavailable",
        )
        raise OAuthTokenExchangeError(safe_code, safe_description, status_code if isinstance(status_code, int) else None) from error


def _load_credentials(client_secrets_file: Path, token_file: Path) -> Credentials:
    _require_client_secrets(client_secrets_file)
    if not token_file.is_file():
        raise YouTubeAuthenticationError("No YouTube account is connected yet.")
    try:
        credentials = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            token_file.write_text(credentials.to_json(), encoding="utf-8")
    except Exception as error:
        raise YouTubeAuthenticationError("Your YouTube connection has expired. Please reconnect.") from error
    if not credentials.valid:
        raise YouTubeAuthenticationError("Your YouTube connection has expired. Please reconnect.")
    return credentials


def get_channel_details(client_secrets_file: Path, token_file: Path) -> dict[str, str | int]:
    credentials = _load_credentials(client_secrets_file, token_file)
    try:
        youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
        response = youtube.channels().list(part="snippet,statistics", mine=True).execute()
    except HttpError as error:
        if error.resp.status in {401, 403}:
            raise YouTubeAuthenticationError("YouTube authorization was rejected. Please reconnect.") from error
        raise YouTubeAuthenticationError("YouTube channel details could not be fetched.") from error
    channels = response.get("items", [])
    if not channels:
        raise YouTubeAuthenticationError("No YouTube channel was found for this Google account.")
    channel = channels[0]
    statistics = channel.get("statistics", {})
    return {
        "channel_id": channel["id"], "title": channel.get("snippet", {}).get("title", "Untitled channel"),
        "description": channel.get("snippet", {}).get("description", ""),
        "subscriber_count": int(statistics.get("subscriberCount", 0)), "video_count": int(statistics.get("videoCount", 0)),
        "view_count": int(statistics.get("viewCount", 0)),
    }


def get_uploaded_videos(client_secrets_file: Path, token_file: Path) -> list[dict[str, str]]:
    """Fetch every item in the authenticated channel's uploads playlist."""
    credentials = _load_credentials(client_secrets_file, token_file)
    try:
        youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
        channel_response = youtube.channels().list(part="contentDetails", mine=True).execute()
        channels = channel_response.get("items", [])
        if not channels:
            raise YouTubeSyncError("No YouTube channel was found for this Google account.")
        uploads_playlist_id = channels[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
        if not uploads_playlist_id:
            raise YouTubeSyncError("The connected channel does not have an uploads playlist.")

        videos: list[dict[str, str]] = []
        page_token: str | None = None
        while True:
            page = youtube.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=uploads_playlist_id,
                maxResults=50,
                pageToken=page_token,
            ).execute()
            for item in page.get("items", []):
                snippet = item.get("snippet", {})
                content_details = item.get("contentDetails", {})
                video_id = content_details.get("videoId") or snippet.get("resourceId", {}).get("videoId")
                if not video_id:
                    continue
                thumbnails = snippet.get("thumbnails", {})
                thumbnail_url = next(
                    (
                        thumbnails[size]["url"]
                        for size in ("maxres", "standard", "high", "medium", "default")
                        if thumbnails.get(size, {}).get("url")
                    ),
                    "",
                )
                videos.append(
                    {
                        "youtube_video_id": video_id,
                        "title": snippet.get("title", "Untitled video"),
                        "description": snippet.get("description", ""),
                        "published_at": content_details.get("videoPublishedAt") or snippet.get("publishedAt", ""),
                        "thumbnail_url": thumbnail_url,
                    }
                )
            page_token = page.get("nextPageToken")
            if not page_token:
                break
        return videos
    except YouTubeAuthenticationError:
        raise
    except HttpError as error:
        if error.resp.status in {401, 403}:
            raise YouTubeAuthenticationError("YouTube authorization was rejected. Please reconnect.") from error
        raise YouTubeSyncError("YouTube uploads could not be fetched.") from error
