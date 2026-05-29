"""KliprClient — HTTP client for the real klipr batch API (github.com/roycvn/yts).

Endpoints (base = https://klipr.in/api/batch), all authenticated with
`Authorization: Bearer <KLIPR_API_KEY>`:

  POST /dub          {source_type, source_url|source_external_url, target_language,
                      source_language?}                       -> 202 {dub_id}
  POST /auto-clip    {source_type, source_url|source_external_url, ...}
                                                              -> 202 {job_id}
  POST /caption-burn {source_url, ass, source_mime?}          -> {output_key, download_url}
  POST /watermark    {source_url, filename?}                  -> streamed mp4 bytes
  GET  /jobs/{id}?kind=auto_clip|dub|caption_render          -> {job, download_url}

Sources are URLs, not local files: `source_type="youtube"` with a YouTube
`source_url`, or `source_type="upload"` with a Firebase Storage
`source_external_url`. Dub targets use short ISO codes (te, hi, ta, …).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx

SourceType = Literal["youtube", "upload"]
JobKind = Literal["auto_clip", "dub", "caption_render"]
TERMINAL = {"ready", "failed"}


@dataclass
class JobResult:
    id: str
    kind: JobKind
    status: str
    download_url: str | None
    error_message: str | None
    raw: dict


class KliprError(RuntimeError):
    pass


class KliprClient:
    def __init__(self, api_key: str, base_url: str = "https://klipr.in/api/batch",
                 timeout: float = 60.0):
        if not api_key:
            raise ValueError("KLIPR_API_KEY is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    @staticmethod
    def _source_fields(source_type: SourceType, source_url: str) -> dict:
        key = "source_url" if source_type == "youtube" else "source_external_url"
        return {"source_type": source_type, key: source_url}

    # ------------------------------------------------------------------ dub
    async def start_dub(self, source_url: str, target_language: str,
                        source_type: SourceType = "youtube",
                        source_language: str | None = None,
                        source_title: str | None = None) -> str:
        """Start a dub job; returns dub_id.

        Note: the klipr /dub route runs the pipeline synchronously and only
        responds once the dub is terminal (ready/failed), so this POST can take
        up to klipr's 300s maxDuration. We give it a 310s read timeout. A
        subsequent get_job() returns "ready" immediately.
        """
        payload = {**self._source_fields(source_type, source_url),
                   "target_language": target_language}
        if source_language:
            payload["source_language"] = source_language
        if source_title:
            payload["source_title"] = source_title
        timeout = httpx.Timeout(connect=15.0, read=310.0, write=60.0, pool=15.0)
        async with httpx.AsyncClient(timeout=timeout) as http:
            r = await http.post(f"{self.base_url}/dub", json=payload, headers=self._headers)
        self._raise_for(r)
        return r.json()["dub_id"]

    # ------------------------------------------------------------------ auto-clip
    async def start_auto_clip(self, source_url: str,
                              source_type: SourceType = "youtube",
                              source_title: str | None = None,
                              duration_seconds: float | None = None) -> str:
        """Start an auto-clip (Shorts) job; returns job_id."""
        payload = self._source_fields(source_type, source_url)
        if source_title:
            payload["source_title"] = source_title
        if duration_seconds:
            payload["duration_seconds"] = duration_seconds
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            r = await http.post(f"{self.base_url}/auto-clip", json=payload, headers=self._headers)
        self._raise_for(r)
        return r.json()["job_id"]

    # ------------------------------------------------------------------ caption burn
    async def caption_burn(self, source_url: str, ass: str,
                           source_mime: str = "video/mp4",
                           watermark: bool = True) -> JobResult:
        """Burn an ASS subtitle stream; synchronous, returns a download URL.
        Set watermark=False to skip klipr's automatic mark (we add our own)."""
        payload = {"source_url": source_url, "ass": ass, "source_mime": source_mime,
                   "watermark": watermark}
        async with httpx.AsyncClient(timeout=self.timeout * 5) as http:
            r = await http.post(f"{self.base_url}/caption-burn", json=payload, headers=self._headers)
        self._raise_for(r)
        body = r.json()
        return JobResult(id=body.get("output_key", ""), kind="caption_render",
                         status="ready", download_url=body.get("download_url"),
                         error_message=None, raw=body)

    # ------------------------------------------------------------------ watermark
    async def watermark(self, source_url: str, dest: Path,
                        filename: str | None = None) -> Path:
        """Stream a watermarked MP4 to `dest`. source_url must be an R2/Firebase URL."""
        payload = {"source_url": source_url}
        if filename:
            payload["filename"] = filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=self.timeout * 5) as http:
            async with http.stream("POST", f"{self.base_url}/watermark",
                                   json=payload, headers=self._headers) as r:
                if r.status_code >= 400:
                    await r.aread()
                    self._raise_for(r)
                with open(dest, "wb") as f:
                    async for chunk in r.aiter_bytes():
                        f.write(chunk)
        return dest

    # ------------------------------------------------------------------ jobs
    async def get_job(self, job_id: str, kind: JobKind) -> JobResult:
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            r = await http.get(f"{self.base_url}/jobs/{job_id}",
                               params={"kind": kind}, headers=self._headers)
        self._raise_for(r)
        body = r.json()
        job = body.get("job", {})
        return JobResult(id=job_id, kind=kind, status=job.get("status", "unknown"),
                         download_url=body.get("download_url"),
                         error_message=job.get("error_message"), raw=body)

    async def wait_for_job(self, job_id: str, kind: JobKind,
                           interval: float = 10.0, max_wait_s: float = 1800.0) -> JobResult:
        """Poll until the job reaches a terminal state; raise on failure/timeout."""
        waited = 0.0
        while waited < max_wait_s:
            res = await self.get_job(job_id, kind)
            if res.status == "ready":
                return res
            if res.status == "failed":
                raise KliprError(f"{kind} job {job_id} failed: {res.error_message}")
            await asyncio.sleep(interval)
            waited += interval
        raise TimeoutError(f"{kind} job {job_id} did not finish in {max_wait_s}s")

    # ------------------------------------------------------------------ convenience
    async def dub_and_wait(self, source_url: str, target_language: str,
                           source_type: SourceType = "youtube",
                           source_language: str | None = None,
                           **poll) -> JobResult:
        job_id = await self.start_dub(source_url, target_language, source_type, source_language)
        return await self.wait_for_job(job_id, "dub", **poll)

    async def auto_clip_and_wait(self, source_url: str,
                                 source_type: SourceType = "youtube", **poll) -> JobResult:
        job_id = await self.start_auto_clip(source_url, source_type)
        return await self.wait_for_job(job_id, "auto_clip", **poll)

    # ------------------------------------------------------------------ errors
    @staticmethod
    def _raise_for(r: httpx.Response) -> None:
        if r.status_code < 400:
            return
        try:
            body = r.json()
        except Exception:
            body = {"error": r.text[:300]}
        raise KliprError(f"klipr {r.request.method} {r.request.url.path} "
                         f"-> {r.status_code}: {body}")
