"""One-time: mint a YouTube upload refresh token for a channel.

Run this LOCALLY (it opens a browser) once per channel, signed in as that
channel's Google account. Paste the printed refresh token into Railway as
YOUTUBE_REFRESH_TOKEN_<LANG> (e.g. YOUTUBE_REFRESH_TOKEN_TELUGU).

Prereqs:
  - A Google Cloud OAuth 2.0 Client ID of type "Desktop app"
    (console.cloud.google.com → APIs & Services → Credentials).
  - YouTube Data API v3 enabled on that project.
  - pip install google-auth-oauthlib

Usage:
  export YOUTUBE_CLIENT_ID=...; export YOUTUBE_CLIENT_SECRET=...
  python scripts/youtube_auth.py
"""
from __future__ import annotations

import os

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main() -> None:
    cid = os.environ["YOUTUBE_CLIENT_ID"]
    secret = os.environ["YOUTUBE_CLIENT_SECRET"]
    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": cid,
                "client_secret": secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        },
        scopes=SCOPES,
    )
    # access_type=offline + prompt=consent forces Google to return a refresh
    # token even if this client was authorized before (otherwise it's None).
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    if not creds.refresh_token:
        print("\n  No refresh token returned. Revoke prior access at "
              "https://myaccount.google.com/permissions and re-run.\n")
        return
    print("\n  Refresh token (set as YOUTUBE_REFRESH_TOKEN_<LANG> on Railway):\n")
    print(f"    {creds.refresh_token}\n")


if __name__ == "__main__":
    main()
