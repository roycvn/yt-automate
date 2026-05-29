"""Stage 01 — Ideation/metadata. Derive canonical title + theme (Claude), informed by
the proven niche patterns (archetype + dual-language title template)."""
from __future__ import annotations

from ..clients.claude import ClaudeClient
from ..models import SourceVideo


def run(video: SourceVideo, claude: ClaudeClient) -> dict:
    # TODO: ask Claude for {theme, hook, translit} based on video + niche patterns
    raise NotImplementedError("s01 ideation")
