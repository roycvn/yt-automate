"""Auto-pick a thumbnail design from the script.

Claude reads the story (title/hook/subject/mood) and returns a structured design
choice — template + palette + mood + on-image text. A deterministic fallback
keeps the pipeline working with no API key or on any parse failure.
"""
from __future__ import annotations

import json
import os

from .thumbnail_render import ThumbDesign, TEMPLATES

# Named palettes (RGB). accent drives kicker/badge; glow/grad optional.
PALETTES = {
    "crimson":    dict(title_color=(255, 255, 255), accent=(214, 28, 36), stroke=(0, 0, 0), glow=(150, 0, 0)),
    "blood":      dict(title_color=(255, 60, 45), accent=(180, 0, 0), stroke=(0, 0, 0), glow=(150, 0, 0)),
    "teal_cinema":dict(title_color=(255, 255, 255), accent=(0, 190, 190), stroke=(0, 20, 24), glow=(0, 120, 130), bg_tint=(8, 18, 26)),
    "midnight":   dict(title_color=(245, 246, 255), accent=(96, 130, 255), stroke=(6, 8, 24), glow=(40, 60, 180), bg_tint=(8, 10, 28)),
    "gold_luxe":  dict(title_color=(245, 240, 232), accent=(208, 170, 92), stroke=(20, 16, 8), bg_tint=(16, 14, 10)),
    "neon_magenta":dict(title_color=(255, 255, 255), accent=(255, 0, 170), stroke=(20, 0, 35), glow=(140, 0, 160), grad=((0, 255, 255), (255, 0, 200)), bg_tint=(8, 0, 40)),
    "sunset":     dict(title_color=(255, 250, 235), accent=(255, 120, 30), stroke=(40, 12, 0), glow=(200, 70, 0), grad=((255, 210, 60), (255, 70, 40))),
    "emerald":    dict(title_color=(245, 255, 248), accent=(0, 200, 120), stroke=(0, 24, 14), glow=(0, 120, 70), bg_tint=(6, 22, 16)),
    "royal":      dict(title_color=(248, 244, 255), accent=(168, 96, 255), stroke=(18, 8, 30), glow=(110, 40, 200), bg_tint=(16, 8, 28)),
    "mono":       dict(title_color=(255, 255, 255), accent=(245, 210, 0), stroke=(0, 0, 0)),
    "ice":        dict(title_color=(240, 250, 255), accent=(90, 200, 255), stroke=(4, 18, 30), glow=(40, 130, 200), bg_tint=(10, 20, 32)),
    "noir":       dict(title_color=(255, 255, 255), accent=(235, 235, 235), stroke=(0, 0, 0), bg_tint=(6, 6, 8)),
    "candy":      dict(title_color=(255, 255, 255), accent=(255, 70, 150), stroke=(30, 0, 25), glow=(255, 60, 140), grad=((255, 90, 170), (90, 200, 255)), bg_tint=(20, 6, 24)),
    "ember":      dict(title_color=(255, 245, 230), accent=(255, 90, 20), stroke=(30, 8, 0), glow=(200, 60, 0), bg_tint=(22, 10, 6)),
    "ocean":      dict(title_color=(240, 252, 255), accent=(0, 170, 200), stroke=(0, 18, 26), glow=(0, 90, 130), bg_tint=(6, 18, 28)),
    "grape":      dict(title_color=(248, 244, 255), accent=(150, 80, 235), stroke=(16, 6, 28), glow=(90, 30, 180), bg_tint=(14, 8, 26)),
    "rose_gold":  dict(title_color=(255, 248, 244), accent=(224, 150, 140), stroke=(28, 14, 12), bg_tint=(22, 14, 14)),
    "steel":      dict(title_color=(238, 242, 248), accent=(120, 150, 180), stroke=(10, 14, 20), bg_tint=(14, 18, 24)),
    "lime":       dict(title_color=(250, 255, 240), accent=(170, 230, 30), stroke=(14, 22, 0), glow=(90, 150, 0), bg_tint=(14, 20, 6)),
    "blush":      dict(title_color=(255, 250, 250), accent=(255, 110, 130), stroke=(34, 10, 14), glow=(200, 50, 80), bg_tint=(24, 12, 14)),
    "cyber":      dict(title_color=(230, 255, 250), accent=(0, 255, 170), stroke=(0, 20, 18), glow=(0, 160, 120), grad=((0, 255, 200), (60, 130, 255)), bg_tint=(4, 16, 18)),
    "amber":      dict(title_color=(255, 250, 235), accent=(255, 185, 30), stroke=(34, 22, 0), glow=(180, 120, 0), bg_tint=(22, 16, 4)),
    "crimson_gold":dict(title_color=(255, 250, 240), accent=(214, 28, 36), stroke=(26, 4, 4), glow=(150, 0, 0), grad=((255, 210, 90), (214, 28, 36))),
    "slate":      dict(title_color=(240, 244, 250), accent=(90, 110, 140), stroke=(8, 10, 16), bg_tint=(12, 14, 20)),
}

# mood keyword -> Flux lighting phrase (drives the generated background).
MOOD_LIGHTING = {
    "horror": "dark teal and blood-red lighting, fog, dramatic shadows, eerie",
    "luxury": "soft golden rim light, elegant bokeh, premium, cinematic",
    "tech": "cool blue and cyan glow, sleek, futuristic, high-key",
    "emotional": "warm soft light, shallow depth of field, intimate",
    "energetic": "vivid saturated colors, punchy contrast, dynamic",
    "mystery": "moody low-key lighting, single light source, deep shadows",
}

