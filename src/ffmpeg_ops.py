from __future__ import annotations

import subprocess
from pathlib import Path

_POSITIONS = {
    "top-left": "20:20",
    "top-right": "W-w-20:20",
    "bottom-left": "20:H-h-20",
    "bottom-right": "W-w-20:H-h-20",
}


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return float(out)


def probe_resolution(path: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    w, h = out.split("x")
    return int(w), int(h)


def apply_watermark(src: Path, logo: Path, out: Path,
                    position: str = "top-right", opacity: float = 0.6,
                    scale: float = 0.12) -> Path:
    overlay = _POSITIONS.get(position, _POSITIONS["top-right"])
    filt = (
        f"[1]format=rgba,colorchannelmixer=aa={opacity},"
        f"scale=iw*{scale}:-1[wm];[0][wm]overlay={overlay}"
    )
    _run(["ffmpeg", "-y", "-i", str(src), "-i", str(logo),
          "-filter_complex", filt, "-c:a", "copy", str(out)])
    return out


def replace_audio(video: Path, audio: Path, out: Path) -> Path:
    _run(["ffmpeg", "-y", "-i", str(video), "-i", str(audio),
          "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-shortest", str(out)])
    return out


def clip_segment(src: Path, start_s: float, end_s: float, out: Path,
                 vertical: bool = True) -> Path:
    vf = "crop=ih*9/16:ih,scale=1080:1920" if vertical else "scale=1080:1920"
    _run(["ffmpeg", "-y", "-ss", str(start_s), "-to", str(end_s), "-i", str(src),
          "-vf", vf, str(out)])
    return out
