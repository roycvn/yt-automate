"""Stage 02 — Localize. Produce a narration track + captions per target language
(Hindi + Telugu) via the dubbing engine. Visuals are shared; only audio/captions differ."""
from __future__ import annotations

from pathlib import Path

from ..clients.klipr import KliprClient
from ..models import Language, LocalizedMaster, SourceVideo


async def run(video: SourceVideo, source_lang: Language, target_lang: Language,
              klipr: KliprClient) -> LocalizedMaster:
    if target_lang == source_lang:
        # no dubbing needed; caller assembles with original audio
        return LocalizedMaster(source_id=video.id, language=target_lang,
                               master_path=Path(video.path))
    return await klipr.dub(Path(video.path), source_lang, target_lang, video.id)
