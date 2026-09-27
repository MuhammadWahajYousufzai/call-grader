"""Audio validation + normalization (ffmpeg) for Gemini inline upload limits."""

from __future__ import annotations

import subprocess
from pathlib import Path

GEMINI_LIMIT_BYTES = 14 * 1024 * 1024


def probe(path: Path) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,size",
         "-of", "default=noprint_wrappers=1", str(path)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    info: dict = {}
    for line in (r.stdout or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            info[k.strip()] = v.strip()
    return info


def normalize_for_transcription(src: Path, dst: Path) -> Path:
    """Return a path ready for upload: original if small, else mono 16k MP3-ish."""
    if src.stat().st_size <= GEMINI_LIMIT_BYTES:
        return src
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-ac", "1", "-ar", "16000", "-b:a", "32k", str(dst)],
        capture_output=True, timeout=300, check=True,
    )
    return dst


def split_for_upload(path: Path, chunk_seconds: int = 600) -> list[tuple[Path, float]]:
    """Split into chunks; returns [(chunk_path, offset_seconds)]."""
    info = probe(path)
    total = float(info.get("duration", 0) or 0)
    if total <= chunk_seconds and path.stat().st_size <= GEMINI_LIMIT_BYTES:
        return [(path, 0.0)]
    out: list[tuple[Path, float]] = []
    start = 0.0
    idx = 0
    while start < total:
        chunk = path.parent / f"{path.stem}_c{idx}{path.suffix}"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(start), "-t", str(chunk_seconds), "-i", str(path),
             "-c", "copy", str(chunk)],
            capture_output=True, timeout=300, check=True,
        )
        out.append((chunk, start))
        start += chunk_seconds
        idx += 1
    return out
