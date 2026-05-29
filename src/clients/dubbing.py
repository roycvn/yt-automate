"""Dubbing engine wrapper — transcribe + translate + synthesize to a target language.

Primary: ElevenLabs Dubbing API. Fallback: Whisper transcript -> Claude translate -> TTS.
Used by KliprClient.dub() when klipr.in has no native /v1/dub.
"""
from __future__ import annotations

from pathlib import Path

from ..models import Language, LocalizedMaster


class DubbingClient:
    def __init__(self, provider: str, api_key: str | None,
                 artifacts_dir: Path = Path("./artifacts")):
        self.provider = provider
        self.api_key = api_key
        self.artifacts_dir = artifacts_dir

    async def dub(self, source: Path, frm: Language, to: Language,
                  source_id: str) -> LocalizedMaster:
        out_dir = self.artifacts_dir / source_id / to.value
        out_dir.mkdir(parents=True, exist_ok=True)
        # TODO: implement ElevenLabs Dubbing API call:
        #   1. submit `source` with target_lang=to.value
        #   2. poll until done
        #   3. download dubbed audio track + .srt captions
        audio_path = out_dir / "narration.mp3"
        captions_path = out_dir / "captions.srt"
        raise NotImplementedError(
            f"DubbingClient.dub not implemented (provider={self.provider}); "
            f"would produce {audio_path} + {captions_path}"
        )
