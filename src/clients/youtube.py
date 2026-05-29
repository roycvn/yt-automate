"""YouTube Data + Analytics API wrapper. Quota-aware; one channel/refresh-token per language.

Quota note (PLAN.md §7): default ~10,000 units/day, an upload ~1,600 units => ~6 uploads/day
per project. Pace uploads via the publish queue; request quota increase / use multiple projects
for higher volume.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from ..models import Language, PublishResult, SeoMeta


class YouTubeClient:
    UPLOAD_COST = 1600

    def __init__(self, client_id: str, client_secret: str,
                 refresh_token: str, channel_id: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.channel_id = channel_id

    def _service(self):
        # TODO: build google-api-python-client service from OAuth2 refresh token
        raise NotImplementedError("build youtube + youtubeAnalytics services")

    def upload(self, video: Path, seo: SeoMeta, language: Language,
               fmt: Literal["long", "short"], publish_at: datetime,
               captions: Path | None = None,
               privacy: str = "private") -> PublishResult:
        # TODO: resumable upload via videos.insert; set status.publishAt=publish_at,
        # snippet localized title/description/tags, defaultAudioLanguage=language.value;
        # then captions.insert if provided.
        raise NotImplementedError("upload: implement resumable videos.insert with scheduling")

    def fetch_metrics(self, youtube_id: str) -> dict:
        # TODO: youtubeAnalytics reports for views, watch time, CTR, retention
        raise NotImplementedError("fetch_metrics: youtubeAnalytics.reports.query")
