"""Stage 07 — Thumbnail. Generate image + overlay large Devanagari/Telugu text per language."""
from __future__ import annotations

from pathlib import Path

from ..models import Language, SeoMeta


def run(theme: str, seo: SeoMeta, language: Language, out: Path) -> Path:
    # TODO: image-gen API for background, Pillow overlay of big language text + bright face
    raise NotImplementedError("s07 thumbnail")
