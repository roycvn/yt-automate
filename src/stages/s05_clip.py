"""Stage 05 — Clip. Generate vertical Shorts + captions from the master via klipr (or fallback)."""
from __future__ import annotations

from ..clients.klipr import KliprClient
from ..models import ClipSet, LocalizedMaster


async def run(master: LocalizedMaster, klipr: KliprClient,
              count: int = 8, max_duration_s: int = 60) -> ClipSet:
    return await klipr.clip(master.master_path, master.language, master.source_id,
                            count=count, max_duration_s=max_duration_s)
