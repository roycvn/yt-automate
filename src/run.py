"""yta batch runner — delegates all media work to the klipr batch API.

No local ffmpeg: klipr handles dub / auto-clip / watermark / caption-burn.
yta orchestrates (which videos, which languages) and records results. This is
the entrypoint Railway runs on a cron.

Reads sources from source_manifest.json. Each entry that may be processed needs:
    {
      "id": "...",
      "owner_confirmed": true,
      "source_type": "youtube" | "upload",
      "source_url": "https://www.youtube.com/watch?v=..."   (youtube)
                    or a Firebase Storage https URL          (upload),
      "source_language": "hi"        (optional, defaults to config or "hi")
    }

For each owned source it dubs into every target language in config.languages
(skipping the source language) and writes artifacts/results.json.

Env:
    KLIPR_API_KEY   required — klipr_live_...
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .clients.klipr import KliprClient, KliprError
from .clients.youtube import YouTubeClient
from .config import load_config

ROOT = Path(__file__).resolve().parent.parent

# Map a target language to the env suffix for its channel refresh token,
# e.g. te -> YOUTUBE_REFRESH_TOKEN_TELUGU.
LANG_ENV = {"hi": "HINDI", "te": "TELUGU", "ta": "TAMIL"}


def load_sources() -> list[dict]:
    data = json.loads((ROOT / "source_manifest.json").read_text())
    return data.get("videos", [])


def youtube_client_for(lang: str) -> YouTubeClient | None:
    """Build a YouTubeClient for a language's channel, or None if not configured."""
    cid = os.environ.get("YOUTUBE_CLIENT_ID")
    secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    suffix = LANG_ENV.get(lang, lang.upper())
    refresh = os.environ.get(f"YOUTUBE_REFRESH_TOKEN_{suffix}")
    if not (cid and secret and refresh):
        return None
    return YouTubeClient(cid, secret, refresh)


async def process_video(client: KliprClient, video: dict, target_langs: list[str],
                        default_source_lang: str) -> dict:
    source_type = video.get("source_type", "youtube")
    source_url = video.get("source_url")
    source_lang = video.get("source_language", default_source_lang)
    result: dict = {"id": video.get("id"), "source_url": source_url, "dubs": {}}

    if not source_url:
        result["skipped"] = "no source_url"
        return result

    for lang in target_langs:
        if lang == source_lang:
            continue
        try:
            res = await client.dub_and_wait(
                source_url, target_language=lang,
                source_type=source_type, source_language=source_lang,
            )
            entry = {"status": res.status, "download_url": res.download_url}
            # Publish to YouTube if the channel for this language is configured.
            if res.status == "ready" and res.download_url:
                yt = youtube_client_for(lang)
                if yt is None:
                    entry["youtube"] = "skipped: no channel creds"
                else:
                    title = video.get("title") or f"{video.get('id')} [{lang}]"
                    try:
                        vid = yt.upload_from_url(
                            res.download_url, title=title,
                            description=video.get("description", ""),
                            tags=video.get("tags", []),
                            privacy=video.get("privacy", "private"),
                            language=lang,
                        )
                        entry["youtube"] = {"video_id": vid,
                                            "url": f"https://youtu.be/{vid}"}
                    except Exception as e:  # upload failures shouldn't kill the run
                        entry["youtube"] = {"error": str(e)[:300]}
            result["dubs"][lang] = entry
        except (KliprError, TimeoutError) as e:
            result["dubs"][lang] = {"status": "error", "error": str(e)}
    return result


async def main() -> None:
    cfg = load_config()
    api_key = os.environ.get("KLIPR_API_KEY", "")
    if not api_key:
        raise SystemExit("KLIPR_API_KEY is not set")

    client = KliprClient(api_key, base_url=cfg["klipr"]["base_url"])
    target_langs = [str(x) for x in cfg.get("languages", ["hi", "te"])]
    default_source_lang = "hi"

    sources = [v for v in load_sources() if v.get("owner_confirmed")]
    if not sources:
        print("No owner_confirmed sources to process.")
        return

    print(f"Processing {len(sources)} source(s) into languages {target_langs} ...")
    results = []
    for v in sources:
        print(f"  -> {v.get('id')} ({v.get('source_url')})")
        results.append(await process_video(client, v, target_langs, default_source_lang))

    out_dir = ROOT / cfg.get("storage", {}).get("artifacts_dir", "./artifacts").lstrip("./")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "results.json"
    out_file.write_text(json.dumps(
        {"run_at": datetime.now(timezone.utc).isoformat(), "results": results},
        ensure_ascii=False, indent=2,
    ))
    print(f"Done. Wrote {out_file}")
    # TODO: next stage — upload the dubbed/clipped outputs to YouTube
    # (YouTube Data API v3, OAuth refresh token per channel). See PLAN.md s08.


if __name__ == "__main__":
    asyncio.run(main())
