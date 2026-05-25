"""
packages/tools/youtube_client.py
YouTube Data API v3 client — OAuth2 token refresh + resumable video upload.

Uses httpx directly (no google-api-python-client required).

Upload flow
-----------
1. POST https://oauth2.googleapis.com/token  →  short-lived access_token
2. POST https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable
       with JSON metadata  →  upload session URI (Location header)
3. PUT  {upload_uri}  streaming the MP4 bytes  →  {"id": "VIDEO_ID", ...}

Required env vars
-----------------
YOUTUBE_CLIENT_ID
YOUTUBE_CLIENT_SECRET
YOUTUBE_REFRESH_TOKEN   ← run scripts/youtube_auth.py once to obtain this

Optional
--------
YOUTUBE_PRIVACY   default "unlisted" — set to "public" when ready to go live
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

_TOKEN_URL  = "https://oauth2.googleapis.com/token"
_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"

# YouTube category IDs (used in video metadata)
_CATEGORY_SCIENCE_TECH = "28"
_CATEGORY_PEOPLE_BLOGS = "22"


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def youtube_available() -> bool:
    """True when all three OAuth credentials are configured."""
    return all([
        os.getenv("YOUTUBE_CLIENT_ID"),
        os.getenv("YOUTUBE_CLIENT_SECRET"),
        os.getenv("YOUTUBE_REFRESH_TOKEN"),
    ])


async def upload_video(
    video_path: Path,
    title: str,
    description: str,
    tags: list[str],
    privacy: str | None = None,
    category_id: str = _CATEGORY_SCIENCE_TECH,
) -> str:
    """
    Upload a video file to YouTube and return the video_id.

    privacy defaults to YOUTUBE_PRIVACY env var, then "unlisted".
    Raises RuntimeError on API or upload failure.
    """
    privacy = privacy or os.getenv("YOUTUBE_PRIVACY", "unlisted")
    file_size = video_path.stat().st_size

    log.info("[YOUTUBE] Starting upload | file=%s size=%.1f MB privacy=%s",
             video_path.name, file_size / (1024 ** 2), privacy)

    access_token = await _refresh_access_token()
    upload_uri   = await _create_upload_session(
        access_token, title, description, tags, privacy, file_size, category_id,
    )
    video_id = await _stream_upload(upload_uri, video_path, access_token, file_size)

    log.info("[YOUTUBE] ✓ Uploaded | video_id=%s url=https://youtu.be/%s",
             video_id, video_id)
    return video_id


# ---------------------------------------------------------------------------
# Internal — token management
# ---------------------------------------------------------------------------

async def _refresh_access_token() -> str:
    """Exchange refresh_token for a short-lived access_token."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            _TOKEN_URL,
            data={
                "client_id":     os.getenv("YOUTUBE_CLIENT_ID", ""),
                "client_secret": os.getenv("YOUTUBE_CLIENT_SECRET", ""),
                "refresh_token": os.getenv("YOUTUBE_REFRESH_TOKEN", ""),
                "grant_type":    "refresh_token",
            },
        )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Token refresh failed {resp.status_code}: {resp.text[:300]}"
        )
    token = resp.json().get("access_token", "")
    if not token:
        raise RuntimeError(f"No access_token in response: {resp.json()}")
    return token


# ---------------------------------------------------------------------------
# Internal — upload session
# ---------------------------------------------------------------------------

async def _create_upload_session(
    access_token: str,
    title: str,
    description: str,
    tags: list[str],
    privacy: str,
    file_size: int,
    category_id: str,
) -> str:
    """
    Initiate a resumable upload session.
    Returns the upload URI from the Location header.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            _UPLOAD_URL,
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={
                "Authorization":          f"Bearer {access_token}",
                "Content-Type":           "application/json",
                "X-Upload-Content-Type":  "video/mp4",
                "X-Upload-Content-Length": str(file_size),
            },
            json={
                "snippet": {
                    "title":       title[:100],
                    "description": description[:5000],
                    "tags":        tags[:500],
                    "categoryId":  category_id,
                },
                "status": {
                    "privacyStatus": privacy,
                },
            },
        )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Upload session creation failed {resp.status_code}: {resp.text[:300]}"
        )
    upload_uri = resp.headers.get("Location", "")
    if not upload_uri:
        raise RuntimeError("YouTube did not return an upload URI in Location header")
    log.debug("[YOUTUBE] Upload session created | uri_prefix=%s", upload_uri[:60])
    return upload_uri


# ---------------------------------------------------------------------------
# Internal — streaming upload
# ---------------------------------------------------------------------------

async def _stream_upload(
    upload_uri: str,
    video_path: Path,
    access_token: str,
    file_size: int,
) -> str:
    """
    Stream the MP4 file to the resumable upload URI.
    Returns the video_id on success.
    """
    with open(video_path, "rb") as fh:
        async with httpx.AsyncClient(timeout=600.0) as client:
            resp = await client.put(
                upload_uri,
                content=fh,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type":  "video/mp4",
                    "Content-Length": str(file_size),
                },
            )

    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Video upload failed {resp.status_code}: {resp.text[:400]}"
        )

    video_id = resp.json().get("id", "")
    if not video_id:
        raise RuntimeError(f"No video id in upload response: {resp.text[:200]}")
    return video_id
