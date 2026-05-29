"""Stage 08 — Publish. Quota-aware upload + scheduling to the per-language channel."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from ..clients.youtube import YouTubeClient
from ..models import Language, PublishResult, SeoMeta


def next_slot(base: datetime, index: int, cadence_hours: int) -> datetime:
    return base + timedelta(hours=cadence_hours * index)


def run(video: Path, seo: SeoMeta, language: Language,
        fmt: Literal["long", "short"], publish_at: datetime,
        yt: YouTubeClient, captions: Path | None = None,
        privacy: str = "private") -> PublishResult:
    return yt.upload(video, seo, language, fmt, publish_at, captions, privacy)
