"""Test harness: a FastAPI TestClient with all heavy/external pipeline steps
mocked so the UI/API can be tested fast and offline. Captures the overlay_logos
items so branding (logo windowing, premium) can be asserted."""
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def client(tmp_path, monkeypatch):
    import src.web.app as app

    # Route work dirs into tmp so tests don't litter artifacts/.
    monkeypatch.setattr(app, "WORK_ROOT", tmp_path / "web")
    (tmp_path / "web").mkdir(parents=True, exist_ok=True)

    # Deterministic config (no real config.yaml dependency for branding).
    monkeypatch.setattr(app, "load_config", lambda: {
        "channel": {"name": "TestChan", "language": "hi", "voice_speaker": "anushka",
                    "scenes": 3, "outro_text": "Sub 🔔", "title_suffix": " | T"},
        "profiles": {"Hindi Horror": {"name": "TestChan", "language": "hi", "voice_speaker": "anushka"}},
        "branding": {"logos": [
            {"path": "assets/logos/klipr.png", "position": "top-right", "scale": 0.12},
            {"path": "assets/logo_trans_white_letter.png", "position": "bottom-right", "scale": 0.16}]},
        "thumbnail": {"banner_text": "TEST"},
        "publish": {"initial_privacy": "private"},
        "klipr": {"base_url": "https://klipr.in/api/batch"},
    })

    captured = {"overlay_items": None}

    # --- mock the heavy pipeline ---
    monkeypatch.setattr(app, "generate_scene_images",
                        lambda scenes, d, **k: [Path(d) / f"s{ s.id }.png" for s in scenes])
    monkeypatch.setattr(app, "synthesize_scenes",
                        lambda scenes, d, **k: [Path(d) / f"s{ s.id }.wav" for s in scenes])

    def fake_skeleton(scenes, images, audios, work, **kw):
        work = Path(work); work.mkdir(parents=True, exist_ok=True)
        f = work / "finished_nocaps.mp4"; f.write_bytes(b"\x00")
        return f, "ASS", {"intro_s": 3.0, "body_dur": 30.0, "body_end": 33.0}
    monkeypatch.setattr(app, "build_finished_skeleton", fake_skeleton)
    monkeypatch.setattr(app, "upload_and_sign", lambda p, key, **k: "https://x.supabase.co/" + key)

    class FakeKlipr:
        async def caption_burn(self, url, ass, watermark=True):
            return SimpleNamespace(download_url="https://x/y.mp4", status="ready")
    monkeypatch.setattr(app, "KliprClient_from_env", lambda: FakeKlipr())

    class FakeStream:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def raise_for_status(self): pass
        def read(self): return b"\x00\x00"
        def iter_bytes(self): yield b"\x00\x00"
    import httpx
    monkeypatch.setattr(httpx, "stream", lambda *a, **k: FakeStream())

    def fake_overlay(src, out, items):
        captured["overlay_items"] = items
        Path(out).write_bytes(b"\x00"); return Path(out)
    monkeypatch.setattr(app, "overlay_logos", fake_overlay)
    monkeypatch.setattr(app, "player_safe",
                        lambda src, out: (Path(out).write_bytes(b"\x00"), Path(out))[1])
    monkeypatch.setattr(app, "make_short",
                        lambda src, out, **k: (Path(out).write_bytes(b"\x00"), Path(out))[1])

    def fake_thumb(title, work, **kw):
        work = Path(work); work.mkdir(parents=True, exist_ok=True)
        t = work / "t.png"; t.write_bytes(b"\x89PNG"); return t
    monkeypatch.setattr(app, "make_thumbnail", fake_thumb)

    # script generation (Claude) — only used for topic path
    monkeypatch.setattr(app, "generate_script", lambda channel=None, theme=None, **k:
                        app.StoryScript("Gen", "Gen", "d", ["t"],
                                        app.ThumbnailConcept("s", "h", "m"),
                                        [app.Scene(1, "n", "p")]))

    from fastapi.testclient import TestClient
    c = TestClient(app.app)        # the FastAPI instance, not the module
    c.captured = captured
    return c


def wait_job(client, jid, timeout=15):
    for _ in range(int(timeout / 0.2)):
        j = client.get(f"/api/job/{jid}").json()
        if j["status"] in ("done", "error"):
            return j
        time.sleep(0.2)
    raise AssertionError("job did not finish")
