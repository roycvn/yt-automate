"""Top-level: produce ONE finished, SEO-optimized, thumbnailed video and
(optionally) upload it to YouTube. Fully automated — no manual work.

script -> images -> voice -> finish (intro/outro + drone) -> klipr captions
       -> thumbnail -> SEO metadata -> [YouTube upload + thumbnail set]

Env: ANTHROPIC_API_KEY, REPLICATE_API_TOKEN, SARVAM_API_KEY, KLIPR_API_KEY,
     NEXT_PUBLIC_SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY,
     (upload) YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN_<LANG>
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

from .generate.script import generate_script, StoryScript, Scene, ThumbnailConcept
from .generate.images import generate_scene_images
from .generate.videos import generate_scene_videos
from .generate.voice import synthesize_scenes
from .generate.finishing import build_finished_skeleton, player_safe, overlay_logos
from .config import load_config
from .generate.thumbnail import make_thumbnail
from .generate import seo
from .clients.klipr import KliprClient
from .clients.storage import upload_and_sign
from .clients.youtube import YouTubeClient

ROOT = Path(__file__).resolve().parent.parent
LANG_ENV = {"hi": "HINDI", "te": "TELUGU", "ta": "TAMIL"}
OUTRO = "TheStoryBoardz — सब्सक्राइब करें 🔔"


def youtube_for(lang: str) -> YouTubeClient | None:
    cid = os.environ.get("YOUTUBE_CLIENT_ID")
    sec = os.environ.get("YOUTUBE_CLIENT_SECRET")
    tok = os.environ.get(f"YOUTUBE_REFRESH_TOKEN_{LANG_ENV.get(lang, lang.upper())}")
    return YouTubeClient(cid, sec, tok) if (cid and sec and tok) else None


def load_or_generate_script(out: Path, reuse: Path | None, channel: dict) -> StoryScript:
    if reuse and reuse.exists():
        d = json.loads(reuse.read_text())
        th = d.get("thumbnail") or {}
        return StoryScript(
            d.get("title") or d.get("title_hi", ""), d.get("title_translit", ""),
            d["description"], d["tags"],
            ThumbnailConcept(th.get("subject", ""), th.get("hook", ""), th.get("mood", "")),
            [Scene(s["id"], s.get("narration") or s.get("narration_hi", ""),
                   s["image_prompt"], s.get("duration_seconds"))
             for s in d["scenes"]])
    s = generate_script(channel=channel)
    (out / "script.json").write_text(json.dumps(s.to_dict(), ensure_ascii=False, indent=2))
    return s


def produce(reuse_script: Path | None = None,
            privacy: str = "private", upload: bool = True) -> dict:
    cfg = load_config()
    channel = cfg.get("channel", {})
    language = channel.get("language", "hi")
    speaker = channel.get("voice_speaker", "anushka")
    outro = channel.get("outro_text", f"{channel.get('name', 'Subscribe')} 🔔")
    title_suffix = channel.get("title_suffix", "")

    work = ROOT / "artifacts" / f"produce-{int(time.time())}"
    work.mkdir(parents=True, exist_ok=True)
    klipr = KliprClient(os.environ["KLIPR_API_KEY"])

    script = load_or_generate_script(work, reuse_script, channel)
    print(f"script: {script.title} ({len(script.scenes)} scenes)")

    # Generation mode: "image" (Flux still + ken-burns zoom, default) or
    # "video" (fal.ai AI motion clips per scene, in the configured style).
    gen = cfg.get("generation", {})
    mode = gen.get("mode", "image")
    style = gen.get("style", "2d")
    clip_seconds = int(gen.get("clip_seconds", 5))

    images: list[Path] = []
    scene_videos: list[Path] | None = None
    if mode == "video":
        scene_videos = generate_scene_videos(
            script.scenes, work / "videos", style=style,
            aspect_ratio="16:9", duration_seconds=clip_seconds)
        print(f"scene videos done ({style})")
    else:
        images = generate_scene_images(script.scenes, work / "images")
        print("images done")
    audios = synthesize_scenes(script.scenes, work / "audio",
                               language=language, speaker=speaker)
    print("voice done")

    finished, ass, meta = build_finished_skeleton(
        script.scenes, images, audios, work / "finish",
        intro_title=script.title, outro_text=outro, language=language,
        scene_videos=scene_videos)
    url = upload_and_sign(finished, f"produce/{work.name}.mp4")
    res = asyncio.run(klipr.caption_burn(url, ass, watermark=False))
    import httpx
    raw = work / "captioned.mp4"
    with httpx.stream("GET", res.download_url, timeout=600) as r:
        r.raise_for_status()
        raw.write_bytes(r.read())
    # Brand overlays: Klipr top-right (unless premium); channel logo only on the
    # real video (windowed between intro end and body end).
    premium = bool(channel.get("premium"))
    items = []
    for it in cfg.get("branding", {}).get("logos", []):
        pos = it.get("position")
        entry = {**it, "path": str(ROOT / it["path"])}
        if pos == "top-right" and premium:
            continue
        if pos == "bottom-right":
            entry["start"] = meta["intro_s"]
            entry["end"] = meta["body_end"]
        items.append(entry)
    branded = overlay_logos(raw, work / "branded.mp4", items)
    final = player_safe(branded, work / "final.mp4")
    print("final video:", final)

    # Thumbnail: per-video concept from the script (dynamic), with config fallback.
    tcfg = cfg.get("thumbnail", {})
    th = script.thumbnail
    thumb = make_thumbnail(
        th.hook or script.title, work / "thumb", klipr=klipr, upload_and_sign=upload_and_sign,
        subject=th.subject or tcfg.get("subject", "dramatic subject, strong emotion"),
        banner=tcfg.get("banner_text", ""),
        mood=th.mood or tcfg.get("mood", "dramatic cinematic lighting, bold colors"),
        title_color=tcfg.get("title_color", "&H00FFFFFF"),
        accent_color=tcfg.get("accent_color", "&H000000FF"),
        language=language)
    print("thumbnail:", thumb)

    description = seo.build_description(script.title, script.title_translit,
                                        script.description, script.tags, channel)
    tags = seo.build_tags(script.tags, channel.get("seo_tags"))
    meta = {"title": f"{script.title}{title_suffix}",
            "description": description, "tags": tags,
            "final": str(final), "thumbnail": str(thumb)}
    (work / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    result = {"work": str(work), **meta, "youtube": None}
    if upload:
        yt = youtube_for(language)
        if yt is None:
            result["youtube"] = "skipped: no channel creds (set YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN_<LANG>)"
        else:
            vid = yt.upload_from_file(final, meta["title"], description,
                                      tags=tags, privacy=privacy, language=language)
            try:
                yt.set_thumbnail(vid, thumb)
            except Exception as e:
                result["thumbnail_error"] = str(e)[:200]
            result["youtube"] = {"video_id": vid, "url": f"https://youtu.be/{vid}"}
    print("RESULT:", json.dumps(result, ensure_ascii=False)[:300])
    return result


if __name__ == "__main__":
    import sys
    reuse = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    produce(reuse_script=reuse)
