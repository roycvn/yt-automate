"""Automated script generation via Claude — niche-agnostic.

Driven by a CHANNEL PROFILE (config), so the same engine writes for any
channel: horror, moral stories, cooking, motivation, tech, history, etc. The
model also returns a per-video THUMBNAIL CONCEPT (subject + hook text) chosen
to fit *this* video — so thumbnails are contextual, not a fixed template.

Output is a structured object: title + SEO + ordered scenes (narration +
image prompt) + thumbnail concept.

Env: ANTHROPIC_API_KEY
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict

DEFAULT_MODEL = "claude-haiku-4-5-20251001"   # ~5-10s vs sonnet ~30s

# Channel profile keys (all optional; sensible fallbacks). Set in config.yaml.
DEFAULT_PROFILE = {
    "name": "My Channel",
    "language": "hi",
    "language_name": "Hindi (Devanagari)",
    "niche": "short engaging stories",
    "tone": "engaging, clear, emotionally resonant",
    "audience": "general audience",
    "format": "narrated story with a strong hook and a satisfying payoff",
    "art_style": "cinematic, high quality, consistent style across scenes",
    "scenes": 16,
}

SYSTEM_TEMPLATE = """You are a scriptwriter + creative director for the YouTube
channel "{name}".

CHANNEL PROFILE
- Niche: {niche}
- Tone: {tone}
- Target audience: {audience}
- Video format: {format}
- Narration language: {language_name}

TASK
Write ONE original, 100% new video for this channel ({scenes} scenes,
~3-5 min narrated). Never copy existing works, names, or plots. Open with a
strong hook, sustain interest, and land a satisfying ending appropriate to the
niche. Narration must be natural spoken {language_name}.

Also design a THUMBNAIL CONCEPT that best sells THIS specific video: pick the
single most click-worthy visual subject from the story and a 2-5 word hook.

Every image_prompt MUST begin with this exact art-style prefix so all scenes
look like one production: "{art_style}". Keep characters/objects visually
consistent by describing them the same way each time.

Return ONLY valid JSON, no prose:
{{
  "title": "<catchy title in {language_name}>",
  "title_translit": "<roman transliteration, or repeat title if already latin>",
  "description": "<2-3 line description with natural keywords>",
  "tags": ["...", "..."],            // 10-15 search tags for this niche
  "thumbnail": {{
     "subject": "<vivid English description of the thumbnail's main visual — a
                 person/object/scene with strong emotion, fit for this niche>",
     "hook": "<2-5 word on-image hook in {language_name}>",
     "mood": "<color/lighting mood, e.g. 'dark red/teal, dramatic' or
              'bright warm, appetizing'>"
  }},
  "scenes": [
    {{"id": 1, "narration": "<1-3 sentences>",
      "image_prompt": "<art-style prefix + this scene, detailed>"}}
  ]
}}"""

USER_TEMPLATE = "Create the next video. {theme}Make it genuinely original."


@dataclass
class Scene:
    id: int
    narration: str
    image_prompt: str


@dataclass
class ThumbnailConcept:
    subject: str
    hook: str
    mood: str = ""


@dataclass
class StoryScript:
    title: str
    title_translit: str
    description: str
    tags: list[str]
    thumbnail: ThumbnailConcept
    scenes: list[Scene] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def generate_script(channel: dict | None = None, theme: str | None = None,
                    model: str = DEFAULT_MODEL, api_key: str | None = None) -> StoryScript:
    from anthropic import Anthropic

    profile = {**DEFAULT_PROFILE, **(channel or {})}
    system = SYSTEM_TEMPLATE.format(**profile)
    user = USER_TEMPLATE.format(theme=(theme + " ") if theme else "")

    client = Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(model=model, max_tokens=8000, system=system,
                                 messages=[{"role": "user", "content": user}])
    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1].lstrip("json").strip()
    data = json.loads(text)

    th = data.get("thumbnail", {})
    return StoryScript(
        title=data["title"], title_translit=data.get("title_translit", data["title"]),
        description=data["description"], tags=data["tags"],
        thumbnail=ThumbnailConcept(subject=th.get("subject", ""),
                                   hook=th.get("hook", ""), mood=th.get("mood", "")),
        scenes=[Scene(**s) for s in data["scenes"]],
    )
