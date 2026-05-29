from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class Language(str, Enum):
    HINDI = "hi"
    TELUGU = "te"


class Stage(str, Enum):
    OWNERSHIP = "s00_ownership"
    IDEATION = "s01_ideation"
    LOCALIZE = "s02_localize"
    WATERMARK = "s03_watermark"
    ASSEMBLE = "s04_assemble"
    CLIP = "s05_clip"
    SEO = "s06_seo"
    THUMBNAIL = "s07_thumbnail"
    PUBLISH = "s08_publish"
    ANALYTICS = "s09_analytics"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    QUARANTINED = "quarantined"


class SourceVideo(BaseModel):
    id: str
    path: Path
    owner_confirmed: bool = False
    title_canonical: str | None = None
    duration_s: float | None = None
    resolution: tuple[int, int] | None = None


class LocalizedMaster(BaseModel):
    source_id: str
    language: Language
    master_path: Path
    captions_path: Path | None = None
    watermarked: bool = False


class ClipSet(BaseModel):
    master_id: str
    language: Language
    shorts: list[Path] = []
    captions: list[Path] = []


class SeoMeta(BaseModel):
    language: Language
    title: str
    description: str
    tags: list[str] = []
    chapters: list[str] = []


class PublishResult(BaseModel):
    youtube_id: str
    language: Language
    fmt: Literal["long", "short"]
    scheduled_at: datetime
