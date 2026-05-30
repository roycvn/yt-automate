# Deploy yta as a Klipr worker (Railway)

End-state: a normal user opens `klipr.in/dashboard/yt-automate`, clicks
**Generate**, and a finished video comes back ~6 min later. The Klipr UI
talks to a hosted yta worker over HTTPS — the user never sees Railway,
Python, or ffmpeg.

## 1. Push the repo

The deploy assets (`Dockerfile`, `railway.json`, `.dockerignore`) are
already committed. From this directory:

```
git push origin main
```

## 2. Create a Railway service

1. Go to https://railway.app/new
2. **Deploy from GitHub Repo** → pick this repo (`yt-automate`).
3. Railway detects `railway.json` + `Dockerfile` automatically.
4. **Settings → Networking → Generate Domain**. Save the URL — looks
   like `https://yta-production-xxxx.up.railway.app`.

## 3. Environment variables (Service → Variables)

Required (paste from your local `.env`):

```
KLIPR_API_KEY=klipr_live_...
ANTHROPIC_API_KEY=sk-ant-...        # script generation
REPLICATE_API_TOKEN=r8_...          # Flux images
SARVAM_API_KEY=...                  # Indian-language TTS
NEXT_PUBLIC_SUPABASE_URL=https://...supabase.co
SUPABASE_SERVICE_ROLE_KEY=...       # to upload to reels-output
WORKER_TOKEN=<generate-a-long-random-string>
```

`WORKER_TOKEN` gates every `/api/*` route — only callers presenting the
matching `Authorization: Bearer <token>` header are accepted. Paste the
same value into Klipr's env (next step).

Optional (only if this worker should also upload to YouTube directly —
otherwise Klipr handles that side):

```
YOUTUBE_CLIENT_ID=...
YOUTUBE_CLIENT_SECRET=...
YOUTUBE_REFRESH_TOKEN_HINDI=...
YOUTUBE_REFRESH_TOKEN_TELUGU=...
```

## 4. Wire Klipr → worker

In the Klipr Vercel project (Settings → Environment Variables) add:

```
YTA_WORKER_URL=https://yta-production-xxxx.up.railway.app
YTA_WORKER_TOKEN=<same value as WORKER_TOKEN above>
```

Redeploy Klipr so the new env takes effect.

## 5. Smoke-test

```
curl https://yta-production-xxxx.up.railway.app/
```

Should return the bundled studio HTML (the worker also serves the
internal UI at `/` so you can test directly).

```
curl -H "Authorization: Bearer $WORKER_TOKEN" \
     https://yta-production-xxxx.up.railway.app/api/channels
```

Should return JSON with `profiles`, `lang_defaults`, etc.

Now open `klipr.in/dashboard/yt-automate`, fill the form, click
**Generate**. The Klipr UI POSTs to the Railway worker, polls for
status, and shows the finished video — no other moving parts.

## Cost expectations

Railway free tier covers ~500h/mo of a small container — fine for
testing. For real traffic upgrade to the $5/mo Hobby plan and pin the
service to 1 GB RAM / 1 vCPU. Per-video API cost (Claude haiku + Flux
schnell + Sarvam bulbul) lands around **$0.10**.

## Scaling notes

This single worker handles one video at a time per `ThreadPoolExecutor`
worker (configured to 2 in `src/web/app.py`). For >2 concurrent users,
either bump that worker count (if memory allows) or run multiple
Railway replicas behind the same domain — the FastAPI server is
stateless apart from the in-memory `_jobs` dict; jobs lose status if
the container restarts, so for production you'll eventually want to
move that into Supabase. Not blocking for v1.
