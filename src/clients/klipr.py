"""KliprClient — built against the (not-yet-existing) klipr.in API contract in PLAN.md §6.

When config klipr.use_real_api is False, clipping falls back to local ffmpeg and dubbing
routes to the dubbing engine. Flip the flag once api.klipr.in is live; no other code changes.
"""
from __future__ import annotations

from pathlib import Path

import httpx

from ..models import ClipSet, Language, LocalizedMaster
from .. import ffmpeg_ops


class KliprClient:
    def __init__(self, api_key: str | None, base_url: str, use_real_api: bool,
                 dubbing_client=None, artifacts_dir: Path = Path("./artifacts")):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.use_real_api = use_real_api
        self.dubbing = dubbing_client
        self.artifacts_dir = artifacts_dir

    # ------------------------------------------------------------------ clip
    async def clip(self, source: Path, language: Language, master_id: str,
                   count: int = 8, max_duration_s: int = 60) -> ClipSet:
        if self.use_real_api:
            return await self._clip_remote(source, language, master_id, count, max_duration_s)
        return self._clip_local(source, language, master_id, count, max_duration_s)

    async def _clip_remote(self, source, language, master_id, count, max_duration_s) -> ClipSet:
        # POST /v1/clip -> {job_id}; poll GET /v1/jobs/{id}; download clips. (PLAN.md §6.1-6.2)
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "language": language.value,
            "target": {"aspect": "9:16", "max_duration_s": max_duration_s, "count": count},
            "captions": {"enabled": True, "burn_in": True},
            "selection": "auto-highlights",
        }
        async with httpx.AsyncClient(timeout=60) as http:
            # TODO: multipart upload of `source` or pre-signed URL exchange
            r = await http.post(f"{self.base_url}/clip", json=payload, headers=headers)
            r.raise_for_status()
            job_id = r.json()["job_id"]
            result = await self._poll(http, job_id, headers)
        shorts, caps = [], []
        for c in result.get("clips", []):
            shorts.append(Path(c["url"]))            # TODO: download to artifacts_dir
            if c.get("captions_url"):
                caps.append(Path(c["captions_url"]))
        return ClipSet(master_id=master_id, language=language, shorts=shorts, captions=caps)

    def _clip_local(self, source, language, master_id, count, max_duration_s) -> ClipSet:
        dur = ffmpeg_ops.probe_duration(source)
        out_dir = self.artifacts_dir / master_id / "shorts"
        out_dir.mkdir(parents=True, exist_ok=True)
        shorts = []
        # naive even segmentation as fallback; real klipr does highlight detection
        step = max(dur / count, max_duration_s)
        t = 0.0
        i = 0
        while t < dur and i < count:
            end = min(t + max_duration_s, dur)
            out = out_dir / f"short_{i:02d}.mp4"
            ffmpeg_ops.clip_segment(source, t, end, out, vertical=True)
            shorts.append(out)
            t += step
            i += 1
        return ClipSet(master_id=master_id, language=language, shorts=shorts, captions=[])

    # ------------------------------------------------------------------ dub
    async def dub(self, source: Path, frm: Language, to: Language,
                  source_id: str) -> LocalizedMaster:
        if self.use_real_api:
            return await self._dub_remote(source, frm, to, source_id)
        if self.dubbing is None:
            raise RuntimeError("No dubbing backend configured (klipr disabled, dubbing client missing)")
        return await self.dubbing.dub(source, frm, to, source_id)

    async def _dub_remote(self, source, frm, to, source_id) -> LocalizedMaster:
        # POST /v1/dub (PLAN.md §6.3) — optional; only if klipr.in implements it.
        raise NotImplementedError("klipr /v1/dub not implemented; keep use_real_api off for dubbing")

    # ------------------------------------------------------------------ poll
    async def _poll(self, http: httpx.AsyncClient, job_id: str, headers: dict,
                    interval: float = 3.0, max_tries: int = 200) -> dict:
        import asyncio
        for _ in range(max_tries):
            r = await http.get(f"{self.base_url}/jobs/{job_id}", headers=headers)
            r.raise_for_status()
            data = r.json()
            if data["status"] == "done":
                return data
            if data["status"] == "failed":
                raise RuntimeError(f"klipr job {job_id} failed")
            await asyncio.sleep(interval)
        raise TimeoutError(f"klipr job {job_id} did not finish")
