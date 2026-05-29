"""Stage 03 — Watermark. Overlay the channel logo before clipping so every Short inherits it."""
from __future__ import annotations

from pathlib import Path

from .. import ffmpeg_ops


def run(src: Path, logo: Path, out: Path, position: str = "top-right",
        opacity: float = 0.6, scale: float = 0.12) -> Path:
    return ffmpeg_ops.apply_watermark(src, logo, out, position, opacity, scale)
