"""Unit tests for yta pure logic (no network, no ffmpeg)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.generate import seo
from src.generate.captions import _split_sentences, _ts, build_ass
from src.generate.script import StoryScript, Scene, ThumbnailConcept
from src.clients.klipr import KliprClient, JobResult


# ----------------------------- captions
def test_split_sentences_devanagari_and_ascii():
    out = _split_sentences("पहला वाक्य। दूसरा वाक्य! तीसरा?")
    assert len(out) == 3


def test_ts_format():
    assert _ts(0) == "0:00:00.00"
    assert _ts(65.5) == "0:01:05.50"


class _S:
    def __init__(self, n): self.narration = n


def test_build_ass_skips_title_when_no_intro(tmp_path, monkeypatch):
    # wav_duration is called per scene; stub it to a constant.
    import src.generate.captions as cap
    monkeypatch.setattr(cap, "wav_duration", lambda p: 4.0)
    scenes = [_S("एक वाक्य।"), _S("दूसरा वाक्य।")]
    audios = [Path("a.wav"), Path("b.wav")]
    with_title = build_ass(scenes, audios, intro_s=3, outro_s=4,
                           intro_title="मेरी कहानी", outro_text="Subscribe")
    no_title = build_ass(scenes, audios, intro_s=0, outro_s=4,
                         intro_title="", outro_text="Subscribe")
    assert "मेरी कहानी" in with_title
    assert "Title,," in with_title           # a Title dialogue event exists
    assert "मेरी कहानी" not in no_title       # skipped when no intro/title
    assert "[Script Info]" in with_title  # ASS header present
    # language picks the right Noto family (Telugu input -> Noto Sans Telugu).
    te = build_ass(scenes, audios, intro_s=3, outro_s=4,
                   intro_title="తెలుగు", outro_text="Subscribe", language="te")
    assert "Noto Sans Telugu" in te


# ----------------------------- seo
def test_build_tags_dedup_and_cap():
    tags = ["a", "a", "b", "c"]
    out = seo.build_tags(tags, base_tags=["c", "d"])
    assert out == ["a", "b", "c", "d"]          # deduped, order preserved
    big = ["x" * 50 for _ in range(40)]
    assert len(seo.build_tags(big)) <= 30       # capped


def test_build_description_has_keywords_and_cta():
    d = seo.build_description("Title", "Title", "base desc", ["k1", "k2"],
                              channel={"name": "Chan", "cta": "SUB NOW"})
    assert "base desc" in d and "SUB NOW" in d
    assert "k1, k2" in d and "#" in d           # keywords + hashtags


# ----------------------------- klipr client (pure parts)
def test_source_fields():
    assert KliprClient._source_fields("youtube", "u") == {"source_type": "youtube", "source_url": "u"}
    assert KliprClient._source_fields("upload", "u") == {"source_type": "upload", "source_external_url": "u"}


def test_klipr_requires_key():
    import pytest
    with pytest.raises(ValueError):
        KliprClient("")


def test_jobresult_shape():
    r = JobResult(id="1", kind="dub", status="ready", download_url="u", error_message=None, raw={})
    assert r.status == "ready" and r.download_url == "u"


# ----------------------------- web helpers
def test_resolve_channel_merges_override(monkeypatch):
    import src.web.app as app
    monkeypatch.setattr(app, "load_config", lambda: {"channel": {"name": "Base", "language": "hi", "scenes": 16}})
    merged = app._resolve_channel({"language": "te", "name": ""})
    assert merged["language"] == "te"           # override applied
    assert merged["name"] == "Base"             # empty override ignored
    assert merged["scenes"] == 16               # default kept


def test_script_from_dict_back_compat():
    import src.web.app as app
    s = app._script_from_dict({"title": "T", "tags": [], "description": "",
                               "scenes": [{"id": 1, "narration_hi": "old field", "image_prompt": "p"}],
                               "thumbnail": {"subject": "x", "hook": "h", "mood": "m"}})
    assert isinstance(s, StoryScript)
    assert s.scenes[0].narration == "old field"  # narration_hi -> narration
    assert s.thumbnail.hook == "h"


# ----------------------------- finishing pure helpers
def test_position_map_has_eight():
    from src.generate.finishing import _POS
    assert set(["top-right", "bottom-right", "bottom-center", "mid-left"]).issubset(_POS)
    assert len(_POS) == 8


def test_prepare_music_none(tmp_path):
    from src.generate.finishing import prepare_music
    assert prepare_music(tmp_path, 30.0, mode="none") is None


# ----------------------------- thumbnail layout
def test_layout_title_short_stays_max_size():
    from src.generate.thumbnail import layout_title, TITLE_SIZE_MAX
    text, size = layout_title("मोहिनी", "hi")
    assert size == TITLE_SIZE_MAX and "\\N" not in text


def test_layout_title_long_wraps_and_shrinks():
    from src.generate.thumbnail import layout_title, TITLE_SIZE_MAX
    text, size = layout_title("आधी रात को दरवाज़ा किसने खटखटाया", "hi")
    assert "\\N" in text                      # wrapped to multiple lines
    assert text.count("\\N") + 1 <= 3         # within max_lines
    assert size < TITLE_SIZE_MAX              # shrank to fit


def test_layout_title_height_budget():
    # three tall Telugu lines must shrink so the block fits above the banner
    from src.generate.thumbnail import layout_title, TITLE_SIZE_MAX
    _, size = layout_title("భేడియా మనిషి రహస్యం", "te")
    assert size < TITLE_SIZE_MAX


def test_layout_title_honors_hard_break():
    from src.generate.thumbnail import layout_title
    text, _ = layout_title("भाग एक|रहस्य", "hi")
    assert text.split("\\N")[0] == "भाग एक"


def test_build_thumb_ass_includes_kicker_and_styles():
    from src.generate.thumbnail import build_thumb_ass
    ass = build_thumb_ass("मोहिनी", kicker="डरावनी कहानी",
                          banner="BASED ON A TRUE STORY", language="hi")
    assert "Style: Kicker," in ass and "Style: BigTitle," in ass
    assert "Dialogue: 0,0:00:00.00,0:00:02.00,Kicker,,0,0,0,,डरावनी कहानी" in ass
    # title font matches the Devanagari script of the text
    assert "Noto Sans Devanagari" in ass


def test_build_thumb_ass_no_kicker_omits_event():
    from src.generate.thumbnail import build_thumb_ass
    ass = build_thumb_ass("मोहिनी", language="hi")
    assert ",Kicker,," not in ass


def test_ass_bgr_to_rgb():
    from src.generate.thumbnail import _ass_bgr_to_rgb
    assert _ass_bgr_to_rgb("&H000000FF") == (255, 0, 0)   # red
    assert _ass_bgr_to_rgb("&H00FFFFFF") == (255, 255, 255)


# ----------------------------- thumbnail design + local render
def test_choose_design_fallback_horror(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from src.generate.thumbnail_design import choose_design
    d = choose_design(title="t", hook="खूनी कुआँ", subject="s",
                      mood="scary", niche="horror stories", language="hi")
    assert d.template in ("cinematic",) and d.accent == (180, 0, 0)  # blood palette
    assert d.title == "खूनी कुआँ" and d.lang == "hi"


def test_choose_design_fallback_luxury(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from src.generate.thumbnail_design import choose_design
    d = choose_design(title="t", hook="WEALTH SECRETS", subject="s", mood="",
                      niche="luxury wealth", language="en")
    assert d.template == "luxe"


def test_render_all_templates(tmp_path, monkeypatch):
    from PIL import Image
    from src.generate.thumbnail_render import render, ThumbDesign, TEMPLATES
    from src.generate.thumbnail_design import PALETTES
    bg = tmp_path / "bg.png"
    Image.new("RGB", (1280, 720), (40, 30, 50)).save(bg)
    for tpl in TEMPLATES:
        out = render(ThumbDesign(title="आधी रात की कहानी", template=tpl,
                                 kicker="कहानी", badge="NEW", lang="hi",
                                 **PALETTES["crimson"]), bg, tmp_path / f"{tpl}.png")
        im = Image.open(out)
        assert im.size == (1280, 720)


def test_make_thumbnail_local_engine(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from PIL import Image
    from src.generate import thumbnail as tn

    def fake_gen(prompt, dest, **kw):
        Image.new("RGB", (1280, 720), (30, 20, 40)).save(dest)
        return dest
    monkeypatch.setattr(tn, "generate_image", fake_gen)
    out = tn.make_thumbnail("खूनी कुआँ", tmp_path / "thumb", engine="local",
                            language="hi", niche="horror", hook="खूनी कुआँ")
    assert out.exists() and Image.open(out).size == (1280, 720)


def test_new_templates_registered():
    from src.generate.thumbnail_render import TEMPLATES
    for t in ("split", "callout", "before_after"):
        assert t in TEMPLATES


def test_apply_palette_overrides_colors():
    from src.generate.thumbnail_render import ThumbDesign
    from src.generate.thumbnail_design import apply_palette, PALETTES
    d = ThumbDesign(title="x")
    apply_palette(d, "gold_luxe")
    assert d.accent == PALETTES["gold_luxe"]["accent"]


def test_display_font_stays_in_script():
    # an Indic title requesting a Latin-only display weight must NOT get Anton
    from src.generate.thumbnail_render import font, _FONT_FILES
    f = font("दरवाज़ा", 80, "display", "hi")
    assert "Anton" not in f.path and "Devanagari" in f.path


def test_emphasis_renders_without_breaking(tmp_path):
    from PIL import Image
    from src.generate.thumbnail_render import render, ThumbDesign
    from src.generate.thumbnail_design import PALETTES
    bg = tmp_path / "bg.png"; Image.new("RGB", (1280, 720), (30, 20, 40)).save(bg)
    out = render(ThumbDesign(title="दरवाज़े के पीछे कौन था", template="cinematic",
                             emphasis="कौन", lang="hi", **PALETTES["crimson"]),
                 bg, tmp_path / "e.png")
    assert Image.open(out).size == (1280, 720)


def test_palette_and_template_counts():
    from src.generate.thumbnail_render import TEMPLATES
    from src.generate.thumbnail_design import PALETTES
    assert len(TEMPLATES) == 15 and len(PALETTES) == 24
