"""Per-scene narration via Sarvam TTS (native Hindi / Telugu / other Indian langs).

Mirrors klipr's Sarvam adapter: bulbul:v2, ~500-char chunking, WAV stitching.
Returns one WAV per scene so assembly can sync each image to its narration.

Env: SARVAM_API_KEY
"""
from __future__ import annotations

import os
import re
import wave
from pathlib import Path

import httpx

BASE = "https://api.sarvam.ai"
MODEL = "bulbul:v2"

LANG_CODE = {"hi": "hi-IN", "te": "te-IN", "ta": "ta-IN", "bn": "bn-IN",
             "kn": "kn-IN", "ml": "ml-IN", "mr": "mr-IN", "gu": "gu-IN"}


def _chunk(text: str, max_len: int = 450) -> list[str]:
    t = text.strip()
    if len(t) <= max_len:
        return [t]
    parts = re.split(r"([।॥.!?]+\s*)", t)
    out, buf = [], ""
    for p in parts:
        if not p:
            continue
        if len(buf + p) > max_len and buf:
            out.append(buf.strip())
            buf = p
        else:
            buf += p
    if buf.strip():
        out.append(buf.strip())
    return out


def synthesize(text: str, dest: Path, language: str = "hi",
               speaker: str = "anushka", timeout_s: float = 90.0) -> Path:
    """Synthesize narration text to a single WAV at dest."""
    import base64

    api_key = os.environ["SARVAM_API_KEY"]
    lang = LANG_CODE.get(language, "hi-IN")
    pcm_parts: list[bytes] = []
    params = (1, 2, 22050)  # channels, sampwidth(bytes), framerate (bulbul:v2 = 22.05k mono 16-bit)

    with httpx.Client(timeout=timeout_s) as http:
        for chunk in _chunk(text):
            r = http.post(f"{BASE}/text-to-speech",
                          headers={"api-subscription-key": api_key,
                                   "content-type": "application/json"},
                          json={"text": chunk, "target_language_code": lang,
                                "speaker": speaker, "model": MODEL})
            r.raise_for_status()
            b64 = r.json().get("audios", [None])[0]
            if not b64:
                raise RuntimeError("Sarvam returned no audio")
            raw = base64.b64decode(b64)
            pcm_parts.append(raw[44:])  # strip RIFF header, keep PCM

    dest.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(dest), "wb") as w:
        w.setnchannels(params[0])
        w.setsampwidth(params[1])
        w.setframerate(params[2])
        w.writeframes(b"".join(pcm_parts))
    return dest


def synthesize_scenes(scenes: list, out_dir: Path, language: str = "hi",
                      speaker: str = "anushka") -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for sc in scenes:
        p = out_dir / f"scene_{sc.id:02d}.wav"
        synthesize(sc.narration_hi, p, language=language, speaker=speaker)
        paths.append(p)
    return paths
