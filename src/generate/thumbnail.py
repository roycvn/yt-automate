"""Eye-catching thumbnail generation (reference style).

Flux renders a dramatic scene — a terrified human face on one side, a haunted
scene behind — with empty space for text. klipr's libass burns a huge title
plus a red "banner" subtitle (correct Devanagari/Telugu shaping). We extract a
1280x720 frame. Composition mimics high-CTR horror thumbnails.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .images import generate_image

W, H = 1280, 720

# Niche-agnostic: subject on the RIGHT, darker space on the LEFT for the title.
# `mood` (from the per-video thumbnail concept) drives color/lighting, so this
# works for horror, cooking, motivation, tech, etc.
THUMB_BG_PROMPT_T = (
    "YouTube thumbnail background, ultra dramatic cinematic, high contrast, a "
    "{subject} positioned on the RIGHT side as the focal point, {mood}, the "
    "LEFT third is a darker uncluttered area for a bold title, professional, "
    "sharp, no text, highly eye-catching, scroll-stopping"
)

# Two styles: a huge white title (top-left) + a red banner subtitle (bottom-left).
THUMB_ASS_T = """[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: BigTitle,Noto Sans Devanagari,150,{title_color},&H00000000,&H00000000,1,0,1,14,8,7,50,50,60,1
Style: Banner,Noto Sans Devanagari,56,&H00FFFFFF,&H00000000,{accent_color},1,0,4,0,0,1,50,50,70,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{events}
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
                   subject: str = "dramatic subject, strong emotion",
                   banner: str = "",
                   mood: str = "dramatic cinematic lighting, bold colors",
                   title_color: str = "&H00FFFFFF",
                   accent_color: str = "&H000000FF") -> Path:
    """Produce a 1280x720 thumbnail with a huge title + optional banner burned in.
    `klipr` is a KliprClient; `upload_and_sign(path, key)` -> klipr-fetchable URL."""
    import asyncio
    import time
    import httpx

    work.mkdir(parents=True, exist_ok=True)
    bg = generate_image(THUMB_BG_PROMPT_T.format(subject=subject, mood=mood),
                        work / "thumb_bg.png", aspect_ratio="16:9")
    clip = _still_clip(bg, work / "thumb_clip.mp4")
    events = ["Dialogue: 0,0:00:00.00,0:00:02.00,BigTitle,,0,0,0,," + title]
    if banner:
        events.append("Dialogue: 0,0:00:00.00,0:00:02.00,Banner,,0,0,0,," + banner)
    ass = THUMB_ASS_T.format(title_color=title_color, accent_color=accent_color,
                             events="\n".join(events))

    url = upload_and_sign(clip, f"thumb/{int(time.time())}.mp4")
    res = asyncio.run(klipr.caption_burn(url, ass, watermark=False))
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
