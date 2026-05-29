"""Eye-catching thumbnail generation.

Flux renders a dramatic, high-contrast horror background (close-up scary
subject, space for text); klipr's libass burns a huge title (correct
Devanagari/Telugu shaping); we extract a single 1280x720 frame as the
thumbnail. Reuses the same proven caption pipeline so text never breaks.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .images import generate_image

W, H = 1280, 720

THUMB_BG_PROMPT_T = (
    "YouTube horror thumbnail, ultra dramatic, high contrast, vivid colors, "
    "a terrifying {subject} close-up with glowing eyes, blood-red and teal "
    "lighting, fog, intense shadows, cinematic 2D animated horror style, "
    "lots of empty space at the top for big text, no text, eye-catching"
)

# A short ASS that places one huge glowing line in the upper third.
THUMB_ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Thumb,Noto Sans Devanagari,110,&H0000F0FF,&H00000020,&H00000000,1,0,1,8,4,8,40,40,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:02.00,Thumb,,0,0,0,,{title}
"""


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def _still_clip(image: Path, out: Path, dur: float = 2.0) -> Path:
    _run([
        "ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(image),
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-vf", f"scale={W}:{H},format=yuv420p", "-t", f"{dur}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-c:a", "aac", str(out),
    ])
    return out


def make_thumbnail(title: str, work: Path, *, klipr, upload_and_sign,
                   subject: str = "chudail witch") -> Path:
    """Produce a 1280x720 thumbnail PNG with the title burned in. `klipr` is a
    KliprClient; `upload_and_sign(path, key)` returns a klipr-fetchable URL."""
    import asyncio
    import time
    import httpx

    work.mkdir(parents=True, exist_ok=True)
    bg = generate_image(THUMB_BG_PROMPT_T.format(subject=subject),
                        work / "thumb_bg.png", aspect_ratio="16:9")
    clip = _still_clip(bg, work / "thumb_clip.mp4")
    ass = THUMB_ASS.format(title=title)

    url = upload_and_sign(clip, f"thumb/{int(time.time())}.mp4")
    res = asyncio.run(klipr.caption_burn(url, ass))
    burned = work / "thumb_burned.mp4"
    with httpx.stream("GET", res.download_url, timeout=300) as r:
        r.raise_for_status()
        with open(burned, "wb") as f:
            for c in r.iter_bytes():
                f.write(c)

    out = work / "thumbnail.png"
    _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1", "-i", str(burned),
          "-frames:v", "1", "-vf", f"scale={W}:{H}", str(out)])
    return out
