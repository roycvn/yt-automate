"""Stage 00 — Ownership gate. Nothing proceeds without owner_confirmed=true."""
from __future__ import annotations

import json
from pathlib import Path

from ..models import SourceVideo


def load_manifest(path: Path) -> list[SourceVideo]:
    data = json.loads(Path(path).read_text())
    return [SourceVideo(**v) for v in data.get("videos", [])]


def check(video: SourceVideo) -> bool:
    """Return True if the video may enter the pipeline, else it is quarantined."""
    return bool(video.owner_confirmed)
