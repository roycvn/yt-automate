"""Assemble scene images + per-scene narration into a finished MP4.

Each scene becomes a clip: its image held for the narration's duration with a
slow ken-burns zoom, with the narration as audio. Clips are concatenated into
the final video. Requires ffmpeg/ffprobe on PATH (the generation worker image
installs them — this is the one stage that needs ffmpeg, unlike the light cron).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

FPS = 30


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def _wav_duration(path: Path) -> float:
    import wave
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def _scene_clip(image: Path, audio: Path, out: Path,
                width: int = 1920, height: int = 1080) -> Path:
    """One scene: image (ken-burns zoom over `dur`) + narration audio -> mp4."""
    dur = max(_wav_duration(audio), 1.0)
    frames = int(dur * FPS)
    # Scale up then slow zoompan; pad to exact canvas to avoid odd dims.
    vf = (
        f"scale={width*2}:{height*2},"
        f"zoompan=z='min(zoom+0.0008,1.12)':d={frames}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={FPS},"
        f"format=yuv420p"
    )
    _run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-i", str(image),
        "-i", str(audio),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k",
        "-t", f"{dur:.3f}", "-shortest",
        str(out),
    ])
    return out


def assemble(images: list[Path], audios: list[Path], out: Path,
             work: Path, width: int = 1920, height: int = 1080) -> Path:
    """Build per-scene clips and concatenate into the final video at `out`."""
    if len(images) != len(audios):
        raise ValueError("images and audios must be 1:1 per scene")
    work.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []
    for i, (img, aud) in enumerate(zip(images, audios)):
        clip = work / f"clip_{i:02d}.mp4"
        _scene_clip(img, aud, clip, width, height)
        clips.append(clip)

    concat_list = work / "concat.txt"
    concat_list.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    out.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k",
        str(out),
    ])
    return out
