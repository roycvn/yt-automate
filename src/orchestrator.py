"""Per-video orchestrator. Builds the DAG, fans out across languages, idempotent via DB.

Run:  python -m src.orchestrator
This is a wiring skeleton — each stage stub raises NotImplementedError until built.
Stages already runnable end-to-end with the local fallback: s00, s03, s04, s05.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from . import db
from .clients.claude import ClaudeClient
from .clients.dubbing import DubbingClient
from .clients.klipr import KliprClient
from .clients.youtube import YouTubeClient
from .config import load_config
from .models import Language, SourceVideo, Stage, StageStatus
from .stages import (
    s00_ownership, s01_ideation, s02_localize, s03_watermark, s04_assemble,
    s05_clip, s06_seo, s07_thumbnail, s08_publish, s09_analytics,
)


def build_clients(cfg: dict):
    artifacts = Path(cfg["storage"]["artifacts_dir"])
    dubbing = DubbingClient(cfg["dubbing"]["provider"], None, artifacts)
    klipr = KliprClient(
        api_key=None,
        base_url=cfg["klipr"]["base_url"],
        use_real_api=cfg["klipr"]["use_real_api"],
        dubbing_client=dubbing,
        artifacts_dir=artifacts,
    )
    claude = ClaudeClient(cfg["seo"]["model"])
    return klipr, claude


async def process_video(video: SourceVideo, cfg: dict, conn) -> None:
    artifacts = Path(cfg["storage"]["artifacts_dir"])
    klipr, claude = build_clients(cfg)
    source_lang = Language.HINDI  # source assumed Hindi; configurable later

    # s00 ownership gate
    if not s00_ownership.check(video):
        db.set_status(conn, video.id, "", Stage.OWNERSHIP.value, StageStatus.QUARANTINED.value)
        print(f"[quarantine] {video.id} — owner not confirmed")
        return
    db.set_status(conn, video.id, "", Stage.OWNERSHIP.value, StageStatus.DONE.value)

    base_time = datetime.now(timezone.utc)
    for li, lang_str in enumerate(cfg["languages"]):
        lang = Language(lang_str)
        channel = next(c for c in cfg["channels"].values() if c["language"] == lang_str)
        out_dir = artifacts / video.id / lang_str
        out_dir.mkdir(parents=True, exist_ok=True)

        # s03 watermark (shared visuals; per-language logo)
        wm_out = out_dir / "watermarked.mp4"
        s03_watermark.run(
            Path(video.path), Path(channel["watermark"]), wm_out,
            position=cfg["watermark"]["position"],
            opacity=cfg["watermark"]["opacity"], scale=cfg["watermark"]["scale"],
        )

        # s02 localize (dub if not source language)
        master_loc = await s02_localize.run(video, source_lang, lang, klipr)

        # s04 assemble (mux dubbed narration onto watermarked video)
        narration = master_loc.master_path if lang != source_lang else None
        master = s04_assemble.run(wm_out, narration, out_dir / "master.mp4",
                                  video.id, lang, master_loc.captions_path)

        # s05 clip
        clips = await s05_clip.run(master, klipr,
                                   count=cfg["clip"]["count"],
                                   max_duration_s=cfg["clip"]["max_duration_s"])
        db.set_status(conn, video.id, lang_str, Stage.CLIP.value,
                      StageStatus.DONE.value, artifact=str(out_dir))

        # s06 seo, s07 thumbnail, s08 publish, s09 analytics — wire once clients implemented
        print(f"[ok] {video.id} [{lang_str}] watermarked+assembled+clipped: {len(clips.shorts)} shorts")


async def main():
    cfg = load_config()
    videos = s00_ownership.load_manifest(Path("source_manifest.json"))
    with db.connect(cfg["storage"]["db_path"]) as conn:
        for v in videos:
            await process_video(v, cfg, conn)


if __name__ == "__main__":
    asyncio.run(main())
