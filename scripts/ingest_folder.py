"""Scan a folder of videos and emit/merge source_manifest.json entries.

All entries default to owner_confirmed=false — you must explicitly confirm ownership
before anything publishes.

Usage:
    python scripts/ingest_folder.py "/path/to/folder" [source_manifest.json]
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import ffmpeg_ops  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    folder = Path(sys.argv[1])
    manifest_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("source_manifest.json")

    existing = {}
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text())
        existing = {v["path"]: v for v in data.get("videos", [])}

    videos = list(existing.values())
    for f in sorted(folder.glob("*.mp4")):
        if str(f) in existing:
            continue
        try:
            dur = ffmpeg_ops.probe_duration(f)
            w, h = ffmpeg_ops.probe_resolution(f)
        except Exception:
            dur, w, h = None, None, None
        videos.append({
            "id": f"vid-{uuid.uuid4().hex[:8]}",
            "path": str(f),
            "owner_confirmed": False,
            "proof": "",
            "license": "",
            "duration_s": dur,
            "resolution": [w, h] if w else None,
        })

    manifest_path.write_text(json.dumps({"videos": videos}, ensure_ascii=False, indent=2))
    print(f"Wrote {len(videos)} entries to {manifest_path} "
          f"(all new entries owner_confirmed=false — confirm before publishing)")


if __name__ == "__main__":
    main()
