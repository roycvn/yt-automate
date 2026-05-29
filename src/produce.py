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

from .generate.script import generate_script, StoryScript, Scene
from .generate.images import generate_scene_images
from .generate.voice import synthesize_scenes
from .generate.finishing import build_finished_skeleton, player_safe, add_logos
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


def load_or_generate_script(out: Path, reuse: Path | None) -> StoryScript:
    if reuse and reuse.exists():
        d = json.loads(reuse.read_text())
        return StoryScript(d["title_hi"], d["title_translit"], d["description"],
                           d["tags"], [Scene(**s) for s in d["scenes"]])
    s = generate_script()
    (out / "script.json").write_text(json.dumps(s.to_dict(), ensure_ascii=False, indent=2))
    return s


def produce(language: str = "hi", reuse_script: Path | None = None,
            privacy: str = "private", upload: bool = True) -> dict:
    work = ROOT / "artifacts" / f"produce-{int(time.time())}"
    work.mkdir(parents=True, exist_ok=True)
    klipr = KliprClient(os.environ["KLIPR_API_KEY"])

    script = load_or_generate_script(work, reuse_script)
    print(f"script: {script.title_hi} ({len(script.scenes)} scenes)")

    images = generate_scene_images(script.scenes, work / "images")
    audios = synthesize_scenes(script.scenes, work / "audio", language=language)
    print("images + voice done")

    finished, ass = build_finished_skeleton(
        script.scenes, images, audios, work / "finish",
        intro_title=script.title_hi, outro_text=OUTRO)
    url = upload_and_sign(finished, f"produce/{work.name}.mp4")
    res = asyncio.run(klipr.caption_burn(url, ass, watermark=False))
    import httpx
    raw = work / "captioned.mp4"
    with httpx.stream("GET", res.download_url, timeout=600) as r:
        r.raise_for_status()
        raw.write_bytes(r.read())
    # Brand overlays: Klipr logo top-right, TheStoryBoardz logo bottom-right.
    branded = add_logos(raw, work / "branded.mp4",
                        tr_logo=ROOT / "assets" / "logos" / "klipr.png",
                        br_logo=ROOT / "assets" / "logo_trans_white_letter.png")
    final = player_safe(branded, work / "final.mp4")
    print("final video:", final)

    thumb = make_thumbnail(script.title_hi, work / "thumb",
                           klipr=klipr, upload_and_sign=upload_and_sign)
    print("thumbnail:", thumb)

    description = seo.build_description(script.title_hi, script.title_translit,
                                        script.description, script.tags, language)
    tags = seo.build_tags(script.tags)
    meta = {"title": f"{script.title_hi} | Horror Story | TheStoryBoardz",
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
