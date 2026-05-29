"""Smoke-test the real klipr batch API from yta.

Usage:
    export KLIPR_API_KEY=klipr_live_...
    python scripts/klipr_smoke.py dub  "https://www.youtube.com/watch?v=<id>" te
    python scripts/klipr_smoke.py clip "https://www.youtube.com/watch?v=<id>"
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.clients.klipr import KliprClient  # noqa: E402


async def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    cmd, source_url = sys.argv[1], sys.argv[2]
    api_key = os.environ.get("KLIPR_API_KEY", "")
    client = KliprClient(api_key)

    if cmd == "dub":
        target = sys.argv[3] if len(sys.argv) > 3 else "te"
        print(f"starting dub -> {target} ...")
        res = await client.dub_and_wait(source_url, target_language=target,
                                        source_language="hi", interval=8)
        print("status:", res.status)
        print("download_url:", res.download_url)
    elif cmd == "clip":
        print("starting auto-clip ...")
        res = await client.auto_clip_and_wait(source_url, interval=8)
        print("status:", res.status)
        print("clips/job:", res.raw.get("job"))
    else:
        print(f"unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
