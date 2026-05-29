"""Produce a fully-finished video from the existing 3-scene build:
intro/outro cards + ambient drone + klipr-burned Hindi captions.

Env: KLIPR_API_KEY, NEXT_PUBLIC_SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.generate.finishing import build_finished_skeleton  # noqa: E402
from src.clients.storage import upload_and_sign  # noqa: E402
from src.clients.klipr import KliprClient  # noqa: E402


async def main() -> None:
    data = json.loads(Path("artifacts/sample_script.json").read_text())
    from types import SimpleNamespace
    scenes = [SimpleNamespace(**s) for s in data["scenes"][:3]]
    imgs = [Path(f"artifacts/build/img_{s.id:02d}.png") for s in scenes]
    auds = [Path(f"artifacts/build/aud_{s.id:02d}.wav") for s in scenes]

    work = Path("artifacts/finish")
    finished, ass = build_finished_skeleton(
        scenes, imgs, auds, work,
        intro_title=data["title_hi"],
        outro_text="TheStoryBoardz — सब्सक्राइब करें 🔔",
    )
    Path(work / "captions.ass").write_text(ass)
    print("skeleton:", finished, finished.stat().st_size, "bytes")

    key = f"finish-test/{int(time.time())}.mp4"
    url = upload_and_sign(finished, key)
    print("uploaded, signed url ready")

    client = KliprClient(os.environ["KLIPR_API_KEY"])
    res = await client.caption_burn(url, ass)
    print("caption-burn:", res.status, res.download_url)

    # download the captioned result, then re-encode player-safe
    import httpx
    from src.generate.finishing import player_safe
    raw = Path("artifacts/finish/final_raw.mp4")
    with httpx.stream("GET", res.download_url, timeout=300) as r:
        r.raise_for_status()
        with open(raw, "wb") as f:
            for c in r.iter_bytes():
                f.write(c)
    out = player_safe(raw, Path("artifacts/finish/final.mp4"))
    print("FINAL:", out, out.stat().st_size, "bytes")


if __name__ == "__main__":
    asyncio.run(main())
