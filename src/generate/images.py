"""Per-scene image generation via klipr's /api/batch/image.

yta no longer talks to Replicate directly — all image generation is centralised
on klipr (same KLIPR_API_KEY used for everything else).
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from ..clients.klipr import KliprClient


def _client() -> KliprClient:
    return KliprClient(os.environ["KLIPR_API_KEY"])


def generate_image(prompt: str, dest: Path, aspect_ratio: str = "16:9", **_) -> Path:
    """Generate one image and save it to dest (PNG)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = asyncio.run(_client().generate_image(prompt, aspect_ratio=aspect_ratio,
                                                output_format="png"))
    dest.write_bytes(data)
    return dest


def generate_scene_images(scenes: list, out_dir: Path, aspect_ratio: str = "16:9") -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for sc in scenes:
        p = out_dir / f"scene_{sc.id:02d}.png"
        generate_image(sc.image_prompt, p, aspect_ratio=aspect_ratio)
        paths.append(p)
    return paths
