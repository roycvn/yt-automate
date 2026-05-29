"""Per-scene narration via klipr's /api/batch/tts.

yta no longer talks to Sarvam directly — TTS goes through klipr (same
KLIPR_API_KEY). Returns one WAV per scene so assembly syncs each image to its
narration.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from ..clients.klipr import KliprClient


def _client() -> KliprClient:
    return KliprClient(os.environ["KLIPR_API_KEY"])


def synthesize(text: str, dest: Path, language: str = "hi",
               speaker: str = "anushka", **_) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = asyncio.run(_client().tts(text, language=language, speaker=speaker))
    dest.write_bytes(data)
    return dest


def synthesize_scenes(scenes: list, out_dir: Path, language: str = "hi",
                      speaker: str = "anushka") -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for sc in scenes:
        p = out_dir / f"scene_{sc.id:02d}.wav"
        synthesize(sc.narration, p, language=language, speaker=speaker)
        paths.append(p)
    return paths
