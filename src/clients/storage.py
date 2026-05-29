"""Supabase Storage upload — hand klipr a signed URL for a locally-rendered file.

Uses the service-role key (server-side only). Uploads to the reels-output
bucket (already video/mp4-capable) and returns a signed URL on a *.supabase.co
host, which klipr's batch API allows as a source.

Env: NEXT_PUBLIC_SUPABASE_URL (or SUPABASE_URL), SUPABASE_SERVICE_ROLE_KEY
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx

DEFAULT_BUCKET = "reels-output"


def _base() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL") or os.environ["NEXT_PUBLIC_SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return url.rstrip("/"), key


def upload_and_sign(path: Path, key: str, bucket: str = DEFAULT_BUCKET,
                    expires_s: int = 3600, content_type: str = "video/mp4") -> str:
    """Upload a local file and return a signed URL valid for expires_s seconds."""
    base, srv = _base()
    headers = {"Authorization": f"Bearer {srv}", "apikey": srv}
    with httpx.Client(timeout=300.0) as http:
        # Upsert the object.
        up = http.post(
            f"{base}/storage/v1/object/{bucket}/{key}",
            headers={**headers, "content-type": content_type, "x-upsert": "true"},
            content=path.read_bytes(),
        )
        up.raise_for_status()
        # Sign it.
        sign = http.post(
            f"{base}/storage/v1/object/sign/{bucket}/{key}",
            headers={**headers, "content-type": "application/json"},
            json={"expiresIn": expires_s},
        )
        sign.raise_for_status()
        signed_path = sign.json()["signedURL"]
    return f"{base}/storage/v1{signed_path}"
