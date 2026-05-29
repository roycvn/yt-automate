# yt-automate

A **niche-agnostic** automated YouTube content engine. Define a channel in
`config.yaml`, and it generates complete original videos end to end:

```
script (Claude) → images (Flux) → narration (Sarvam) → assemble (ffmpeg)
   → intro/outro + ambient bed → captions (klipr) → brand logos
   → contextual thumbnail → SEO metadata → YouTube upload
```

Swap the `channel:` profile and the same engine produces for **any** niche —
horror, cooking, motivation, tech, history, kids. Each video's thumbnail
concept (subject + hook + mood) is generated to fit *that* video.

It also localizes/dubs to other languages (e.g. Telugu) and clips Shorts via
the **klipr batch API**.

## Configure
Everything lives in `config.yaml`:
- `channel:` — name, language, niche, tone, art style, voice, scenes, outro.
- `branding.logos[]` — logo files + positions (top-right, bottom-right, …).
- `thumbnail:` — banner text, colors (subject/mood come per-video from Claude).

## Run
```bash
python -m src.produce          # generate + (if creds set) upload one video
python -m src.run              # light path: dub owned sources via klipr
```

## Deploy (Railway — two services from this repo)
1. **Generator** (heavy, needs ffmpeg): build from `Dockerfile.generator`
   (`railway.generator.json`), cron-scheduled — runs `python -m src.produce`.
2. **Light cron** (no ffmpeg): build from `Dockerfile` (`railway.json`) —
   runs `python -m src.run` for klipr-delegated dubbing of owned sources.

### Required env vars
`ANTHROPIC_API_KEY`, `REPLICATE_API_TOKEN`, `SARVAM_API_KEY`, `KLIPR_API_KEY`,
`NEXT_PUBLIC_SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and for upload:
`YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN_<LANG>`
(mint with `scripts/youtube_auth.py`).

See `PLAN.md` for the full architecture.
