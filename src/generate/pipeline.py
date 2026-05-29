"""End-to-end automated generation of one original video.

script (Claude) -> images (Flux) -> narration (Sarvam) -> assemble (ffmpeg)
=> a finished MP4 + its title/description/tags. No manual work.

Env: ANTHROPIC_API_KEY, REPLICATE_API_TOKEN, SARVAM_API_KEY (+ ffmpeg on PATH).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .script import generate_script
from .images import generate_scene_images
from .voice import synthesize_scenes
from .assemble import assemble


@dataclass
class GeneratedVideo:
    video_path: Path
    title: str
    title_translit: str
    description: str
    tags: list[str]
    language: str
    script_path: Path


def produce_video(out_root: Path, theme: str | None = None,
                  language: str = "hi", speaker: str = "anushka",
                  width: int = 1920, height: int = 1080,
                  script_model: str = "claude-sonnet-4-6") -> GeneratedVideo:
    """Generate one complete original video. Returns its path + metadata."""
    work = out_root
    work.mkdir(parents=True, exist_ok=True)

    # 1. Script
    script = generate_script(theme=theme, model=script_model) if theme \
        else generate_script(model=script_model)
    script_path = work / "script.json"
    script_path.write_text(json.dumps(script.to_dict(), ensure_ascii=False, indent=2))

    # 2. Images  3. Voice
    images = generate_scene_images(script.scenes, work / "images",
                                   aspect_ratio="16:9" if width >= height else "9:16")
    audios = synthesize_scenes(script.scenes, work / "audio",
                               language=language, speaker=speaker)

    # 4. Assemble
    video = assemble(images, audios, work / "final.mp4", work / "work",
                     width=width, height=height)

    return GeneratedVideo(
        video_path=video, title=script.title_hi, title_translit=script.title_translit,
        description=script.description, tags=script.tags, language=language,
        script_path=script_path,
    )
