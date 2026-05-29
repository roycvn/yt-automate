"""Publish an already-produced video to YouTube (no re-rendering).

Reads metadata.json + final.mp4 + thumbnail from a produce-* work dir and
uploads to the channel for the configured language. Credentials are loaded
from yta/.env (gitignored) via src.config — never passed on the command line.

Usage:
    # put YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET / YOUTUBE_REFRESH_TOKEN_<LANG>
    # into yta/.env first, then:
    python scripts/publish.py                 # newest produce-* dir
    python scripts/publish.py artifacts/produce-1780059958
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import load_config  # noqa: E402  (also loads .env)
from src.produce import youtube_for  # noqa: E402


def latest_produce_dir() -> Path | None:
    dirs = sorted((ROOT / "artifacts").glob("produce-*"), reverse=True)
    return dirs[0] if dirs else None


def main() -> None:
    work = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_produce_dir()
    if not work or not (work / "metadata.json").exists():
        raise SystemExit(f"No metadata.json found in {work}")

    cfg = load_config()
    language = cfg.get("channel", {}).get("language", "hi")
    privacy = cfg.get("publish", {}).get("initial_privacy", "private")

    meta = json.loads((work / "metadata.json").read_text())
    final = work / "final.mp4"
    thumb = work / "thumb" / "thumbnail.png"

    yt = youtube_for(language)
    if yt is None:
        raise SystemExit(
            "YouTube creds missing. Put YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, "
            f"and YOUTUBE_REFRESH_TOKEN_{language.upper()} in yta/.env")

    print(f"Uploading {final.name} -> '{meta['title']}' (privacy={privacy}) ...")
    vid = yt.upload_from_file(final, meta["title"], meta["description"],
                             tags=meta.get("tags", []), privacy=privacy, language=language)
    url = f"https://youtu.be/{vid}"
    print("UPLOADED:", url)
    if thumb.exists():
        try:
            yt.set_thumbnail(vid, thumb)
            print("thumbnail set")
        except Exception as e:
            print("thumbnail set failed:", str(e)[:200])
    print("DONE:", url)


if __name__ == "__main__":
    main()
