# Automated Multi-Language YouTube Publishing System — Build Plan

> **Purpose of this document:** A self-contained spec that can be handed to Claude CLI to
> scaffold and build the system. It describes an automated pipeline that takes source
> videos, applies the channel watermark, generates localized (Hindi + Telugu) versions,
> clips them into Shorts via the **klipr.in API**, generates SEO, and publishes to YouTube.
>
> **The klipr.in API does not exist yet** — Section 6 defines the API contract we want it
> to expose. Until it exists, the `KliprClient` is built against this contract and backed by
> a local fallback (ffmpeg + a dubbing engine) so the rest of the system can run.

---

## 0. Ownership & Compliance Gate (read first)

This system assumes **all source content is owned by the operator**. Before any video enters
the pipeline it must pass an ownership gate:

- `source_manifest.json` must record, per file: `owner_confirmed: true`, original project
  file / proof of creation, and license.
- Files failing the gate are quarantined, never published.
- Localizing to a second language (Telugu) does **not** create new rights — YouTube Content ID
  matches **visuals**, so dubbed re-uploads of third-party footage are still claimable. The gate
  is the safeguard; do not bypass it.

---

## 1. Goal

Turn one owned source video into a multi-language, multi-format published set:

```
1 source video
  → Hindi master (watermarked)  → 1 long-form + 5–8 Shorts
  → Telugu master (watermarked) → 1 long-form + 5–8 Shorts
```

Run this at volume across a large back-catalog, with SEO and scheduling automated and an
analytics feedback loop to prioritize what works.

---

## 2. Tech Stack

| Concern | Choice | Notes |
|---|---|---|
| Language / runtime | Python 3.11+ | async where it helps (uploads, API calls) |
| Orchestration | Prefect *or* a simple job queue (Redis + RQ) | per-video DAG, retries, idempotency |
| Media processing | ffmpeg | watermark, mux, format conversion, fallback clipping |
| Clipping | **klipr.in API** (Section 6) | Shorts generation + captions |
| Dubbing / TTS | ElevenLabs Dubbing API (primary) | Hindi↔Telugu; Google Cloud TTS as fallback |
| Script / SEO / ideation | Claude API | one service reused across stages |
| Thumbnails | image-gen API + Pillow overlay | bright face + large Devanagari/Telugu word |
| Upload & scheduling | YouTube Data API v3 | OAuth2, resumable upload, scheduling |
| Analytics | YouTube Analytics API | feedback loop |
| Storage | local disk or S3-compatible | artifacts per stage, content-addressed |
| Config | `.env` + `config.yaml` | secrets out of source |
| State / metadata | SQLite (start) → Postgres (scale) | per-video status, idempotency keys |

---

## 3. Repository Layout

```
.
├── PLAN.md                      # this file
├── config.yaml                  # channels, languages, watermark, schedule rules
├── .env.example                 # API keys (never commit real .env)
├── source_manifest.json         # ownership gate records
├── assets/
│   ├── watermark/               # channel logo PNGs (per channel/language)
│   └── fonts/                    # Devanagari + Telugu fonts for thumbnails/captions
├── src/
│   ├── orchestrator.py          # builds & runs the per-video DAG
│   ├── stages/
│   │   ├── s00_ownership.py     # ownership gate
│   │   ├── s01_ideation.py      # topic/title (Claude)
│   │   ├── s02_localize.py      # translate + dub to target languages
│   │   ├── s03_watermark.py     # ffmpeg overlay of channel logo
│   │   ├── s04_assemble.py      # mux audio/video/BGM → master per language
│   │   ├── s05_clip.py          # KliprClient → Shorts + captions
│   │   ├── s06_seo.py           # title/desc/tags/chapters (Claude)
│   │   ├── s07_thumbnail.py     # generate + text overlay
│   │   ├── s08_publish.py       # YouTube Data API upload + schedule
│   │   └── s09_analytics.py     # pull metrics, write back to DB
│   ├── clients/
│   │   ├── klipr.py             # KliprClient (Section 6 contract + local fallback)
│   │   ├── dubbing.py           # ElevenLabs / Google dubbing wrapper
│   │   ├── claude.py            # Claude API wrapper (caching enabled)
│   │   └── youtube.py           # YouTube Data + Analytics wrapper
│   ├── models.py                # pydantic: Video, Language, Job, Artifact, PublishResult
│   ├── db.py                    # state store
│   └── ffmpeg_ops.py            # watermark, convert, mux helpers
├── tests/
└── scripts/
    └── ingest_folder.py         # scan a folder → source_manifest entries
```

