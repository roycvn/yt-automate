"""Turn the raw body assembly into a finished video: intro/outro cards, an
original ambient drone bed, and (via klipr) burned captions.

Text rendering (title, captions, CTA) is deferred to klipr's libass pass for
correct Devanagari/Telugu shaping — see captions.build_ass. Here we only build
the silent video skeleton + audio bed.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .assemble import assemble
from .captions import build_ass, wav_duration
from .images import generate_image

INTRO_BG_PROMPT = (
    "Cinematic 2D animated horror title-card background, pitch-dark eerie "
    "atmosphere, swirling fog, faint blood-red moonlight, ominous silhouettes "
    "in the distance, heavy vignette, lots of empty dark space in the center "
    "for a title, no text, dramatic, film-grain"
)
OUTRO_BG_PROMPT = (
    "Cinematic 2D animated horror end-card background, dark misty graveyard at "
    "night, dim glow, empty center space for text, no text, eerie, vignette"
)

FPS = 30
W, H = 1920, 1080
INTRO_S = 3.0
OUTRO_S = 4.0
BG = "0x0A0A12"  # near-black, slight blue


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def _card(out: Path, dur: float, image: Path | None = None) -> Path:
    """A silent video card of length `dur`. With `image`, a cinematic slow-zoom
    over the artwork; otherwise a flat dark background. Title text is burned
    later via ASS."""
    frames = int(dur * FPS)
    if image is not None:
        vf = (
            f"scale={W*2}:{H*2},"
            f"zoompan=z='min(zoom+0.0010,1.15)':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
            f"format=yuv420p"
        )
        _run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-loop", "1", "-i", str(image),
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-vf", vf, "-t", f"{dur}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", str(out),
        ])
        return out
    _run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c={BG}:s={W}x{H}:r={FPS}:d={dur}",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", f"{dur}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", str(out),
    ])
    return out


def _drone(out: Path, dur: float) -> Path:
    """Original low ambient tension bed (two detuned low sines + tremolo + lowpass)."""
    _run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"sine=frequency=55:duration={dur}",
        "-f", "lavfi", "-i", f"sine=frequency=82.5:duration={dur}",
        "-filter_complex",
        "[0][1]amix=inputs=2,tremolo=f=0.15:d=0.6,lowpass=f=180,volume=0.9",
        "-t", f"{dur}", str(out),
    ])
    return out


def _concat(clips: list[Path], out: Path) -> Path:
    inputs: list[str] = []
    for c in clips:
        inputs += ["-i", str(c)]
    n = len(clips)
    streams = "".join(f"[{i}:v][{i}:a]" for i in range(n))
    _run([
        "ffmpeg", "-y", "-loglevel", "error", *inputs,
        "-filter_complex", f"{streams}concat=n={n}:v=1:a=1[v][a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", str(out),
    ])
    return out


def _mix_drone(video: Path, drone: Path, out: Path) -> Path:
    _run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(video), "-i", str(drone),
        "-filter_complex",
        "[1:a]volume=0.32[d];[0:a][d]amix=inputs=2:duration=first:dropout_transition=0[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", str(out),
    ])
    return out


def add_logos(src: Path, out: Path, *, right_logo: Path | None = None,
              bottom_logo: Path | None = None, br_logo: Path | None = None,
              tr_logo: Path | None = None,
              right_scale: float = 0.12, bottom_scale: float = 0.20,
              br_scale: float = 0.16, tr_scale: float = 0.12,
              opacity: float = 0.9, margin: int = 36) -> Path:
    """Overlay branding. `tr_logo` top-right, `right_logo` mid-right,
    `bottom_logo` bottom-center, `br_logo` bottom-right (footer). Missing logos
    are skipped. Re-encodes once."""
    inputs = ["-i", str(src)]
    filters: list[str] = []
    last = "0:v"
    idx = 1
    if tr_logo and tr_logo.exists():
        inputs += ["-i", str(tr_logo)]
        filters.append(
            f"[{idx}]format=rgba,colorchannelmixer=aa={opacity},scale=iw*{tr_scale}:-1[tr]")
        filters.append(f"[{last}][tr]overlay=W-w-{margin}:{margin}[v{idx}]")
        last = f"v{idx}"; idx += 1
    if right_logo and right_logo.exists():
        inputs += ["-i", str(right_logo)]
        filters.append(
            f"[{idx}]format=rgba,colorchannelmixer=aa={opacity},scale=iw*{right_scale}:-1[r]")
        filters.append(f"[{last}][r]overlay=W-w-{margin}:(H-h)/2[v{idx}]")
        last = f"v{idx}"; idx += 1
    if bottom_logo and bottom_logo.exists():
        inputs += ["-i", str(bottom_logo)]
        filters.append(
            f"[{idx}]format=rgba,colorchannelmixer=aa={opacity},scale=iw*{bottom_scale}:-1[b]")
        filters.append(f"[{last}][b]overlay=(W-w)/2:H-h-{margin}[v{idx}]")
        last = f"v{idx}"; idx += 1
    if br_logo and br_logo.exists():
        inputs += ["-i", str(br_logo)]
        filters.append(
            f"[{idx}]format=rgba,colorchannelmixer=aa={opacity},scale=iw*{br_scale}:-1[br]")
        filters.append(f"[{last}][br]overlay=W-w-{margin}:H-h-{margin}[v{idx}]")
        last = f"v{idx}"; idx += 1
    if not filters:
        return src
    _run([
        "ffmpeg", "-y", "-loglevel", "error", *inputs,
        "-filter_complex", ";".join(filters),
        "-map", f"[{last}]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-c:a", "copy", str(out),
    ])
    return out


# position name -> ffmpeg overlay x:y expression (w,h = overlay dims, m = margin)
_POS = {
    "top-left": "{m}:{m}",
    "top-right": "W-w-{m}:{m}",
    "top-center": "(W-w)/2:{m}",
    "mid-left": "{m}:(H-h)/2",
    "mid-right": "W-w-{m}:(H-h)/2",
    "bottom-left": "{m}:H-h-{m}",
    "bottom-right": "W-w-{m}:H-h-{m}",
    "bottom-center": "(W-w)/2:H-h-{m}",
}


def overlay_logos(src: Path, out: Path, items: list[dict]) -> Path:
    """Overlay an arbitrary set of logos from config. Each item:
    {path, position, scale, opacity, margin}. Unknown/missing entries skipped.
    `position` is one of _POS keys. Re-encodes once."""
    valid = []
    for it in items:
        p = Path(it["path"])
        if p.exists() and it.get("position") in _POS:
            valid.append(it)
    if not valid:
        return src
    inputs = ["-i", str(src)]
    filters: list[str] = []
    last = "0:v"
    for i, it in enumerate(valid, start=1):
        inputs += ["-i", str(it["path"])]
        scale = float(it.get("scale", 0.14))
        op = float(it.get("opacity", 0.9))
        m = int(it.get("margin", 36))
        xy = _POS[it["position"]].format(m=m)
        filters.append(f"[{i}]format=rgba,colorchannelmixer=aa={op},scale=iw*{scale}:-1[l{i}]")
        tag = f"v{i}"
        filters.append(f"[{last}][l{i}]overlay={xy}[{tag}]")
        last = tag
    _run([
        "ffmpeg", "-y", "-loglevel", "error", *inputs,
        "-filter_complex", ";".join(filters),
        "-map", f"[{last}]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-c:a", "copy", str(out),
    ])
    return out


def player_safe(src: Path, out: Path) -> Path:
    """Re-encode to a widely-compatible profile (QuickTime-safe) + faststart."""
    _run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", "-c:a", "aac", "-b:a", "160k", str(out),
    ])
    return out


def build_finished_skeleton(scenes: list, images: list[Path], audios: list[Path],
                            work: Path, *, intro_title: str, outro_text: str
                            ) -> tuple[Path, str]:
    """Produce the captionless finished video (intro+body+outro+drone) and the
    ASS text to burn on it. Returns (video_path, ass_text)."""
    work.mkdir(parents=True, exist_ok=True)
    body = assemble(images, audios, work / "body.mp4", work / "body_work", W, H)
    # Cinematic title/end cards from dedicated Flux backgrounds (slow zoom).
    intro_bg = generate_image(INTRO_BG_PROMPT, work / "intro_bg.png", aspect_ratio="16:9")
    outro_bg = generate_image(OUTRO_BG_PROMPT, work / "outro_bg.png", aspect_ratio="16:9")
    intro = _card(work / "intro.mp4", INTRO_S, image=intro_bg)
    outro = _card(work / "outro.mp4", OUTRO_S, image=outro_bg)
    joined = _concat([intro, body, outro], work / "joined.mp4")

    body_dur = sum(max(wav_duration(a), 1.0) for a in audios)
    total = INTRO_S + body_dur + OUTRO_S
    drone = _drone(work / "drone.wav", total)
    finished = _mix_drone(joined, drone, work / "finished_nocaps.mp4")

    ass = build_ass(scenes, audios, intro_s=INTRO_S, outro_s=OUTRO_S,
                    intro_title=intro_title, outro_text=outro_text)
    return finished, ass
