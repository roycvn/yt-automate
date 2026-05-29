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
