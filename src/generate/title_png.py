"""Render an intro/outro title as a transparent PNG with proper text shaping.

Why this exists: libass on Vercel (and on Railway via BtbN ffmpeg) ships with
HarfBuzz, BUT it falls back to its non-shaping path for any ASS event that
carries an animated \\t() transform — and for some font/script combos appears
to skip Indic GSUB substitution even on static events. The most visible
casualty was Telugu titles like "దర్పణం": the conjunct `ర్ప` came out as
`ర + virama dot + ప` instead of `ర` collapsing into a subscript under `ప`.

Pre-render the title with Pillow's RAQM layout engine (libraqm + HarfBuzz)
and overlay that PNG on the intro card via a plain ffmpeg overlay. RAQM
handles every Indic conjunct correctly out of the box.

Returns the PNG path. Caller (finishing.py) overlays it during _card().
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .captions import _font_for

ROOT = Path(__file__).resolve().parent.parent.parent
FONTS_DIR = ROOT / "assets" / "fonts"

# Map the Noto family name (from captions._font_for) to a bundled TTF file.
# Bold variant first; fall back to Regular when no Bold ships for that script.
_FONT_FILES: dict[str, list[str]] = {
    "Noto Sans Telugu": ["NotoSansTelugu-Bold.ttf", "NotoSansTelugu-Regular.ttf"],
    "Noto Sans Devanagari": ["NotoSansDevanagari-Regular.ttf"],
    "Noto Sans Tamil": ["NotoSansTamil-Regular.ttf"],
    "Noto Sans": ["NotoSans-Bold.ttf", "NotoSans-Regular.ttf"],
}


def _resolve_font(family: str, size: int) -> ImageFont.FreeTypeFont:
    """Load the bundled font and force the RAQM layout engine — without RAQM
    Pillow uses its built-in simple shaper which has the same shortcomings as
    libass. raqm: True is verified in the postinstall script."""
    candidates = _FONT_FILES.get(family) or _FONT_FILES["Noto Sans"]
    for name in candidates:
        p = FONTS_DIR / name
        if p.exists():
            return ImageFont.truetype(str(p), size, layout_engine=ImageFont.Layout.RAQM)
    raise FileNotFoundError(
        f"no bundled font for family={family}; checked {candidates} in {FONTS_DIR}"
    )


def render_title_png(
    text: str,
    out: Path,
    *,
    language: str = "hi",
    width: int = 1920,
    height: int = 1080,
    fontsize: int = 150,
    fill: tuple[int, int, int, int] = (255, 215, 0, 255),  # gold (RGB), matches ASS Title &H0000D7FF (BGR)
    stroke: tuple[int, int, int, int] = (10, 10, 10, 255),
    stroke_width: int = 6,
) -> Path:
    """Render `text` centered on a transparent canvas. Returns the PNG path.

    The default fill matches the ASS Title style colour (gold) so the inline
    burn and this overlay are interchangeable visually."""
    out.parent.mkdir(parents=True, exist_ok=True)
    family = _font_for(language)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Auto-shrink font size if the text is wider than 90% of the canvas — Indic
    # text can be much wider than Latin at the same point size.
    max_w = int(width * 0.9)
    size = fontsize
    while size > 32:
        font = _resolve_font(family, size)
        w = draw.textlength(text, font=font)
        if w <= max_w:
            break
        size = int(size * 0.92)

    # Vertical baseline: Pillow's textbbox returns (l, t, r, b) for the glyph
    # ink box, which is what we want for true visual centering.
    font = _resolve_font(family, size)
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (width - tw) // 2 - bbox[0]
    y = (height - th) // 2 - bbox[1]
    draw.text(
        (x, y),
        text,
        font=font,
        fill=fill,
        stroke_width=stroke_width,
        stroke_fill=stroke,
    )
    img.save(str(out))
    return out
