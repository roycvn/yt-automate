"""Build an ASS subtitle track for the finished video.

All on-screen text (intro title, scene narration captions, outro CTA) is
emitted as ASS events and burned by klipr's libass pass — libass shapes
Devanagari/Telugu correctly (ffmpeg drawtext does not). Timings are derived
from each scene's narration audio duration.
"""
from __future__ import annotations

import re
import wave
from pathlib import Path

# Per-language Noto font picker. Using the wrong script's Noto (e.g. Devanagari
# for Telugu) makes libass fall back to a font that doesn't shape that script's
# conjuncts — letters render as disconnected base+vowel-sign pairs instead of
# proper akshara. Match the script to the language.
_FONT_BY_LANG = {
    "hi": "Noto Sans Devanagari",
    "mr": "Noto Sans Devanagari",
    "ne": "Noto Sans Devanagari",
    "sa": "Noto Sans Devanagari",
    "te": "Noto Sans Telugu",
    "ta": "Noto Sans Tamil",
    "kn": "Noto Sans Kannada",
    "ml": "Noto Sans Malayalam",
    "bn": "Noto Sans Bengali",
    "gu": "Noto Sans Gujarati",
    "pa": "Noto Sans Gurmukhi",
    "or": "Noto Sans Oriya",
    "en": "Noto Sans",
}


def _font_for(lang: str) -> str:
    return _FONT_BY_LANG.get((lang or "hi").lower(), "Noto Sans")


def _ass_header(font: str) -> str:
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1920\n"
        "PlayResY: 1080\n"
        "WrapStyle: 0\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, "
        "Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Caption,{font},64,&H00FFFFFF,&H00000000,&H64000000,1,0,1,3,2,2,80,80,90,1\n"
        f"Style: Title,{font},120,&H0000D7FF,&H00101010,&H96000000,1,0,1,6,5,5,80,80,80,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def _ts(t: float) -> str:
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[।॥.!?])\s+", text.strip())
    return [p for p in parts if p.strip()]


def _event(start: float, end: float, style: str, text: str) -> str:
    text = text.replace("\n", " ").strip()
    return f"Dialogue: 0,{_ts(start)},{_ts(end)},{style},,0,0,0,,{text}"


def build_ass(scenes: list, audio_paths: list[Path], *,
              intro_s: float, outro_s: float,
              intro_title: str, outro_text: str,
              language: str = "hi") -> str:
    """Compose the full ASS. Body scenes are offset by intro_s; outro at the end."""
    events: list[str] = []
    # Intro title card — only when we generated a title card (intro_title set
    # and there's intro time). For uploaded/no intro, skip the title event.
    if intro_title and intro_s > 0.5:
        intro_fx = r"{\fad(600,500)\t(0,2400,\fscx118\fscy118)}"
        events.append(_event(0.2, max(intro_s - 0.2, 0.6), "Title", intro_fx + intro_title))

    # Scene captions, split per sentence proportionally across each scene's audio.
    t = intro_s
    for sc, ap in zip(scenes, audio_paths):
        dur = max(wav_duration(ap), 1.0)
        if not sc.narration.strip():
            t += dur  # advance the timeline but emit no caption (muted scene)
            continue
        sentences = _split_sentences(sc.narration) or [sc.narration]
        total_chars = sum(len(s) for s in sentences) or 1
        ct = t
        for sent in sentences:
            seg = dur * (len(sent) / total_chars)
            events.append(_event(ct, ct + seg, "Caption", sent))
            ct += seg
        t += dur

    # Outro CTA.
    events.append(_event(t + 0.2, t + outro_s, "Title", r"{\fad(500,400)}" + outro_text))
    return _ass_header(_font_for(language)) + "\n".join(events) + "\n"