---

## 4. Pipeline Stages (per source video)

Each stage is idempotent, writes a content-addressed artifact, and records status in the DB.
Re-running skips completed stages. Languages fan out after localization.

| # | Stage | Input | Output | Engine |
|---|---|---|---|---|
| 00 | Ownership gate | source file | pass/quarantine | local |
| 01 | Ideation/metadata | source + research patterns | canonical title, theme | Claude |
| 02 | **Localize** | source audio/script | Hindi + **Telugu** narration tracks | Dubbing API |
| 03 | **Watermark** | source video | watermarked video (per channel) | ffmpeg |
| 04 | Assemble | watermarked video + lang narration + BGM | `master.{lang}.mp4` | ffmpeg |
| 05 | Clip | `master.{lang}.mp4` | Shorts + captions per lang | **klipr API** |
| 06 | SEO | title/theme + lang | title, description, tags, chapters per lang | Claude |
| 07 | Thumbnail | theme + lang | thumbnail image per lang/format | image API |
| 08 | Publish | all of the above | YouTube video IDs, scheduled | YouTube API |
| 09 | Analytics | published IDs | metrics → DB → feeds stage 01 | YouTube API |

### 4a. Watermark stage (s03) — detail

- Channel logo PNG (transparent) from `assets/watermark/<channel>.png`.
- ffmpeg overlay, configurable position/opacity/scale via `config.yaml`:
  ```
  ffmpeg -i in.mp4 -i watermark.png \
    -filter_complex "[1]format=rgba,colorchannelmixer=aa=0.6,scale=iw*0.12:-1[wm];[0][wm]overlay=W-w-20:20" \
    -c:a copy out.mp4
  ```
- Per-language watermark variants supported (e.g., Telugu channel logo differs from Hindi).
- Applied **before** clipping so every Short inherits the watermark automatically.

### 4b. Localization stage (s02) — Telugu + Hindi — detail

- **Two sub-steps:** (1) transcript/translate source → target language text; (2) synthesize
  speech in target language.
- Preferred path: **ElevenLabs Dubbing API** (handles transcribe→translate→voice in one call,
  preserves timing). Fallback: Whisper transcript → Claude translate → Google/ElevenLabs TTS.
- Output is a time-aligned narration track per language; visuals are shared, so we only swap
  audio + captions.
- Caption (.srt) generated per language for burned-in or YouTube subtitle upload.
- **Telugu feasibility note:** klipr's role is clipping/captioning, *not* dubbing. The Telugu
  conversion happens here in s02 via the dubbing engine; klipr (s05) then clips the already-
  Telugu master. The klipr API spec (Section 6) still includes an optional `language` field and
  a dubbing endpoint in case klipr.in later offers it — see `/v1/dub`.

---

## 5. Data Model (pydantic sketch)

```python
class Language(str, Enum):
    HINDI = "hi"
    TELUGU = "te"

class SourceVideo(BaseModel):
    id: str
    path: Path
    owner_confirmed: bool
    title_canonical: str | None
    duration_s: float
    resolution: tuple[int, int]

class LocalizedMaster(BaseModel):
    source_id: str
    language: Language
    master_path: Path
    captions_path: Path
    watermarked: bool

class ClipSet(BaseModel):
    master_id: str
    language: Language
    shorts: list[Path]
    captions: list[Path]

class PublishResult(BaseModel):
    youtube_id: str
    language: Language
    fmt: Literal["long", "short"]
    scheduled_at: datetime
```

---

## 6. klipr.in API Contract (DOES NOT EXIST YET — design target)

We build `KliprClient` against this contract. Until klipr.in implements it, the client uses a
**local ffmpeg fallback** for clipping and the dubbing engine for `/v1/dub`. Swapping to the
real API later = config flag only.

**Base URL:** `https://api.klipr.in/v1`
**Auth:** `Authorization: Bearer <KLIPR_API_KEY>`
**Conventions:** JSON; long jobs are async (return `job_id`, poll or webhook).

### 6.1 `POST /v1/clip` — generate Shorts from a long video
```jsonc
// request
{
  "source_url": "https://.../master.te.mp4",   // or multipart upload
  "language": "te",                             // for caption/segmentation
  "target": { "aspect": "9:16", "max_duration_s": 60, "count": 8 },
  "captions": { "enabled": true, "style": "bold-center", "burn_in": true },
  "selection": "auto-highlights",               // or explicit timestamps
  "watermark": { "keep_source": true }          // we already watermarked upstream
}
// response
{ "job_id": "clip_abc123", "status": "queued" }
```

