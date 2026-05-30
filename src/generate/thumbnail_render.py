"""Local Pillow thumbnail renderer — modern, multi-template design engine.

Renders fully in Python (raqm-shaped Indic text), giving gradients, glows,
shapes, badges, cross-fonts and auto-fit wrapping that libass cannot do. A
`ThumbDesign` (chosen by Claude, see thumbnail_design.py) selects a template +
palette + mood; `render()` composites it over a Flux background.

Backgrounds keep the subject on the RIGHT, so templates lay text in the LEFT
column. All templates share one set of tested effects below.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageOps

from .thumbnail import _script_of  # reuse the Unicode-block script detector

W, H = 1280, 720
_FONTS_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"

# (script, weight) -> file. Weights: regular/bold (body), display (heavy poster
# face), condensed (tall narrow), serif (posh). Latin gets real display faces
# (Anton/Bebas); Devanagari gets a variable serif; Indic sans ship Regular/Bold.
_FONT_FILES = {
    ("en", "bold"): "NotoSans-Bold.ttf", ("en", "regular"): "NotoSans-Regular.ttf",
    ("en", "display"): "Anton-Regular.ttf", ("en", "condensed"): "BebasNeue-Regular.ttf",
    ("hi", "bold"): "NotoSansDevanagari-Regular.ttf",
    ("hi", "regular"): "NotoSansDevanagari-Regular.ttf",
    ("hi", "serif"): "NotoSerifDevanagari.ttf",
    ("hi", "display"): "NotoSerifDevanagari.ttf",
    ("te", "bold"): "NotoSansTelugu-Bold.ttf",
    ("te", "regular"): "NotoSansTelugu-Regular.ttf",
    ("te", "display"): "NotoSansTelugu-Bold.ttf",
    ("ta", "bold"): "NotoSansTamil-Regular.ttf",
    ("ta", "regular"): "NotoSansTamil-Regular.ttf",
}
_VARIABLE_BOLD = {"NotoSerifDevanagari.ttf"}  # set a heavy instance for display
_RAQM = None  # lazy: Layout.RAQM if available else BASIC

# localized BEFORE/AFTER labels for the before_after template
_BEFORE_AFTER = {
    "hi": ("पहले", "बाद में"), "mr": ("आधी", "नंतर"),
    "te": ("ముందు", "తరువాత"), "ta": ("முன்", "பின்"),
    "kn": ("ಮೊದಲು", "ನಂತರ"), "ml": ("മുമ്പ്", "ശേഷം"),
    "bn": ("আগে", "পরে"), "gu": ("પહેલાં", "પછી"),
    "en": ("BEFORE", "AFTER"),
}


def _layout():
    global _RAQM
    if _RAQM is None:
        try:
            from PIL import features
            _RAQM = (ImageFont.Layout.RAQM if features.check("raqm")
                     else ImageFont.Layout.BASIC)
        except Exception:
            _RAQM = ImageFont.Layout.BASIC
    return _RAQM


def font(text: str, size: int, weight: str = "bold", lang: str | None = None):
    # Shaping MUST match the text's actual script, so resolve by script first.
    sc = _script_of(text)
    if sc == "en" and lang and (lang, "bold") in _FONT_FILES:
        sc = lang  # ASCII-only text on an Indic channel: keep its family
    # find the requested weight within the script; degrade weight, not script,
    # so an Indic title never falls back to a Latin-only display face (tofu).
    key = None
    for w in (weight, "bold", "regular", "display"):
        if (sc, w) in _FONT_FILES:
            key = (sc, w)
            break
    if key is None:
        for w in (weight, "display", "bold", "regular"):
            if ("en", w) in _FONT_FILES:
                key = ("en", w)
                break
    fname = _FONT_FILES[key]
    path = _FONTS_DIR / fname
    if not path.exists():
        path = _FONTS_DIR / _FONT_FILES[("en", "bold")]
        fname = _FONT_FILES[("en", "bold")]
    f = ImageFont.truetype(str(path), size, layout_engine=_layout())
    if fname in _VARIABLE_BOLD:
        for inst in (b"Bold", b"Black", b"SemiBold"):
            try:
                f.set_variation_by_name(inst)
                break
            except Exception:
                continue
    return f


# ----------------------------------------------------------------- image effects

def cover(img, w=W, h=H):
    sr, dr = img.width / img.height, w / h
    nw, nh = (int(h * sr), h) if sr > dr else (w, int(w / sr))
    img = img.resize((nw, nh), Image.LANCZOS)
    l, t = (nw - w) // 2, (nh - h) // 2
    return img.crop((l, t, l + w, t + h))


def grade(img, color=1.25, contrast=1.12, bright=1.0):
    img = ImageEnhance.Color(img).enhance(color)
    img = ImageEnhance.Contrast(img).enhance(contrast)
    return ImageEnhance.Brightness(img).enhance(bright)


def tint(img, rgb, amt=0.18):
    return Image.blend(img.convert("RGB"), Image.new("RGB", img.size, rgb), amt)


def vignette(img, strength=0.8):
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).ellipse([-W * .25, -H * .25, W * 1.25, H * 1.25], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(170))
    dark = ImageEnhance.Brightness(img).enhance(1 - strength * 0.6)
    return Image.composite(img, dark, mask)


def left_scrim(img, frac=0.62, alpha=210):
    """Darken the left column so text reads, fading out toward the subject."""
    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    px = grad.load()
    edge = int(W * frac)
    for x in range(edge):
        a = int(alpha * (1 - x / edge) ** 1.3)
        for y in range(H):
            px[x, y] = (0, 0, 0, a)
    return Image.alpha_composite(img.convert("RGBA"), grad)


def bottom_gradient(img, rgb=(0, 0, 0), alpha=235, start=0.32):
    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    px = grad.load()
    for y in range(H):
        f = max(0.0, (y / H - start) / (1 - start))
        a = int(alpha * f)
        for x in range(W):
            px[x, y] = (rgb[0], rgb[1], rgb[2], a)
    return Image.alpha_composite(img.convert("RGBA"), grad)


def gradient_layer(size, c_top, c_bot):
    w, h = size
    g = Image.new("RGBA", (1, h), 0)
    gp = g.load()
    for y in range(h):
        f = y / max(1, h - 1)
        gp[0, y] = tuple(int(c_top[i] + (c_bot[i] - c_top[i]) * f) for i in range(3)) + (255,)
    return g.resize((w, h))


def emoji_img(ch, px):
    """Color emoji at ~px tall, or None if no emoji font present (Linux/prod)."""
    candidates = [
        "/System/Library/Fonts/Apple Color Emoji.ttc",
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
        str(_FONTS_DIR / "NotoColorEmoji.ttf"),
    ]
    for fp in candidates:
        if not os.path.exists(fp):
            continue
        for strike in (160, 137, 109, 96):
            try:
                ef = ImageFont.truetype(fp, strike)
                c = Image.new("RGBA", (strike + 40, strike + 40), (0, 0, 0, 0))
                ImageDraw.Draw(c).text((0, 0), ch, font=ef, embedded_color=True)
                bb = c.getbbox()
                if not bb:
                    break
                c = c.crop(bb)
                r = px / c.height
                return c.resize((max(1, int(c.width * r)), px), Image.LANCZOS)
            except Exception:
                continue
    return None


# ----------------------------------------------------------------- text drawing

_D = ImageDraw.Draw(Image.new("RGB", (1, 1)))


def _w(s, fnt):
    b = fnt.getbbox(s)
    return b[2] - b[0]


def wrap(text, fnt, max_w):
    out = []
    for chunk in text.replace("\\N", "|").split("|"):
        line = ""
        for word in chunk.split():
            t = (line + " " + word).strip()
            if _w(t, fnt) <= max_w or not line:
                line = t
            else:
                out.append(line)
                line = word
        if line:
            out.append(line)
    return out or [text]


def _norm(w):
    return "".join(c for c in w.lower() if c.isalnum() or 'ऀ' <= c <= 'ൿ')


def headline(base, text, *, lang=None, weight="bold", x=60, max_w=760,
             max_lines=3, bottom_y=None, top_y=None, max_h=460,
             size_max=150, size_min=52, fill=(255, 255, 255), grad=None,
             stroke="auto", stroke_fill=(0, 0, 0), glow=None, glow_r=22,
             line_gap=0.06, align="left", emphasis="", emphasis_color=None):
    """Auto-sized, word-wrapped headline. Returns (image, (top_y, block_h)).
    `emphasis` words (space-separated) are drawn in `emphasis_color` — words
    are safe split points for Indic shaping (conjuncts never cross spaces)."""
    emph = {_norm(w) for w in emphasis.split()} if emphasis else set()
    target = int(max_w * 0.98)
    size = size_max
    while size > size_min:
        f = font(text, size, weight, lang)
        lines = wrap(text, f, target)
        asc, desc = f.getmetrics()
        lh = int((asc + desc) * (1 + line_gap))
        if (len(lines) <= max_lines and all(_w(l, f) <= target for l in lines)
                and lh * len(lines) <= max_h):
            break
        size -= 5
    f = font(text, size, weight, lang)
    lines = wrap(text, f, target)
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * (1 + line_gap))
    block_h = lh * len(lines)
    y0 = top_y if top_y is not None else (bottom_y - block_h if bottom_y else 80)
    sw = max(5, size // 13) if stroke == "auto" else (stroke or 0)

    def lx(line):
        if align == "center":
            return (W - _w(line, f)) // 2
        if align == "right":
            return W - x - _w(line, f)
        return x

    base = base.convert("RGBA")
    if glow:
        gl = Image.new("RGBA", base.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(gl)
        for i, ln in enumerate(lines):
            gd.text((lx(ln), y0 + i * lh), ln, font=f, fill=glow + (255,))
        base = Image.alpha_composite(base, gl.filter(ImageFilter.GaussianBlur(glow_r)))
    d = ImageDraw.Draw(base)
    for i, ln in enumerate(lines):
        xx, yy = lx(ln), y0 + i * lh
        if grad:
            if sw:
                d.text((xx, yy), ln, font=f, fill=None, stroke_width=sw, stroke_fill=stroke_fill)
            b = f.getbbox(ln)
            gw, gh = b[2] - b[0] + 4, b[3] - b[1] + 4
            mask = Image.new("L", (gw, gh), 0)
            ImageDraw.Draw(mask).text((-b[0] + 2, -b[1] + 2), ln, font=f, fill=255)
            base.paste(gradient_layer((gw, gh), grad[0], grad[1]), (xx + b[0] - 2, yy + b[1] - 2), mask)
            d = ImageDraw.Draw(base)
        elif emph and emphasis_color and any(_norm(w) in emph for w in ln.split()):
            # draw word-by-word so the emphasized word(s) take the accent color
            cx = xx
            words = ln.split(" ")
            space_w = _w(" ", f)
            for j, word in enumerate(words):
                col = emphasis_color if _norm(word) in emph else fill
                d.text((cx, yy), word, font=f, fill=col, stroke_width=sw, stroke_fill=stroke_fill)
                cx += _w(word, f) + space_w
        else:
            d.text((xx, yy), ln, font=f, fill=fill, stroke_width=sw, stroke_fill=stroke_fill)
    return base, (y0, block_h)


def tracked(base, text, xy, fnt, fill, *, spacing=6, stroke=0, stroke_fill=(0, 0, 0)):
    """Letter-spaced text for posh/modern kickers. Latin only — drawing glyph by
    glyph would break Indic shaping (conjuncts/matras), so complex scripts are
    drawn as a single shaped run."""
    d = ImageDraw.Draw(base)
    x, y = xy
    if _script_of(text) != "en":
        d.text((x, y), text, font=fnt, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
        return x + _w(text, fnt)
    for ch in text:
        d.text((x, y), ch, font=fnt, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
        x += _w(ch, fnt) + (spacing if ch != " " else spacing + fnt.size // 4)
    return x


def badge(base, text, xy, *, lang=None, size=58, fg=(255, 255, 255),
          bg=(200, 0, 0), pad=20, radius=12, weight="bold", stroke=0,
          stroke_fill=(0, 0, 0)):
    f = font(text, size, weight, lang)
    b = f.getbbox(text)
    tw, th = b[2] - b[0], b[3] - b[1]
    x, y = xy
    d = ImageDraw.Draw(base)
    if bg is not None:
        d.rounded_rectangle([x, y, x + tw + pad * 2, y + th + pad * 2], radius=radius, fill=bg)
    d.text((x + pad - b[0], y + pad - b[1]), text, font=f, fill=fg,
           stroke_width=stroke, stroke_fill=stroke_fill)
    return (x, y, x + tw + pad * 2, y + th + pad * 2)


def hairline(base, x, y, w, color, thick=4):
    ImageDraw.Draw(base).rectangle([x, y, x + w, y + thick], fill=color)


# ----------------------------------------------------------------- design schema

@dataclass
class ThumbDesign:
    title: str
    template: str = "cinematic"
    kicker: str = ""
    badge: str = ""
    emoji: str = ""
    emphasis: str = ""                     # word(s) in the title to color with accent
    # palette (RGB); accent drives kicker/badge/banner, glow optional
    title_color: tuple = (255, 255, 255)
    accent: tuple = (220, 30, 40)
    stroke: tuple = (0, 0, 0)
    glow: tuple | None = None
    grad: tuple | None = None              # (top_rgb, bot_rgb) for gradient title
    bg_tint: tuple | None = None
    mood: str = "dramatic cinematic lighting"
    subject: str = "dramatic subject, strong emotion"
    lang: str = "hi"

    def banner_lang(self):
        return _script_of(self.badge) if self.badge else "en"


# ----------------------------------------------------------------- templates
# Each template(base_rgb_image, d: ThumbDesign) -> RGBA image.

def t_cinematic(img, d):
    img = grade(tint(img, d.bg_tint or (10, 12, 24), 0.12), color=1.3, contrast=1.18)
    base = bottom_gradient(left_scrim(vignette(img, .8)))
    if d.kicker:
        kf = font(d.kicker, 46, "bold", d.lang)
        tracked(base, d.kicker.upper() if d.lang == "en" else d.kicker, (62, 54), kf,
                d.accent, spacing=8, stroke=3)
    base, _ = headline(base, d.title, lang=d.lang, emphasis=d.emphasis, emphasis_color=d.accent, bottom_y=H - 78, x=60, max_w=780,
                       fill=d.title_color, grad=d.grad, glow=d.glow,
                       stroke_fill=d.stroke, max_lines=3)
    if d.badge:
        badge(base, d.badge, (60, H - 66), lang=d.banner_lang(), size=46,
              fg=(255, 255, 255), bg=d.accent)
    _corner_emoji(base, d)
    return base


def t_minimal(img, d):
    img = grade(tint(img, d.bg_tint or (18, 18, 22), 0.15), color=1.1, contrast=1.1)
    base = left_scrim(img, frac=0.66, alpha=200)
    y = 150
    if d.kicker:
        kf = font(d.kicker, 40, "regular", d.lang)
        tracked(base, d.kicker.upper() if d.lang == "en" else d.kicker, (64, y), kf, d.accent, spacing=10)
        hairline(base, 64, y + 60, 90, d.accent, 6)
        y += 96
    base, _ = headline(base, d.title, lang=d.lang, emphasis=d.emphasis, emphasis_color=d.accent, top_y=y, x=64, max_w=720, weight="bold",
                       fill=d.title_color, stroke=0, max_lines=4, size_max=128, line_gap=0.12)
    return base


def t_bold_block(img, d):
    img = grade(img, color=1.4, contrast=1.25)
    base = vignette(img, .7).convert("RGBA")
    # solid accent block behind the title (magazine/bold)
    block = Image.new("RGBA", (W, 320), (0, 0, 0, 0))
    ImageDraw.Draw(block).rectangle([0, 0, 820, 320], fill=d.accent + (235,))
    base.alpha_composite(block, (0, H - 340))
    if d.badge:
        badge(base, d.badge, (60, 50), lang=d.banner_lang(), size=50,
              fg=d.accent, bg=(255, 255, 255), radius=6)
    base, _ = headline(base, d.title, lang=d.lang, emphasis=d.emphasis, emphasis_color=d.accent, bottom_y=H - 70, x=70, max_w=740,
                       weight="display", fill=(255, 255, 255), stroke=0, max_lines=3)
    _corner_emoji(base, d)
    return base


def t_neon(img, d):
    img = grade(tint(img, d.bg_tint or (8, 0, 40), 0.3), color=1.25, contrast=1.2, bright=.96)
    base = bottom_gradient(vignette(img, .85), start=.4)
    if d.kicker:
        badge(base, d.kicker, (60, 48), lang=d.lang, size=50, fg=(0, 255, 200),
              bg=None, stroke=5, stroke_fill=(30, 0, 60))
    base, _ = headline(base, d.title, lang=d.lang, emphasis=d.emphasis, emphasis_color=d.accent, bottom_y=H - 72, x=60, max_w=800,
                       grad=d.grad or ((0, 255, 255), (255, 0, 200)),
                       glow=d.glow or (120, 0, 200), glow_r=24, stroke=8,
                       stroke_fill=(15, 0, 35), max_lines=2, size_max=160)
    return base


def t_luxe(img, d):
    """Posh/minimal: thin rules, gold accents, restrained title."""
    img = grade(tint(img, d.bg_tint or (16, 14, 10), 0.2), color=1.05, contrast=1.08)
    base = left_scrim(img, frac=0.6, alpha=205)
    gold = d.accent if d.accent != (220, 30, 40) else (208, 170, 92)
    hairline(base, 64, 150, 220, gold, 4)
    if d.kicker:
        kf = font(d.kicker, 38, "regular", d.lang)
        tracked(base, d.kicker.upper() if d.lang == "en" else d.kicker, (64, 168), kf, gold, spacing=12)
    base, _ = headline(base, d.title, lang=d.lang, emphasis=d.emphasis, emphasis_color=d.accent, top_y=240, x=64, max_w=700, weight="serif",
                       fill=(245, 240, 232), stroke=0, max_lines=3, size_max=120, line_gap=0.14)
    hairline(base, 64, H - 120, 220, gold, 4)
    return base


def t_spotlight(img, d):
    img = grade(img, color=1.3, contrast=1.15)
    dark = ImageEnhance.Brightness(img).enhance(0.38)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).ellipse([W * .42, -H * .2, W * 1.05, H * .85], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(130))
    base = bottom_gradient(Image.composite(img, dark, mask))
    if d.kicker:
        badge(base, d.kicker, (60, 50), lang=d.lang, size=50, fg=d.stroke or (20, 10, 0),
              bg=d.accent, radius=30)
    base, _ = headline(base, d.title, lang=d.lang, emphasis=d.emphasis, emphasis_color=d.accent, bottom_y=H - 74, x=60, max_w=720,
                       fill=d.title_color, glow=d.glow or d.accent, glow_r=22,
                       stroke="auto", stroke_fill=d.stroke, max_lines=3)
    return base


def _corner_emoji(base, d):
    if not d.emoji:
        return
    e = emoji_img(d.emoji, 132)
    if e:
        base.alpha_composite(e, (W - 168, H - 168))


def _arrow(base, start, end, color, width=18):
    """Bold straight arrow from start->end with a filled head."""
    import math
    d = ImageDraw.Draw(base)
    d.line([start, end], fill=color, width=width)
    ang = math.atan2(end[1] - start[1], end[0] - start[0])
    hl = width * 2.6
    for s in (2.6, -2.6):
        d.line([end, (end[0] - hl * math.cos(ang - s / 4 if s > 0 else ang + s / 4),
                      end[1] - hl * math.sin(ang - s / 4 if s > 0 else ang + s / 4))],
               fill=color, width=width)


def t_split(img, d):
    """Hard split: dark title column on the left, bright subject on the right,
    separated by a bold accent divider."""
    img = grade(img, color=1.35, contrast=1.2)
    base = img.convert("RGBA")
    split_x = int(W * 0.5)
    panel = Image.new("RGBA", (split_x, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    bg = d.bg_tint or (12, 12, 18)
    pd.rectangle([0, 0, split_x, H], fill=bg + (232,))
    base.alpha_composite(panel, (0, 0))
    ImageDraw.Draw(base).rectangle([split_x - 9, 0, split_x + 9, H], fill=d.accent + (255,))
    if d.kicker:
        badge(base, d.kicker, (56, 50), lang=d.lang, size=46, fg=(255, 255, 255), bg=d.accent)
    base, _ = headline(base, d.title, lang=d.lang, emphasis=d.emphasis, emphasis_color=d.accent, x=56, max_w=split_x - 110,
                       top_y=150, max_h=420, fill=d.title_color, glow=d.glow,
                       stroke_fill=d.stroke, max_lines=4, size_max=120)
    _corner_emoji(base, d)
    return base


def t_callout(img, d):
    """Circle + arrow drawing the eye to the subject (right), title on the left."""
    img = grade(tint(img, d.bg_tint or (10, 10, 18), 0.1), color=1.3, contrast=1.18)
    base = bottom_gradient(left_scrim(vignette(img, .75)))
    cx, cy, r = int(W * 0.74), int(H * 0.42), 150
    for i, wdt in enumerate((22, 14)):
        col = d.accent if i == 0 else (255, 255, 255)
        ImageDraw.Draw(base).ellipse([cx - r, cy - r, cx + r, cy + r], outline=col + (255,), width=wdt)
        r -= 4
    _arrow(base, (int(W * 0.40), int(H * 0.30)), (cx - 140, cy - 40), d.accent, 16)
    if d.kicker:
        badge(base, d.kicker, (56, 48), lang=d.lang, size=46, fg=(255, 255, 255), bg=d.accent)
    base, _ = headline(base, d.title, lang=d.lang, emphasis=d.emphasis, emphasis_color=d.accent, x=56, max_w=560, bottom_y=H - 80,
                       fill=d.title_color, glow=d.glow, stroke_fill=d.stroke, max_lines=3)
    return base


def t_before_after(img, d):
    """Single-image before/after: cold desaturated left vs vivid right, split by
    a white divider with labels. Title spans the bottom."""
    half = W // 2
    cold = ImageEnhance.Color(img).enhance(0.25)
    cold = ImageEnhance.Brightness(cold).enhance(0.7)
    warm = grade(img, color=1.5, contrast=1.25, bright=1.05)
    base = Image.new("RGB", (W, H))
    base.paste(cold.crop((0, 0, half, H)), (0, 0))
    base.paste(warm.crop((half, 0, W, H)), (half, 0))
    base = bottom_gradient(base.convert("RGBA"))
    ImageDraw.Draw(base).rectangle([half - 6, 0, half + 6, H], fill=(255, 255, 255, 255))
    def_before, def_after = _BEFORE_AFTER.get(d.lang, _BEFORE_AFTER["en"])
    lbl_before, lbl_after = (d.kicker or def_before), (d.badge or def_after)
    badge(base, lbl_before, (40, 40), lang=_script_of(lbl_before), size=44,
          fg=(255, 255, 255), bg=(70, 80, 90))
    bb = badge(base, lbl_after, (half + 40, 40), lang=_script_of(lbl_after), size=44,
               fg=(20, 20, 20), bg=d.accent)
    base, _ = headline(base, d.title, lang=d.lang, emphasis=d.emphasis, emphasis_color=d.accent, x=0, max_w=W - 120, align="center",
                       bottom_y=H - 60, fill=d.title_color, stroke_fill=d.stroke,
                       glow=d.glow, max_lines=2, size_max=120)
    return base


def duotone(img, dark, light):
    """Map luminance to a two-color ramp (modern poster look)."""
    g = ImageOps.grayscale(img)
    return ImageOps.colorize(g, black=dark, white=light).convert("RGB")


def t_magazine(img, d):
    """Editorial: thin top/bottom rules, a kicker label, serif headline."""
    img = grade(tint(img, d.bg_tint or (14, 14, 16), 0.16), color=1.1, contrast=1.1)
    base = left_scrim(img, frac=0.64, alpha=200)
    hairline(base, 56, 60, W - 112, d.accent, 5)
    if d.kicker:
        kf = font(d.kicker, 40, "regular", d.lang)
        tracked(base, d.kicker.upper() if d.lang == "en" else d.kicker, (56, 80), kf, d.accent, spacing=12)
    base, _ = headline(base, d.title, lang=d.lang, emphasis=d.emphasis, emphasis_color=d.accent, weight="serif", top_y=150, x=56,
                       max_w=720, fill=d.title_color, stroke=0, max_lines=4,
                       size_max=118, line_gap=0.14)
    hairline(base, 56, H - 60, W - 112, d.accent, 5)
    if d.badge:
        badge(base, d.badge, (56, H - 130), lang=d.banner_lang(), size=44,
              fg=(255, 255, 255), bg=d.accent)
    return base


def t_sticker(img, d):
    """Playful: title in a thick-bordered rounded sticker."""
    img = grade(img, color=1.45, contrast=1.2)
    base = bottom_gradient(vignette(img, .7))
    if d.kicker:
        badge(base, d.kicker, (56, 48), lang=d.lang, size=48, fg=(20, 20, 20),
              bg=(255, 255, 255), radius=40)
    f = font(d.title, 110, "display", d.lang)
    lines = wrap(d.title, f, 660)
    while len(lines) > 3 and f.size > 60:
        f = font(d.title, f.size - 6, "display", d.lang)
        lines = wrap(d.title, f, 660)
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * 1.02)
    tw = max(_w(l, f) for l in lines)
    pad = 30
    x0, y1 = 50, H - 70
    y0 = y1 - lh * len(lines) - pad * 2
    d2 = ImageDraw.Draw(base)
    d2.rounded_rectangle([x0, y0, x0 + tw + pad * 2, y1], radius=28, fill=d.accent + (255,),
                         outline=(255, 255, 255, 255), width=8)
    for i, ln in enumerate(lines):
        d2.text((x0 + pad, y0 + pad + i * lh), ln, font=f, fill=d.title_color,
                stroke_width=4, stroke_fill=d.stroke)
    _corner_emoji(base, d)
    return base


def t_duotone(img, d):
    """Bold duotone wash + heavy headline — music/poster energy."""
    dk = tuple(min(c, 40) for c in (d.bg_tint or (10, 4, 30)))
    lt = d.accent
    base = bottom_gradient(duotone(img, dk, lt).convert("RGBA"), rgb=dk, start=0.25)
    if d.kicker:
        badge(base, d.kicker, (56, 48), lang=d.lang, size=50, fg=(20, 20, 20),
              bg=(255, 255, 255), radius=6)
    base, _ = headline(base, d.title, lang=d.lang, emphasis=d.emphasis, emphasis_color=d.accent, weight="display", bottom_y=H - 72,
                       x=56, max_w=820, fill=d.title_color, stroke=0, max_lines=3,
                       size_max=170)
    return base


def t_frame(img, d):
    """Premium: full inner border frame with corner ticks, centered-low title."""
    img = grade(tint(img, d.bg_tint or (12, 12, 16), 0.14), color=1.15, contrast=1.12)
    base = bottom_gradient(vignette(img, .8))
    m = 28
    dd = ImageDraw.Draw(base)
    dd.rectangle([m, m, W - m, H - m], outline=d.accent + (255,), width=6)
    for cx, cy in ((m, m), (W - m, m), (m, H - m), (W - m, H - m)):
        dd.rectangle([cx - 22, cy - 22, cx + 22, cy + 22], outline=(255, 255, 255, 255), width=6)
    if d.kicker:
        kf = font(d.kicker, 44, "regular", d.lang)
        tracked(base, d.kicker.upper() if d.lang == "en" else d.kicker,
                (60, 60), kf, d.accent, spacing=10)
    base, _ = headline(base, d.title, lang=d.lang, emphasis=d.emphasis, emphasis_color=d.accent, bottom_y=H - 80, x=60, max_w=W - 200,
                       align="center", fill=d.title_color, glow=d.glow,
                       stroke_fill=d.stroke, max_lines=3)
    return base


def t_lower_third(img, d):
    """Broadcast lower-third: accent bar + dark sub-bar with the title."""
    img = grade(img, color=1.3, contrast=1.15)
    base = bottom_gradient(img.convert("RGBA"), start=0.45)
    bar_y = H - 230
    dd = ImageDraw.Draw(base)
    dd.rectangle([0, bar_y, W, bar_y + 14], fill=d.accent + (255,))
    dd.rectangle([0, bar_y + 14, W, H], fill=(0, 0, 0, 205))
    if d.kicker:
        badge(base, d.kicker, (56, bar_y - 78), lang=d.lang, size=46,
              fg=(255, 255, 255), bg=d.accent, radius=4)
    base, _ = headline(base, d.title, lang=d.lang, emphasis=d.emphasis, emphasis_color=d.accent, top_y=bar_y + 40, x=56, max_w=W - 120,
                       max_h=150, fill=d.title_color, stroke=0, max_lines=2, size_max=96)
    return base


def t_vs(img, d):
    """Comparison: split with a circular VS badge dividing the two sides."""
    img = grade(img, color=1.35, contrast=1.2)
    base = img.convert("RGBA")
    half = W // 2
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle([0, 0, half, H], fill=(0, 0, 0, 150))
    base = Image.alpha_composite(base, sh)
    dd = ImageDraw.Draw(base)
    dd.rectangle([half - 5, 0, half + 5, H], fill=(255, 255, 255, 255))
    r = 78
    dd.ellipse([half - r, H // 2 - r, half + r, H // 2 + r], fill=d.accent + (255,),
               outline=(255, 255, 255, 255), width=7)
    vf = font("VS", 92, "display", "en")
    vb = vf.getbbox("VS")
    dd.text((half - (vb[2] - vb[0]) // 2 - vb[0], H // 2 - (vb[3] - vb[1]) // 2 - vb[1]),
            "VS", font=vf, fill=(255, 255, 255))
    base, _ = headline(base, d.title, lang=d.lang, emphasis=d.emphasis, emphasis_color=d.accent, bottom_y=H - 70, x=0, max_w=W - 120,
                       align="center", fill=d.title_color, glow=d.glow,
                       stroke_fill=d.stroke, max_lines=2, size_max=110)
    return base


TEMPLATES = {
    "cinematic": t_cinematic,
    "minimal": t_minimal,
    "bold_block": t_bold_block,
    "neon": t_neon,
    "luxe": t_luxe,
    "spotlight": t_spotlight,
    "split": t_split,
    "callout": t_callout,
    "before_after": t_before_after,
    "magazine": t_magazine,
    "sticker": t_sticker,
    "duotone": t_duotone,
    "frame": t_frame,
    "lower_third": t_lower_third,
    "vs": t_vs,
}


def render(design: ThumbDesign, bg: Path, out: Path) -> Path:
    frame = cover(Image.open(bg).convert("RGB"))
    fn = TEMPLATES.get(design.template, t_cinematic)
    result = fn(frame, design)
    out.parent.mkdir(parents=True, exist_ok=True)
    result.convert("RGB").save(out, "PNG")
    return out
