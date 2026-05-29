"""Automated original story-script generation via Claude.

Produces a 100%-original Hindi horror story in the proven niche format
(chudail / dayan / bhoot, ordinary-object hook, twist ending) as a structured
object: title + SEO + an ordered list of scenes, each with narration text and
an image prompt. This is the creative core that drives image gen, TTS, and
assembly downstream.

Env: ANTHROPIC_API_KEY
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict

DEFAULT_MODEL = "claude-opus-4-7"

SYSTEM = """You are a writer for a Hindi animated horror-story YouTube channel
(genre: चुड़ैल / डायन / भूत — like "Scary Pumpkin" style, but ALL CONTENT MUST BE
100% ORIGINAL — never reuse existing stories, names, or plots). Your stories:
- run ~3-5 minutes narrated (≈ 14-18 short scenes),
- open with an everyday hook (an ordinary object/place/person) that turns supernatural,
- build dread, deliver a sharp twist, end with a chilling final line,
- are written in natural spoken Hindi (Devanagari), narrator voice.

Return ONLY valid JSON, no prose, in exactly this shape:
{
  "title_hi": "<catchy Hindi title>",
  "title_translit": "<roman transliteration>",
  "description": "<2-3 line Hindi+English description with keywords>",
  "tags": ["...", "..."],            // 10-15 search tags
  "scenes": [
    {"id": 1, "narration_hi": "<1-3 sentences of narration>",
     "image_prompt": "<detailed English image prompt: dark 2D animated horror cartoon style, the scene, mood, lighting>"}
  ]
}
Image prompts must all specify the SAME consistent art style so scenes look
like one film: "2D animated horror cartoon, muted desaturated palette,
volumetric moonlight, heavy shadows, cinematic". Keep characters visually
consistent across scenes (describe them the same way each time)."""

USER_TEMPLATE = """Write a NEW original Hindi animated horror story.
Theme hint: {theme}
Make it genuinely original (do not copy any known story). 14-18 scenes."""


@dataclass
class Scene:
    id: int
    narration_hi: str
    image_prompt: str


@dataclass
class StoryScript:
    title_hi: str
    title_translit: str
    description: str
    tags: list[str]
    scenes: list[Scene] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def generate_script(theme: str = "एक आम सी चीज़ जो धीरे-धीरे डरावनी हो जाती है",
                    model: str = DEFAULT_MODEL,
                    api_key: str | None = None) -> StoryScript:
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model=model,
        max_tokens=16000,
        system=SYSTEM,
        messages=[{"role": "user", "content": USER_TEMPLATE.format(theme=theme)}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()
    # Strip accidental code fences.
    if text.startswith("```"):
        text = text.split("```", 2)[1].lstrip("json").strip()
    data = json.loads(text)
    scenes = [Scene(**s) for s in data["scenes"]]
    return StoryScript(
        title_hi=data["title_hi"], title_translit=data["title_translit"],
        description=data["description"], tags=data["tags"], scenes=scenes,
    )
