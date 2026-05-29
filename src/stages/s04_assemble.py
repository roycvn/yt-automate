"""Stage 04 — Assemble. Mux watermarked video + per-language narration (+ BGM) into a master."""
from __future__ import annotations

from pathlib import Path

from .. import ffmpeg_ops
from ..models import Language, LocalizedMaster


def run(watermarked_video: Path, narration: Path | None, out: Path,
        source_id: str, language: Language, captions: Path | None = None) -> LocalizedMaster:
    if narration is not None:
        ffmpeg_ops.replace_audio(watermarked_video, narration, out)
    else:
        out = watermarked_video  # original-language master keeps source audio
    return LocalizedMaster(source_id=source_id, language=language,
                           master_path=out, captions_path=captions, watermarked=True)
