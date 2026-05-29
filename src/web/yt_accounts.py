"""Multi-channel YouTube account store + OAuth connect.

Lets the UI authorize ANY number of YouTube channels/accounts. Each connect
runs the Google consent flow (opens a browser), captures a refresh token, reads
the channel's title/id, and stores it in artifacts/youtube_accounts.json. Upload
then targets a chosen connected account — no .env editing, multiple channels.

Env: YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..clients.youtube import YouTubeClient

ROOT = Path(__file__).resolve().parent.parent.parent
STORE = ROOT / "artifacts" / "youtube_accounts.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def _load() -> list[dict]:
    if STORE.exists():
        return json.loads(STORE.read_text()).get("accounts", [])
    return []


def _save(accounts: list[dict]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps({"accounts": accounts}, ensure_ascii=False, indent=2))


def list_accounts() -> list[dict]:
    """Public-safe list (no refresh tokens)."""
    return [{"id": a["channel_id"], "title": a["title"]} for a in _load()]


def _creds() -> tuple[str, str]:
    cid = os.environ.get("YOUTUBE_CLIENT_ID")
    sec = os.environ.get("YOUTUBE_CLIENT_SECRET")
    if not (cid and sec):
        raise RuntimeError("Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET (.env).")
    return cid, sec


def client_for(channel_id: str) -> YouTubeClient | None:
    cid, sec = _creds()
    for a in _load():
        if a["channel_id"] == channel_id:
            return YouTubeClient(cid, sec, a["refresh_token"])
    return None


def connect() -> dict:
    """Run the OAuth consent flow (opens a browser), store the channel, return it."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    cid, sec = _creds()
    flow = InstalledAppFlow.from_client_config(
        {"installed": {"client_id": cid, "client_secret": sec,
                       "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                       "token_uri": "https://oauth2.googleapis.com/token",
                       "redirect_uris": ["http://localhost"]}},
        scopes=SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    if not creds.refresh_token:
        raise RuntimeError("No refresh token returned — revoke prior access and retry.")

    svc = build("youtube", "v3", credentials=Credentials(
        token=creds.token, refresh_token=creds.refresh_token,
        client_id=cid, client_secret=sec,
        token_uri="https://oauth2.googleapis.com/token", scopes=SCOPES),
        cache_discovery=False)
    resp = svc.channels().list(part="snippet", mine=True).execute()
    items = resp.get("items", [])
    if not items:
        raise RuntimeError("No channel found for this account.")
    ch = items[0]
    account = {"channel_id": ch["id"], "title": ch["snippet"]["title"],
               "refresh_token": creds.refresh_token}

    accounts = [a for a in _load() if a["channel_id"] != ch["id"]]
    accounts.append(account)
    _save(accounts)
    return {"id": ch["id"], "title": ch["snippet"]["title"]}
