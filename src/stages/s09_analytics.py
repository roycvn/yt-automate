"""Stage 09 — Analytics. Pull metrics for published videos; feed back into ideation (s01)."""
from __future__ import annotations

from ..clients.youtube import YouTubeClient


def run(youtube_id: str, yt: YouTubeClient) -> dict:
    return yt.fetch_metrics(youtube_id)
