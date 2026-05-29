"""Per-scene image generation via Replicate (Flux).

One image per scene, 9:16 for Shorts-friendly vertical or 16:9 for long-form.
Style consistency comes from the prompts (the script writer bakes the same
style prefix into every scene's image_prompt).

Env: REPLICATE_API_TOKEN
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import httpx

# Flux Schnell — fast + cheap (~$0.003/image). Good enough for story scenes.
FLUX_MODEL = "black-forest-labs/flux-schnell"
API = "https://api.replicate.com/v1"


def _headers() -> dict:
    token = os.environ["REPLICATE_API_TOKEN"]
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def generate_image(prompt: str, dest: Path, aspect_ratio: str = "16:9",
                   timeout_s: float = 120.0) -> Path:
    """Generate a single image from a prompt and save it to dest."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=timeout_s) as http:
        create = http.post(
            f"{API}/models/{FLUX_MODEL}/predictions",
            headers={**_headers(), "Prefer": "wait"},
            json={"input": {"prompt": prompt, "aspect_ratio": aspect_ratio,
                            "output_format": "png", "num_outputs": 1}},
        )
        create.raise_for_status()
        pred = create.json()
        # With Prefer: wait the prediction is usually already terminal; poll otherwise.
        deadline = time.time() + timeout_s
        while pred.get("status") not in ("succeeded", "failed", "canceled"):
            if time.time() > deadline:
                raise TimeoutError("replicate prediction timed out")
            time.sleep(2)
            pred = http.get(f"{API}/predictions/{pred['id']}", headers=_headers()).json()
        if pred["status"] != "succeeded":
            raise RuntimeError(f"flux failed: {pred.get('error')}")
        out = pred["output"]
        url = out[0] if isinstance(out, list) else out
        img = http.get(url)
        img.raise_for_status()
        dest.write_bytes(img.content)
    return dest


def generate_scene_images(scenes: list, out_dir: Path,
                          aspect_ratio: str = "16:9") -> list[Path]:
    """Generate one image per scene (scene.image_prompt). Returns ordered paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for sc in scenes:
        p = out_dir / f"scene_{sc.id:02d}.png"
        generate_image(sc.image_prompt, p, aspect_ratio=aspect_ratio)
        paths.append(p)
    return paths
