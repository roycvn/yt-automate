"""FastAPI UI for the yta video engine.

Flow (matches the 7-step UI):
  1. /api/script        generate from a topic OR accept a pasted script
  2. /api/generate      images+voice+assemble+(bg music)+captions+logos -> video
                        (bg music: none | generate | upload; + intensity)
  3. /api/thumbnail     create/regenerate the thumbnail
  4. /api/video|thumb   preview the final video / thumbnail
  5. /api/download      download the final mp4
  6. /api/youtube/...   status + auto-upload

Long steps run as background jobs; the UI polls /api/job/{id}.
Run:  uvicorn src.web.app:app --reload  (or python -m src.web.app)
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import load_config
from ..generate.script import generate_script, StoryScript, Scene, ThumbnailConcept
from ..generate.images import generate_scene_images
from ..generate.voice import synthesize_scenes
from ..generate.finishing import build_finished_skeleton, overlay_logos, player_safe, make_short
from ..generate.thumbnail import make_thumbnail
from ..generate import seo
from ..clients.klipr import KliprClient
from ..clients.storage import upload_and_sign
from ..produce import youtube_for
from . import yt_accounts

ROOT = Path(__file__).resolve().parent.parent.parent
WORK_ROOT = ROOT / "artifacts" / "web"
STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="yta studio")
_pool = ThreadPoolExecutor(max_workers=2)
_jobs: dict[str, dict] = {}

# Sarvam bulbul:v2 speakers + supported languages for the UI pickers.
VOICES = [
    {"id": "anushka", "label": "Anushka (F)"}, {"id": "manisha", "label": "Manisha (F)"},
    {"id": "vidya", "label": "Vidya (F)"}, {"id": "arya", "label": "Arya (F)"},
    {"id": "abhilash", "label": "Abhilash (M)"}, {"id": "karun", "label": "Karun (M)"},
    {"id": "hitesh", "label": "Hitesh (M)"},
]
LANGUAGES = [
    {"code": "hi", "label": "Hindi"}, {"code": "te", "label": "Telugu"},
    {"code": "ta", "label": "Tamil"}, {"code": "bn", "label": "Bengali"},
    {"code": "kn", "label": "Kannada"}, {"code": "ml", "label": "Malayalam"},
    {"code": "mr", "label": "Marathi"}, {"code": "gu", "label": "Gujarati"},
    {"code": "pa", "label": "Punjabi"}, {"code": "od", "label": "Odia"},
    {"code": "en", "label": "English"},
]

# Per-language smart defaults: pick a good Sarvam voice, the proper
# language_name, and a localized "subscribe" phrase. Selecting a language in
# the UI auto-applies these so the user barely has to configure anything.
LANG_DEFAULTS = {
    "hi": {"language_name": "Hindi (Devanagari)", "voice_speaker": "anushka", "subscribe": "सब्सक्राइब करें 🔔"},
    "te": {"language_name": "Telugu", "voice_speaker": "vidya", "subscribe": "సబ్‌స్క్రైబ్ చేయండి 🔔"},
    "ta": {"language_name": "Tamil", "voice_speaker": "vidya", "subscribe": "சந்தா செலுத்துங்கள் 🔔"},
    "bn": {"language_name": "Bengali", "voice_speaker": "anushka", "subscribe": "সাবস্ক্রাইব করুন 🔔"},
    "kn": {"language_name": "Kannada", "voice_speaker": "vidya", "subscribe": "ಚಂದಾದಾರರಾಗಿ 🔔"},
    "ml": {"language_name": "Malayalam", "voice_speaker": "vidya", "subscribe": "സബ്സ്ക്രൈബ് ചെയ്യൂ 🔔"},
    "mr": {"language_name": "Marathi", "voice_speaker": "karun", "subscribe": "सबस्क्राइब करा 🔔"},
    "gu": {"language_name": "Gujarati", "voice_speaker": "manisha", "subscribe": "સબ્સ્ક્રાઇબ કરો 🔔"},
    "pa": {"language_name": "Punjabi", "voice_speaker": "anushka", "subscribe": "ਸਬਸਕ੍ਰਾਈਬ ਕਰੋ 🔔"},
    "od": {"language_name": "Odia", "voice_speaker": "anushka", "subscribe": "ସବସ୍କ୍ରାଇବ୍ କରନ୍ତୁ 🔔"},
    "en": {"language_name": "English", "voice_speaker": "hitesh", "subscribe": "Subscribe 🔔"},
}


def _resolve_channel(override: dict | None) -> dict:
    """Merge a UI channel override over the config default channel."""
    base = dict(load_config().get("channel", {}))
    if override:
        base.update({k: v for k, v in override.items() if v not in (None, "")})
    return base


# ----------------------------------------------------------------- helpers
def _script_from_dict(d: dict) -> StoryScript:
    th = d.get("thumbnail") or {}
    return StoryScript(
        title=d.get("title", ""), title_translit=d.get("title_translit", ""),
        description=d.get("description", ""), tags=d.get("tags", []),
        thumbnail=ThumbnailConcept(th.get("subject", ""), th.get("hook", ""), th.get("mood", "")),
        scenes=[Scene(s["id"], s.get("narration") or s.get("narration_hi", ""),
                      s["image_prompt"]) for s in d.get("scenes", [])])


def _run_job(fn) -> str:
    jid = uuid.uuid4().hex[:12]
    _jobs[jid] = {"status": "running", "step": "starting", "result": None, "error": None}

    def wrap():
        try:
            _jobs[jid]["result"] = fn(lambda s: _jobs[jid].update(step=s))
            _jobs[jid]["status"] = "done"
        except Exception as e:  # noqa: BLE001
            _jobs[jid]["status"] = "error"
            _jobs[jid]["error"] = str(e)[:500]

    _pool.submit(wrap)
    return jid


# ----------------------------------------------------------------- routes
@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC / "index.html").read_text()


@app.get("/api/channels")
def api_channels() -> dict:
    cfg = load_config()
    return {"profiles": cfg.get("profiles", {}), "default": cfg.get("channel", {}),
            "voices": VOICES, "languages": LANGUAGES, "lang_defaults": LANG_DEFAULTS}


@app.post("/api/script")
def api_script(payload: dict) -> dict:
    """Accept a pasted script (JSON) or generate one from a topic/brief."""
    pasted = (payload.get("script") or "").strip()
    if pasted:
        try:
            data = json.loads(pasted)
        except json.JSONDecodeError:
            raise HTTPException(400, "Pasted script must be valid JSON (title, scenes[], ...).")
        return _script_from_dict(data).to_dict()
    channel = _resolve_channel(payload.get("channel"))
    try:
        s = generate_script(channel=channel, theme=payload.get("topic") or None)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"script generation failed: {str(e)[:300]}"},
                            status_code=502)
    return s.to_dict()


@app.post("/api/generate")
async def api_generate(script: str = Form(...), music_mode: str = Form("generate"),
                       music_intensity: float = Form(0.32), channel: str = Form("{}"),
                       make_shorts: bool = Form(False), bottom_logo: str = Form("default"),
                       intro_mode: str = Form("generate"),
                       music_file: UploadFile | None = File(None),
                       logo_file: UploadFile | None = File(None),
                       intro_file: UploadFile | None = File(None)) -> dict:
    cfg = load_config()
    channel = _resolve_channel(json.loads(channel or "{}"))
    story = _script_from_dict(json.loads(script))
    work = WORK_ROOT / f"job-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    work.mkdir(parents=True, exist_ok=True)
    (work / "script.json").write_text(json.dumps(story.to_dict(), ensure_ascii=False, indent=2))
    (work / "channel.json").write_text(json.dumps(channel, ensure_ascii=False, indent=2))

    music_path = None
    if music_mode == "upload" and music_file is not None:
        music_path = work / f"music_upload{Path(music_file.filename or 'bg').suffix or '.mp3'}"
        music_path.write_bytes(await music_file.read())

    # Custom channel logo (bottom-right). Klipr logo (top-right) stays global.
    custom_logo = None
    if logo_file is not None:
        custom_logo = work / f"logo_upload{Path(logo_file.filename or 'logo').suffix or '.png'}"
        custom_logo.write_bytes(await logo_file.read())

    intro_path = None
    if intro_mode == "upload" and intro_file is not None:
        intro_path = work / f"intro_upload{Path(intro_file.filename or 'intro').suffix or '.mp4'}"
        intro_path.write_bytes(await intro_file.read())

    def job(step):
        step("generating images")
        images = generate_scene_images(story.scenes, work / "images")
        step("synthesizing narration")
        audios = synthesize_scenes(story.scenes, work / "audio",
                                   language=channel.get("language", "hi"),
                                   speaker=channel.get("voice_speaker", "anushka"))
        step("assembling + background music")
        finished, ass, meta = build_finished_skeleton(
            story.scenes, images, audios, work / "finish",
            intro_title=story.title,
            outro_text=channel.get("outro_text", f"{channel.get('name','Subscribe')} 🔔"),
            music_mode=music_mode, music_path=music_path, music_intensity=music_intensity,
            intro_mode=intro_mode, intro_path=intro_path)
        step("burning captions (klipr)")
        klipr = KliprClient_from_env()
        url = upload_and_sign(finished, f"web/{work.name}.mp4")
        res = asyncio.run(klipr.caption_burn(url, ass, watermark=False))
        import httpx
        raw = work / "captioned.mp4"
        with httpx.stream("GET", res.download_url, timeout=600) as r:
            r.raise_for_status(); raw.write_bytes(r.read())
        step("brand overlays + final encode")
        premium = bool(channel.get("premium"))
        items = []
        for it in cfg.get("branding", {}).get("logos", []):
            pos = it.get("position")
            entry = {**it, "path": str(ROOT / it["path"])}
            if pos == "top-right":          # "Made with Klipr" — global, top-right
                if premium:                 # premium removes the Klipr mark
                    continue
            elif pos == "bottom-right":     # channel logo — only on the real video
                if bottom_logo == "none":
                    continue
                if bottom_logo == "upload" and custom_logo is not None:
                    entry["path"] = str(custom_logo)
                entry["start"] = meta["intro_s"]
                entry["end"] = meta["body_end"]
            items.append(entry)
        branded = overlay_logos(raw, work / "branded.mp4", items)
        final = player_safe(branded, work / "final.mp4")
        result = {"work": work.name, "video_url": f"/api/video/{work.name}"}
        if make_shorts:
            step("creating Short (9:16)")
            make_short(final, work / "short.mp4")
            result["short_url"] = f"/api/short/{work.name}"
        return result

    return {"job_id": _run_job(job)}


@app.post("/api/thumbnail")
def api_thumbnail(payload: dict) -> dict:
    cfg = load_config()
    tcfg = cfg.get("thumbnail", {})
    work = WORK_ROOT / payload["work"]
    story = _script_from_dict(json.loads((work / "script.json").read_text()))
    th = story.thumbnail

    def job(step):
        step("rendering thumbnail")
        klipr = KliprClient_from_env()
        out = make_thumbnail(
            th.hook or story.title, work / f"thumb-{int(time.time())}",
            klipr=klipr, upload_and_sign=upload_and_sign,
            subject=th.subject or tcfg.get("subject", "dramatic subject, strong emotion"),
            banner=tcfg.get("banner_text", ""),
            mood=th.mood or tcfg.get("mood", "dramatic cinematic lighting, bold colors"),
            title_color=tcfg.get("title_color", "&H00FFFFFF"),
            accent_color=tcfg.get("accent_color", "&H000000FF"))
        # copy to a stable path the UI can fetch (cache-bust with ts query)
        dest = work / "thumbnail.png"
        dest.write_bytes(out.read_bytes())
        return {"thumb_url": f"/api/thumb/{work.name}?t={int(time.time())}"}

    return {"job_id": _run_job(job)}


@app.post("/api/upload")
def api_upload(payload: dict) -> dict:
    cfg = load_config()
    work_dir = WORK_ROOT / payload["work"]
    ch_file = work_dir / "channel.json"
    channel = json.loads(ch_file.read_text()) if ch_file.exists() else cfg.get("channel", {})
    language = channel.get("language", "hi")
    privacy = cfg.get("publish", {}).get("initial_privacy", "private")
    work = WORK_ROOT / payload["work"]
    story = _script_from_dict(json.loads((work / "script.json").read_text()))

    account_id = payload.get("account_id")

    def job(step):
        yt = yt_accounts.client_for(account_id) if account_id else youtube_for(language)
        if yt is None:
            raise RuntimeError("No YouTube channel selected. Connect a channel first.")
        desc = seo.build_description(story.title, story.title_translit,
                                     story.description, story.tags, channel)
        tags = seo.build_tags(story.tags, channel.get("seo_tags"))
        title = f"{story.title}{channel.get('title_suffix','')}"
        step("uploading to youtube")
        vid = yt.upload_from_file(work / "final.mp4", title, desc, tags=tags,
                                  privacy=privacy, language=language)
        thumb = work / "thumbnail.png"
        if thumb.exists():
            step("setting thumbnail")
            try:
                yt.set_thumbnail(vid, thumb)
            except Exception:  # noqa: BLE001
                pass
        return {"youtube_url": f"https://youtu.be/{vid}", "privacy": privacy}

    return {"job_id": _run_job(job)}


@app.get("/api/job/{jid}")
def api_job(jid: str) -> dict:
    j = _jobs.get(jid)
    if not j:
        raise HTTPException(404, "unknown job")
    return j


@app.get("/api/youtube/accounts")
def api_youtube_accounts() -> dict:
    return {"accounts": yt_accounts.list_accounts()}


@app.post("/api/youtube/connect")
def api_youtube_connect() -> dict:
    """Opens a browser for Google consent, then stores the channel."""
    return {"job_id": _run_job(lambda step: (step("waiting for Google consent…"),
                                             yt_accounts.connect())[1])}


@app.get("/api/video/{work}")
def api_video(work: str) -> FileResponse:
    p = WORK_ROOT / work / "final.mp4"
    if not p.exists():
        raise HTTPException(404, "not ready")
    return FileResponse(p, media_type="video/mp4")


@app.get("/api/thumb/{work}")
def api_thumb(work: str) -> FileResponse:
    p = WORK_ROOT / work / "thumbnail.png"
    if not p.exists():
        raise HTTPException(404, "not ready")
    return FileResponse(p, media_type="image/png")


@app.get("/api/download/{work}")
def api_download(work: str) -> FileResponse:
    p = WORK_ROOT / work / "final.mp4"
    if not p.exists():
        raise HTTPException(404, "not ready")
    return FileResponse(p, media_type="video/mp4", filename=f"{work}.mp4")


@app.get("/api/short/{work}")
def api_short(work: str) -> FileResponse:
    p = WORK_ROOT / work / "short.mp4"
    if not p.exists():
        raise HTTPException(404, "not ready")
    return FileResponse(p, media_type="video/mp4")


@app.get("/api/download_short/{work}")
def api_download_short(work: str) -> FileResponse:
    p = WORK_ROOT / work / "short.mp4"
    if not p.exists():
        raise HTTPException(404, "not ready")
    return FileResponse(p, media_type="video/mp4", filename=f"{work}-short.mp4")


def KliprClient_from_env() -> KliprClient:
    import os
    return KliprClient(os.environ["KLIPR_API_KEY"],
                       base_url=load_config().get("klipr", {}).get("base_url",
                                                                   "https://klipr.in/api/batch"))


if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.web.app:app", host="127.0.0.1", port=8000, reload=False)
