"""UI / API automation tests (FastAPI TestClient, mocked pipeline)."""
import json

from conftest import wait_job

SCRIPT = {"title": "T", "title_translit": "T", "description": "d", "tags": ["a"],
          "thumbnail": {"subject": "s", "hook": "h", "mood": "m"},
          "scenes": [{"id": 1, "narration": "n1", "image_prompt": "p1"},
                     {"id": 2, "narration": "n2", "image_prompt": "p2"}]}


def test_index_serves_ui(client):
    r = client.get("/")
    assert r.status_code == 200 and "yta" in r.text and "Channel" in r.text


def test_channels_catalog(client):
    d = client.get("/api/channels").json()
    assert "Hindi Horror" in d["profiles"]
    assert any(v["id"] == "anushka" for v in d["voices"])
    assert any(l["code"] == "te" for l in d["languages"])
    assert d["lang_defaults"]["te"]["voice_speaker"]   # per-language default present


def test_script_paste(client):
    r = client.post("/api/script", json={"script": json.dumps(SCRIPT)})
    assert r.status_code == 200
    assert r.json()["title"] == "T" and len(r.json()["scenes"]) == 2


def test_script_paste_invalid_json(client):
    assert client.post("/api/script", json={"script": "{not json"}).status_code == 400


def test_script_generate_topic(client):
    r = client.post("/api/script", json={"topic": "a haunted clock", "channel": {}})
    assert r.status_code == 200 and r.json()["title"] == "Gen"


def test_youtube_accounts_empty(client):
    assert client.get("/api/youtube/accounts").json() == {"accounts": []}


def _generate(client, channel, **form):
    data = {"script": json.dumps(SCRIPT), "channel": json.dumps(channel), **form}
    jid = client.post("/api/generate", data=data).json()["job_id"]
    return wait_job(client, jid)


def test_generate_free_keeps_klipr_and_windows_bottom_logo(client):
    j = _generate(client, {"language": "hi", "premium": False},
                  music_mode="generate", make_shorts="false", bottom_logo="default",
                  intro_mode="generate")
    assert j["status"] == "done", j.get("error")
    assert j["result"]["video_url"].startswith("/api/video/")
    items = client.captured["overlay_items"]
    pos = {it["position"]: it for it in items}
    assert "top-right" in pos                         # Klipr kept (free)
    assert pos["bottom-right"]["start"] == 3.0        # bottom logo only on real video
    assert pos["bottom-right"]["end"] == 33.0


def test_generate_premium_removes_klipr(client):
    j = _generate(client, {"language": "hi", "premium": True},
                  music_mode="none", make_shorts="false", bottom_logo="default",
                  intro_mode="none")
    assert j["status"] == "done"
    positions = [it["position"] for it in client.captured["overlay_items"]]
    assert "top-right" not in positions               # Klipr removed (premium)
    assert "bottom-right" in positions


def test_generate_bottom_logo_none(client):
    _generate(client, {"language": "hi", "premium": False},
              music_mode="none", bottom_logo="none", intro_mode="generate")
    positions = [it["position"] for it in client.captured["overlay_items"]]
    assert "bottom-right" not in positions            # don't-add honored
    assert "top-right" in positions


def test_generate_with_short(client):
    j = _generate(client, {"language": "hi"}, make_shorts="true", intro_mode="generate")
    assert j["status"] == "done"
    assert j["result"].get("short_url", "").startswith("/api/short/")


def test_generate_then_video_and_thumbnail_served(client):
    j = _generate(client, {"language": "hi"}, intro_mode="generate")
    work = j["result"]["work"]
    assert client.get(f"/api/video/{work}").status_code == 200
    # thumbnail job
    tj = client.post("/api/thumbnail", json={"work": work}).json()["job_id"]
    t = wait_job(client, tj)
    assert t["status"] == "done"
    assert client.get(f"/api/thumb/{work}").status_code == 200


def test_upload_targets_env_when_no_account(client, monkeypatch):
    import src.web.app as app
    captured = {}

    class FakeYT:
        def upload_from_file(self, p, title, desc, **k):
            captured["title"] = title; return "vid123"
        def set_thumbnail(self, vid, t): captured["thumb"] = True
    monkeypatch.setattr(app, "youtube_for", lambda lang: FakeYT())

    j = _generate(client, {"language": "hi"}, intro_mode="none")
    work = j["result"]["work"]
    uj = client.post("/api/upload", json={"work": work}).json()["job_id"]
    u = wait_job(client, uj)
    assert u["status"] == "done"
    assert u["result"]["youtube_url"] == "https://youtu.be/vid123"
    assert "title" in captured
