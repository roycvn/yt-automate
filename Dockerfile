# yta — Channel-automation worker. Deployed on Railway (or any container
# host). Exposes the FastAPI surface in src/web/app.py; klipr's
# /dashboard/yt-automate page POSTs jobs here and polls /api/job/{id}.
#
# Heavy dependencies pinned at the OS level:
#   - ffmpeg + libass (caption shaping is delegated to klipr; local
#     assembly / intro / overlays still need ffmpeg)
#   - fonts-noto for any local Pillow text fallback (Indic + CJK)
#
# The local thumbnail engine (src/generate/thumbnail_render.py) needs Pillow with
# raqm for Indic shaping. Pillow's manylinux wheels bundle libraqm (>=8.2.0), so
# `pip install Pillow` here is enough; verify post-deploy via GET /api/thumb-options
# ("raqm": true). If it ever reports false, build Pillow from source against
# libraqm-dev — make_thumbnail falls back to klipr/libass until then.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        fonts-noto \
        fonts-noto-cjk \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps first so the docker cache survives source edits.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Source + assets needed at runtime.
COPY src ./src
COPY config.yaml ./config.yaml
COPY assets ./assets

# Railway injects PORT; default for `docker run` locally.
ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/" >/dev/null || exit 1

CMD ["sh", "-c", "uvicorn src.web.app:app --host 0.0.0.0 --port ${PORT}"]
