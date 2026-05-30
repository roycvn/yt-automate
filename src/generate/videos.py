"""Per-scene AI video generation via klipr's /api/batch/video (fal.ai).

The motion-video counterpart to generate/images.py. Instead of a still image
per scene (later ken-burns-zoomed in ffmpeg), each scene becomes a short
generated clip in the configured style (2d | 3d | real). yta still owns
narration, assembly and captions — klipr just produces the raw motion.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from ..clients.klipr import KliprClient, VideoStyle


def _client() -> KliprClient:
    return KliprClient(os.environ["KLIPR_API_KEY"])


def generate_scene_video(prompt: str, dest: Path, *, style: VideoStyle = "2d",
                         aspect_ratio: str = "16:9", duration_seconds: int = 5) -> Path:
    """Generate one scene clip (text-to-video) and save it to dest (mp4)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    return asyncio.run(_client().generate_video(
        prompt, dest, mode="text", style=style,
        aspect_ratio=aspect_ratio, duration_seconds=duration_seconds))


def generate_scene_videos(scenes: list, out_dir: Path, *, style: VideoStyle = "2d",
                          aspect_ratio: str = "16:9",
                          duration_seconds: int = 5) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for sc in scenes:
        p = out_dir / f"scene_{sc.id:02d}.mp4"
        generate_scene_video(sc.image_prompt, p, style=style,
                             aspect_ratio=aspect_ratio,
                             duration_seconds=duration_seconds)
        paths.append(p)
    return paths
