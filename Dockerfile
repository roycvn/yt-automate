# yta batch runner. No ffmpeg: all media work is delegated to the klipr API,
# so this stays a small pure-Python image.
FROM python:3.12-slim

WORKDIR /app

# Install deps first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code.
COPY . .

# Runs once and exits — Railway invokes it on a cron schedule (railway.json).
CMD ["python", "-m", "src.run"]
