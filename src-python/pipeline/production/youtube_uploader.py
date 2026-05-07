"""
Snap Recap — YouTubeUploader

Uploads an MP4 file to YouTube via the YouTube Data API v3.

OAuth tokens are stored with file permissions 600 (owner read/write only)
to prevent accidental credential exposure.

Security notes:
  - Tokens are never logged or included in checkpoints.
  - File permissions are set to 600 immediately after writing.
  - The upload uses resumable upload to handle large files.
"""

from __future__ import annotations

import json
import logging
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

logger = logging.getLogger(__name__)

# YouTube video URL template
_YOUTUBE_URL_TEMPLATE = "https://www.youtube.com/watch?v={video_id}"

# YouTube API scopes required for upload
_YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class VideoMetadata:
    """Metadata for a YouTube video upload."""

    title: str
    description: str
    tags: list
    category_id: str = "22"          # "People & Blogs"
    privacy_status: str = "private"  # "private" | "unlisted" | "public"


@dataclass
class OAuthCredentials:
    """OAuth 2.0 credentials for YouTube API access."""

    client_id: str
    client_secret: str
    token_path: Path          # path to store/load the OAuth token file
    redirect_uri: str = "urn:ietf:wg:oauth:2.0:oob"


# ---------------------------------------------------------------------------
# YouTubeUploader
# ---------------------------------------------------------------------------


class YouTubeUploader:
    """Uploads videos to YouTube via the Data API v3.

    Preconditions:
        - video path exists and is a valid MP4 file
        - credentials.client_id and client_secret are non-empty
        - credentials.token_path's parent directory is writable

    Postconditions:
        - Returns the YouTube video URL on success
        - OAuth token file is written with permissions 600
    """

    def upload(
        self,
        video: Path,
        metadata: VideoMetadata,
        credentials: OAuthCredentials,
    ) -> str:
        """Upload a video to YouTube.

        Args:
            video: Path to the MP4 file to upload.
            metadata: VideoMetadata (title, description, tags, etc.).
            credentials: OAuthCredentials for YouTube API access.

        Returns:
            YouTube video URL (https://www.youtube.com/watch?v=<id>).

        Raises:
            FileNotFoundError: If the video file does not exist.
            RuntimeError: If the upload fails.
        """
        video = Path(video)
        if not video.exists():
            raise FileNotFoundError(f"Video file not found: {video}")

        youtube = self._build_youtube_service(credentials)
        video_id = self._execute_upload(youtube, video, metadata)
        url = _YOUTUBE_URL_TEMPLATE.format(video_id=video_id)
        logger.info("YouTube upload complete: %s", url)
        return url

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_youtube_service(self, credentials: OAuthCredentials):
        """Build an authenticated YouTube API service.

        Loads existing OAuth tokens from disk if available; otherwise
        initiates the OAuth flow.

        Args:
            credentials: OAuthCredentials.

        Returns:
            Authenticated googleapiclient.discovery Resource.
        """
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError(
                "google-api-python-client and google-auth-oauthlib are required. "
                "Install with: pip install google-api-python-client google-auth-oauthlib"
            ) from exc

        token_path = Path(credentials.token_path)
        creds = None

        # Load existing token
        if token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(
                    str(token_path), _YOUTUBE_SCOPES
                )
            except Exception as exc:
                logger.warning("Failed to load OAuth token from %s: %s", token_path, exc)
                creds = None

        # Refresh or re-authenticate
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as exc:
                logger.warning("Token refresh failed: %s", exc)
                creds = None

        if not creds or not creds.valid:
            client_config = {
                "installed": {
                    "client_id": credentials.client_id,
                    "client_secret": credentials.client_secret,
                    "redirect_uris": [credentials.redirect_uri],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
            flow = InstalledAppFlow.from_client_config(client_config, _YOUTUBE_SCOPES)
            creds = flow.run_local_server(port=0)

        # Persist token with restricted permissions (600)
        _save_token_secure(creds, token_path)

        return build("youtube", "v3", credentials=creds)

    def _execute_upload(self, youtube, video: Path, metadata: VideoMetadata) -> str:
        """Execute the resumable upload to YouTube.

        Args:
            youtube: Authenticated YouTube API service.
            video: Path to the MP4 file.
            metadata: VideoMetadata.

        Returns:
            YouTube video ID string.

        Raises:
            RuntimeError: If the upload fails after retries.
        """
        try:
            from googleapiclient.http import MediaFileUpload
        except ImportError as exc:
            raise RuntimeError("google-api-python-client is required.") from exc

        body = {
            "snippet": {
                "title": metadata.title,
                "description": metadata.description,
                "tags": metadata.tags,
                "categoryId": metadata.category_id,
            },
            "status": {
                "privacyStatus": metadata.privacy_status,
            },
        }

        media = MediaFileUpload(
            str(video),
            mimetype="video/mp4",
            resumable=True,
            chunksize=256 * 1024,  # 256 KB chunks
        )

        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    logger.debug(
                        "Upload progress: %.1f%%", status.progress() * 100
                    )
            except Exception as exc:
                raise RuntimeError(f"YouTube upload failed: {exc}") from exc

        video_id = response.get("id")
        if not video_id:
            raise RuntimeError(
                f"YouTube upload returned no video ID. Response: {response}"
            )

        return video_id


# ---------------------------------------------------------------------------
# Token persistence helper
# ---------------------------------------------------------------------------


def _save_token_secure(creds, token_path: Path) -> None:
    """Save OAuth credentials to disk with permissions 600.

    Args:
        creds: google.oauth2.credentials.Credentials instance.
        token_path: Destination path for the token JSON file.
    """
    token_path = Path(token_path)
    token_path.parent.mkdir(parents=True, exist_ok=True)

    token_data = creds.to_json()

    # Write to a temp file first, then rename (atomic on POSIX)
    tmp_path = token_path.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(token_data)

        # Set permissions to 600 before moving into place
        try:
            os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError as exc:
            logger.warning("Could not set token file permissions: %s", exc)

        os.replace(tmp_path, token_path)
        logger.debug("OAuth token saved to %s (mode 600)", token_path)
    except Exception as exc:
        logger.error("Failed to save OAuth token: %s", exc)
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
