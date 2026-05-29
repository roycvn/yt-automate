"""YouTube Data API v3 wrapper — resumable upload from a signed video URL.

Auth: OAuth2 refresh token per channel (one channel per language). Build the
refresh token once via the consent flow with scope
https://www.googleapis.com/auth/youtube.upload (see scripts/youtube_auth.py).

Quota (PLAN.md §7): videos.insert ~1600 units; default ~10k/day => ~6
uploads/day per GCP project. Pace via the cron / request a quota increase.
"""
from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal

import httpx

UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"


class YouTubeClient:
    UPLOAD_COST = 1600

    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token

    def _service(self):
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=self.refresh_token,
            client_id=self.client_id,
            client_secret=self.client_secret,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=[UPLOAD_SCOPE],
        )
        return build("youtube", "v3", credentials=creds, cache_discovery=False)

    def set_thumbnail(self, video_id: str, image_path) -> None:
        from googleapiclient.http import MediaFileUpload
        media = MediaFileUpload(str(image_path), mimetype="image/png")
        self._service().thumbnails().set(videoId=video_id, media_body=media).execute()

    def upload_from_file(self, path, title: str, description: str = "",
                         tags: list[str] | None = None,
                         privacy: Literal["private", "unlisted", "public"] = "private",
                         publish_at: datetime | None = None,
                         language: str | None = None,
                         made_for_kids: bool = False) -> str:
        """Upload a local video file. Returns the YouTube video id."""
        from googleapiclient.http import MediaFileUpload

        status: dict = {"privacyStatus": privacy, "selfDeclaredMadeForKids": made_for_kids}
        if publish_at is not None:
            status["privacyStatus"] = "private"
            status["publishAt"] = publish_at.isoformat()
        snippet: dict = {"title": title[:100], "description": description[:5000],
                         "tags": (tags or [])[:30]}
        if language:
            snippet["defaultAudioLanguage"] = language
            snippet["defaultLanguage"] = language

        media = MediaFileUpload(str(path), mimetype="video/mp4",
                                chunksize=8 * 1024 * 1024, resumable=True)
        request = self._service().videos().insert(
            part="snippet,status",
            body={"snippet": snippet, "status": status},
            media_body=media,
        )
        response = None
        while response is None:
            _, response = request.next_chunk()
        return response["id"]

    def upload_from_url(self, video_url: str, title: str, description: str = "",
                        tags: list[str] | None = None,
                        privacy: Literal["private", "unlisted", "public"] = "private",
                        publish_at: datetime | None = None,
                        language: str | None = None,
                        made_for_kids: bool = False) -> str:
        """Download a video from `video_url` and upload it. Returns the YouTube video id."""
        from googleapiclient.http import MediaFileUpload

        status: dict = {"privacyStatus": privacy, "selfDeclaredMadeForKids": made_for_kids}
        if publish_at is not None:
            # Scheduling requires privacyStatus=private + an RFC3339 publishAt.
            status["privacyStatus"] = "private"
            status["publishAt"] = publish_at.isoformat()

        snippet: dict = {"title": title[:100], "description": description[:5000],
                         "tags": (tags or [])[:30]}
        if language:
            snippet["defaultAudioLanguage"] = language
            snippet["defaultLanguage"] = language

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=True) as tmp:
            with httpx.stream("GET", video_url, timeout=300.0, follow_redirects=True) as r:
                r.raise_for_status()
                for chunk in r.iter_bytes():
                    tmp.write(chunk)
            tmp.flush()

            media = MediaFileUpload(tmp.name, mimetype="video/mp4",
                                    chunksize=8 * 1024 * 1024, resumable=True)
            request = self._service().videos().insert(
                part="snippet,status",
                body={"snippet": snippet, "status": status},
                media_body=media,
            )
            response = None
            while response is None:
                _, response = request.next_chunk()
        return response["id"]
