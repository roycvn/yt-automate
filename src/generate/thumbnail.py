"""Eye-catching thumbnail generation (reference style).

Flux renders a dramatic scene — a terrified human face on one side, a haunted
scene behind — with empty space for text. klipr's libass burns a huge title
plus a red "banner" subtitle (correct Devanagari/Telugu shaping). We extract a
1280x720 frame. Composition mimics high-CTR horror thumbnails.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .captions import _font_for
from .images import generate_image

W, H = 1280, 720

# Local TTFs (the same families klipr's libass has in its fontsdir) used only to
# *measure* text so we can wrap + auto-fit the title before sending the ASS to
# klipr. Names here must stay in sync with assets/fonts and _FONT_BY_LANG.
_FONTS_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
_FONT_FILE = {
    "hi": "NotoSansDevanagari-Regular.ttf",
    "te": "NotoSansTelugu-Bold.ttf",
    "ta": "NotoSansTamil-Regular.ttf",
    "en": "NotoSans-Bold.ttf",
}

# The title sits in a left-hand column; the Flux bg keeps the subject on the
# right. These bound where the title may wrap/grow.
TITLE_COL_W = 760          # px of usable width for the title block
TITLE_MARGIN_R = W - 50 - TITLE_COL_W   # right margin reserving the subject side
TITLE_SIZE_MAX = 150
TITLE_SIZE_MIN = 66
KICKER_SIZE = 54

# Niche-agnostic: subject on the RIGHT, darker space on the LEFT for the title.
# `mood` (from the per-video thumbnail concept) drives color/lighting, so this
# works for horror, cooking, motivation, tech, etc.
THUMB_BG_PROMPT_T = (
    "YouTube thumbnail background, ultra dramatic cinematic, high contrast, a "
    "{subject} positioned on the RIGHT side as the focal point, {mood}, the "
    "LEFT third is a darker uncluttered area for a bold title, professional, "
    "sharp, no text, highly eye-catching, scroll-stopping"
)

# Three stacked styles in the left column:
#   Kicker   — small accent-colored line at the very top (e.g. "डरावनी कहानी")
#   BigTitle — the wrapped, auto-sized headline (size injected per-render)
#   Banner   — bottom-left subtitle band (e.g. "BASED ON A TRUE STORY")
# Title MarginR reserves the right side for the subject so the headline wraps
# into the left column instead of running across the face.
THUMB_ASS_T = """[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Kicker,{kicker_font},{kicker_size},{accent_color},&H00000000,&H00000000,1,0,1,5,3,7,50,{title_margin_r},48,1
Style: BigTitle,{font},{title_size},{title_color},&H00000000,&H00000000,1,0,1,14,8,7,50,{title_margin_r},{title_margin_v},1
Style: Banner,{banner_font},56,&H00FFFFFF,&H00000000,{accent_color},1,0,4,0,0,1,50,50,70,1

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


def _script_of(text: str) -> str:
    """Pick a language code based on the dominant Unicode block of `text`. Used
    to choose a font that actually has the glyphs — libass with no fontconfig
    can't fall back per-glyph, so a font without a script's table renders tofu
    (the empty rectangles in the broken thumbnail). Latin/empty falls through
    to plain Noto Sans which covers ASCII."""
    if not text:
        return "en"
    if any("ఀ" <= c <= "౿" for c in text):
        return "te"
    if any("ऀ" <= c <= "ॿ" for c in text):
        return "hi"
    if any("஀" <= c <= "௿" for c in text):
        return "ta"
    if any("ಀ" <= c <= "೿" for c in text):
        return "kn"
    if any("ഀ" <= c <= "ൿ" for c in text):
        return "ml"
    if any("ঀ" <= c <= "৿" for c in text):
        return "bn"
    if any("઀" <= c <= "૿" for c in text):
        return "gu"
    return "en"


def _measure_font(lang: str, size: int):
    """Local PIL font for measurement only (not the libass render)."""
    from PIL import ImageFont
    fname = _FONT_FILE.get(lang, _FONT_FILE["en"])
    path = _FONTS_DIR / fname
    if not path.exists():
        path = _FONTS_DIR / _FONT_FILE["en"]
    return ImageFont.truetype(str(path), size)


def _text_w(text: str, fnt) -> int:
    b = fnt.getbbox(text)
    return b[2] - b[0]


def _wrap(text: str, fnt, max_w: int) -> list[str]:
    """Greedy word-wrap; honors explicit '\\N'/'|' hard breaks."""
    lines: list[str] = []
    for chunk in text.replace("\\N", "|").split("|"):
        line = ""
        for word in chunk.split():
            trial = (line + " " + word).strip()
            if _text_w(trial, fnt) <= max_w or not line:
                line = trial
            else:
                lines.append(line)
                line = word
        if line:
            lines.append(line)
    return lines or [text]


def layout_title(title: str, lang: str, *, col_w: int = TITLE_COL_W,
                 max_lines: int = 3, size_max: int = TITLE_SIZE_MAX,
                 size_min: int = TITLE_SIZE_MIN) -> tuple[str, int]:
    """Wrap `title` into the left column and pick the largest font size (within
    [size_min, size_max]) that fits within `col_w` and `max_lines`. Returns the
    ASS-ready text (lines joined with '\\N') and the chosen font size."""
    target = int(col_w * 0.96)        # safety margin vs libass metric drift
    block_h = H - 130 - 150           # vertical budget between top reserve & banner
    size = size_max
    while size > size_min:
        fnt = _measure_font(lang, size)
        lines = _wrap(title, fnt, target)
        asc, desc = fnt.getmetrics()
        lh = int((asc + desc) * 1.04)
        if (len(lines) <= max_lines
                and all(_text_w(l, fnt) <= target for l in lines)
                and len(lines) * lh <= block_h):
            break
        size -= 4
    fnt = _measure_font(lang, size)
    lines = _wrap(title, fnt, target)
    return "\\N".join(lines), size


def build_thumb_ass(title: str, *, banner: str = "", kicker: str = "",
                    title_color: str = "&H00FFFFFF",
                    accent_color: str = "&H000000FF",
                    language: str = "hi") -> str:
    """Build the burn-in ASS: an auto-sized/wrapped title, an optional small
    kicker above it, and an optional banner below. Split out from the render so
    it can be unit-tested (and previewed) without klipr/network."""
    title_lang = _script_of(title) if _script_of(title) != "en" else language
    wrapped, title_size = layout_title(title, title_lang)
    # a taller (wrapped) title needs to start higher so the block stays centred
    n_lines = wrapped.count("\\N") + 1
    title_margin_v = 130 if kicker else 90
    if n_lines >= 3:
        title_margin_v = max(60, title_margin_v - (n_lines - 2) * 30)

    events = []
    if kicker:
        events.append("Dialogue: 0,0:00:00.00,0:00:02.00,Kicker,,0,0,0,," + kicker)
    events.append("Dialogue: 0,0:00:00.00,0:00:02.00,BigTitle,,0,0,0,," + wrapped)
    if banner:
        events.append("Dialogue: 0,0:00:00.00,0:00:02.00,Banner,,0,0,0,," + banner)

    # libass with klipr's fontsdir-only setup can't fall back per-glyph between
    # fonts, so each style needs its own correct font. Pick fonts from each
    # text's actual script — the title may be in the channel language while
    # the banner is often English ("BASED ON A TRUE STORY") or vice versa.
    title_font = _font_for(title_lang)
    banner_font = _font_for(_script_of(banner)) if banner else "Noto Sans"
    kicker_font = _font_for(_script_of(kicker)) if kicker else "Noto Sans"
    return THUMB_ASS_T.format(
        font=title_font, banner_font=banner_font, kicker_font=kicker_font,
        title_color=title_color, accent_color=accent_color,
        title_size=title_size, kicker_size=KICKER_SIZE,
        title_margin_r=TITLE_MARGIN_R, title_margin_v=title_margin_v,
        events="\n".join(events))


def _ass_bgr_to_rgb(c: str) -> tuple[int, int, int]:
    """'&H00BBGGRR' (ASS, BGR) -> (R, G, B)."""
    h = c.replace("&H", "").replace("&", "")
    h = h[-6:].rjust(6, "0")
    bb, gg, rr = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return rr, gg, bb


def preview_thumbnail(title: str, out: Path, *, banner: str = "", kicker: str = "",
                      title_color: str = "&H00FFFFFF",
                      accent_color: str = "&H000000FF", language: str = "hi",
                      bg: Path | None = None) -> Path:
    """Offline PIL approximation of the libass layout (no klipr/Flux needed).
    Useful for eyeballing wrap/size/placement before a real render."""
    from PIL import Image, ImageDraw
    title_lang = _script_of(title) if _script_of(title) != "en" else language
    wrapped, size = layout_title(title, title_lang)
    lines = wrapped.split("\\N")
    n = len(lines)
    tmv = 130 if kicker else 90
    if n >= 3:
        tmv = max(60, tmv - (n - 2) * 30)

    img = (Image.open(bg).convert("RGB").resize((W, H)) if bg and Path(bg).exists()
           else Image.new("RGB", (W, H), (28, 24, 30)))
    d = ImageDraw.Draw(img)
    tc, ac = _ass_bgr_to_rgb(title_color), _ass_bgr_to_rgb(accent_color)

    if kicker:
        kf = _measure_font(_script_of(kicker), KICKER_SIZE)
        d.text((50, 48), kicker, font=kf, fill=ac, stroke_width=3,
               stroke_fill=(0, 0, 0))
    tf = _measure_font(title_lang, size)
    asc, desc = tf.getmetrics()
    lh = int((asc + desc) * 1.04)
    for i, ln in enumerate(lines):
        d.text((50, tmv + i * lh), ln, font=tf, fill=tc, stroke_width=8,
               stroke_fill=(0, 0, 0))
    if banner:
        bf = _measure_font(_script_of(banner), 56)
        bb = bf.getbbox(banner)
        bw, bh = bb[2] - bb[0], bb[3] - bb[1]
        d.rectangle([40, H - 70 - bh - 24, 60 + bw + 20, H - 46], fill=ac)
        d.text((50, H - 70 - bh - 12), banner, font=bf, fill=(255, 255, 255))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    return out


_LANG_NAME = {"hi": "Hindi", "te": "Telugu", "ta": "Tamil", "kn": "Kannada",
              "ml": "Malayalam", "bn": "Bengali", "gu": "Gujarati", "mr": "Marathi",
              "en": "English"}


def raqm_available() -> bool:
    """Local rich rendering needs raqm for Indic shaping. Linux/prod Pillow
    wheels often lack libraqm — fall back to the klipr/libass path if so."""
    try:
        from PIL import features
        return bool(features.check("raqm"))
    except Exception:
        return False


def make_thumbnail(title: str, work: Path, *, klipr=None, upload_and_sign=None,
                   subject: str = "dramatic subject, strong emotion",
                   banner: str = "",
                   kicker: str = "",
                   mood: str = "dramatic cinematic lighting, bold colors",
                   title_color: str = "&H00FFFFFF",
                   accent_color: str = "&H000000FF",
                   language: str = "hi",
                   hook: str = "",
                   niche: str = "",
                   template: str = "",
                   palette: str = "",
                   engine: str | None = None) -> Path:
    """Produce a 1280x720 thumbnail.

    Primary engine ('local'): Claude picks a design (template/palette/mood/text),
    Flux renders a background, and a Pillow template composites a modern design.
    Fallback engine ('libass'): the klipr ASS burn-in path (needs klipr +
    upload_and_sign) — used automatically when raqm/local rendering is
    unavailable. Force one with engine='local' | 'libass'."""
    use = engine or ("local" if raqm_available() else "libass")
    if use == "local":
        try:
            return _make_thumbnail_local(
                title, work, subject=subject, banner=banner, kicker=kicker,
                mood=mood, language=language, hook=hook, niche=niche,
                template=template, palette=palette)
        except Exception as e:
            if klipr is None or upload_and_sign is None:
                raise
            print(f"thumbnail: local render failed ({e}); falling back to libass")
    return _make_thumbnail_libass(
        title, work, klipr=klipr, upload_and_sign=upload_and_sign, subject=subject,
        banner=banner, kicker=kicker, mood=mood, title_color=title_color,
        accent_color=accent_color, language=language)


def _make_thumbnail_local(title: str, work: Path, *, subject, banner, kicker,
                          mood, language, hook, niche, template="", palette="") -> Path:
    from .thumbnail_design import choose_design, apply_palette
    from .thumbnail_render import render, TEMPLATES

    work.mkdir(parents=True, exist_ok=True)
    design = choose_design(
        title=title, hook=hook or title, subject=subject, mood=mood,
        niche=niche, language=language,
        language_name=_LANG_NAME.get(language, "Hindi"))
    # explicit overrides from the caller/UI/config win over Claude's choices
    if template in TEMPLATES:
        design.template = template
    if palette:
        apply_palette(design, palette)
    if kicker:
        design.kicker = kicker
    if banner:
        design.badge = banner

    bg = generate_image(THUMB_BG_PROMPT_T.format(subject=design.subject, mood=design.mood),
                        work / "thumb_bg.png", aspect_ratio="16:9")
    return render(design, bg, work / "thumbnail.png")


def _make_thumbnail_libass(title: str, work: Path, *, klipr, upload_and_sign,
                           subject, banner, kicker, mood, title_color,
                           accent_color, language) -> Path:
    import asyncio
    import time
    import httpx

    work.mkdir(parents=True, exist_ok=True)
    bg = generate_image(THUMB_BG_PROMPT_T.format(subject=subject, mood=mood),
                        work / "thumb_bg.png", aspect_ratio="16:9")
    clip = _still_clip(bg, work / "thumb_clip.mp4")
    ass = build_thumb_ass(title, banner=banner, kicker=kicker,
                          title_color=title_color, accent_color=accent_color,
                          language=language)

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