### 6.2 `GET /v1/jobs/{job_id}` — poll status
```jsonc
{ "job_id": "clip_abc123", "status": "done",
  "clips": [ { "url": "https://.../short_01.mp4", "start_s": 412, "end_s": 459,
               "captions_url": "https://.../short_01.srt" } ] }
```

### 6.3 `POST /v1/dub` — OPTIONAL dubbing (if klipr ever offers it)
```jsonc
// request
{ "source_url": "https://.../source.mp4", "from": "hi", "to": "te",
  "preserve_timing": true, "return": ["audio", "captions"] }
// response
{ "job_id": "dub_xyz789", "status": "queued" }
```
> If klipr does not implement `/v1/dub`, `KliprClient.dub()` transparently routes to the
> ElevenLabs/Google dubbing wrapper. The pipeline does not care which backend served it.

### 6.4 `POST /v1/webhooks` (optional) — register completion callback
```jsonc
{ "url": "https://our-host/hooks/klipr", "events": ["job.done", "job.failed"] }
```

### 6.5 Errors
Standard HTTP codes; body `{ "error": { "code": "...", "message": "..." } }`.
Client retries 5xx/429 with exponential backoff; surfaces 4xx to the operator.

### 6.6 `KliprClient` interface (Python)
```python
class KliprClient:
    def __init__(self, api_key: str | None, fallback: ClipFallback): ...
    async def clip(self, source: Path, language: Language,
                   count: int = 8, max_duration_s: int = 60) -> ClipSet: ...
    async def dub(self, source: Path, frm: Language,
                  to: Language) -> LocalizedMaster: ...   # routes to klipr or local
    async def _poll(self, job_id: str) -> dict: ...
```

---

## 7. YouTube Publishing (s08) — constraints to design around

- **Quota:** default ~10,000 units/day; an upload ≈1,600 units ⇒ **~6 uploads/day/project**.
  With Hindi+Telugu × (1 long + ~6 Shorts) per source = ~14 uploads/video, you will exceed one
  project's quota fast. Plan for: (a) quota increase request, and/or (b) multiple GCP projects /
  channels, and/or (c) a publish queue that paces uploads across days.
- **Auth:** OAuth2 per channel; store refresh tokens securely (one per channel/language).
- **Scheduling:** upload as `private` with `publishAt` for an even release cadence.
- **Spam policy:** mass templated uploads risk demonetization even when original. Keep a
  **quality gate** before s08 (LLM or human review of title/thumbnail/first 30s).
- Upload captions (.srt) per language; set `defaultAudioLanguage` and localized title/description.

---

## 8. Configuration (`config.yaml` sketch)

```yaml
channels:
  hindi:
    youtube_channel_id: "UC_xxx"
    watermark: assets/watermark/hindi.png
    language: hi
  telugu:
    youtube_channel_id: "UC_yyy"
    watermark: assets/watermark/telugu.png
    language: te
languages: [hi, te]
watermark:
  position: top-right
  opacity: 0.6
  scale: 0.12
clip:
  count: 8
  max_duration_s: 60
publish:
  uploads_per_day_per_channel: 6
  cadence_hours: 8
klipr:
  use_real_api: false        # flip to true when api.klipr.in is live
```

---

## 9. Build Order (for Claude CLI)

1. **Scaffold** repo layout (Section 3), `models.py`, `db.py`, config loading, `.env.example`.
2. **Ownership gate + ingest** (`scripts/ingest_folder.py`, `s00`). Prove nothing publishes
   without `owner_confirmed`.
3. **YouTube publish (s08)** — riskiest integration. Get one programmatic upload + schedule
   working end-to-end against a test channel. Wire quota-aware publish queue.
4. **SEO (s06)** via Claude — cheap, high-leverage.
5. **Watermark (s03)** ffmpeg overlay + tests.
6. **KliprClient (s05)** against the Section 6 contract, with ffmpeg fallback (`use_real_api: false`).
7. **Localization (s02)** — Hindi + Telugu via dubbing wrapper; captions per language.
8. **Assemble (s04)** + **Thumbnail (s07)**.
9. **Orchestrator** — wire the per-video DAG with language fan-out, retries, idempotency.
10. **Analytics (s09)** feedback loop, last.

---

## 10. Definition of Done (MVP)

- One owned source video → watermarked Hindi + Telugu masters → Shorts via KliprClient
  (fallback ok) → SEO + thumbnails → scheduled uploads to two channels, all from a single
  orchestrator run, idempotent and quota-aware.
```
