"""Storage upload via klipr's /api/batch/upload.

yta no longer holds the Supabase service-role key — uploads go through klipr,
which returns a 1-hour signed URL we can hand back to klipr's other endpoints
(caption-burn, dub).
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from .klipr import KliprClient


def _client() -> KliprClient:
    return KliprClient(os.environ["KLIPR_API_KEY"])


def upload_and_sign(path: Path, key: str | None = None, **_) -> str:
    """Upload a local file via klipr and return a klipr-fetchable signed URL."""
    return asyncio.run(_client().upload_file(Path(path)))