_TEMPLATE_KEYS = list(TEMPLATES)
_PALETTE_KEYS = list(PALETTES)

# fields a palette may set on a ThumbDesign
_PALETTE_FIELDS = ("title_color", "accent", "stroke", "glow", "grad", "bg_tint")


def apply_palette(design, name: str) -> None:
    """Overlay a named palette's colors onto an existing ThumbDesign in place."""
    pal = PALETTES.get(name)
    if not pal:
        return
    for f in _PALETTE_FIELDS:
        setattr(design, f, pal.get(f, getattr(design, f)))

_SYSTEM = (
    "You are an art director for high-CTR YouTube thumbnails across every niche "
    "and region. Given a video's story, choose a thumbnail design. Reply with "
    "ONLY a JSON object, no prose."
)
_USER = """Story:
- title: {title}
- hook: {hook}
- subject: {subject}
- mood: {mood}
- niche: {niche}
- language: {language_name} (on-image text MUST be in this language; keep ASCII labels in English)

Pick the most scroll-stopping design. Return JSON:
{{
  "template": one of {templates},
  "palette":  one of {palettes},
  "mood_key": one of {moods},
  "title":   "<=5 punchy words for the big on-image headline, in {language_name}",
  "kicker":  "<short top label or '' (e.g. category/series, in {language_name})>",
  "badge":   "<short corner tag or '' (e.g. 'PART 1','NEW','EXCLUSIVE')>",
  "emoji":   "<one emoji that fits, or ''>",
  "emphasis":"<the single most important word from your title to color-highlight, or '' — must appear verbatim in title>",
  "subject": "<vivid English description of the background subject for image-gen>"
}}"""


def _coerce(data: dict, *, title: str, subject: str, mood: str, language: str) -> ThumbDesign:
    template = data.get("template") if data.get("template") in TEMPLATES else "cinematic"
    pal = PALETTES.get(data.get("palette"), PALETTES["crimson"])
    mood_key = data.get("mood_key")
    lighting = MOOD_LIGHTING.get(mood_key, mood or "dramatic cinematic lighting")
    return ThumbDesign(
        title=(data.get("title") or title).strip(),
        template=template,
        kicker=(data.get("kicker") or "").strip(),
        badge=(data.get("badge") or "").strip(),
        emoji=(data.get("emoji") or "").strip(),
        emphasis=(data.get("emphasis") or "").strip(),
        mood=lighting,
        subject=(data.get("subject") or subject).strip(),
        lang=language,
        **pal,
    )


def _fallback(*, title, subject, mood, niche, language) -> ThumbDesign:
    """Deterministic design when Claude is unavailable — keyed off niche/mood."""
    n = (niche + " " + mood).lower()
    if any(k in n for k in ("horror", "scary", "ghost", "haunt", "thriller")):
        tpl, pal, mk = "cinematic", "blood", "horror"
    elif any(k in n for k in ("luxury", "wealth", "rich", "premium", "elegant")):
        tpl, pal, mk = "luxe", "gold_luxe", "luxury"
    elif any(k in n for k in ("tech", "ai", "gadget", "science")):
        tpl, pal, mk = "minimal", "midnight", "tech"
    elif any(k in n for k in ("music", "party", "dance", "festival", "sport")):
        tpl, pal, mk = "neon", "neon_magenta", "energetic"
    elif any(k in n for k in ("emotion", "story", "love", "family", "moral")):
        tpl, pal, mk = "spotlight", "sunset", "emotional"
    else:
        tpl, pal, mk = "cinematic", "crimson", "mystery"
    return ThumbDesign(
        title=title, template=tpl, mood=MOOD_LIGHTING.get(mk, mood or "dramatic"),
        subject=subject, lang=language, **PALETTES[pal])


def choose_design(*, title: str, hook: str, subject: str, mood: str,
                  niche: str = "", language: str = "hi",
                  language_name: str = "Hindi", model: str | None = None,
                  api_key: str | None = None) -> ThumbDesign:
    """Claude picks template+palette+mood+text; falls back deterministically."""
    on_image = (hook or title).strip()
    key = api_key or os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return _fallback(title=on_image, subject=subject, mood=mood,
                         niche=niche, language=language)
    try:
        from anthropic import Anthropic
        from .script import DEFAULT_MODEL
        client = Anthropic(api_key=key)
        user = _USER.format(title=title, hook=hook, subject=subject, mood=mood,
                            niche=niche or "general", language_name=language_name,
                            templates=_TEMPLATE_KEYS, palettes=_PALETTE_KEYS,
                            moods=list(MOOD_LIGHTING))
        msg = client.messages.create(model=model or DEFAULT_MODEL, max_tokens=600,
                                     system=_SYSTEM,
                                     messages=[{"role": "user", "content": user}])
        text = "".join(b.text for b in msg.content
                       if getattr(b, "type", None) == "text").strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1].lstrip("json").strip()
        return _coerce(json.loads(text), title=on_image, subject=subject,
                       mood=mood, language=language)
    except Exception:
        return _fallback(title=on_image, subject=subject, mood=mood,
                         niche=niche, language=language)
