"""WAV I/O (16-bit PCM via the stdlib) and ffmpeg helpers. Paths never go inside filtergraphs."""
from __future__ import annotations

import json
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 48000


def ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def ffprobe() -> str:
    return shutil.which("ffprobe") or "ffprobe"


def run(argv: list, cwd: Path | None = None) -> subprocess.CompletedProcess:
    p = subprocess.run([str(a) for a in argv], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(f"{Path(str(argv[0])).name} failed ({p.returncode}): {p.stderr[-1500:]}")
    return p


def to_wav48(src: Path, dst: Path, channels: int = 1) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    run([ffmpeg(), "-v", "error", "-y", "-i", src, "-ac", channels, "-ar", SR, "-c:a", "pcm_s16le", dst])


def read(path: Path) -> np.ndarray:
    """float32 samples, shape (n,) for mono or (n, ch)."""
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2 or w.getframerate() != SR:
            raise ValueError(f"{path.name}: expected 16-bit {SR} Hz, got {w.getsampwidth() * 8}-bit {w.getframerate()} Hz")
        ch = w.getnchannels()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    return data if ch == 1 else data.reshape(-1, ch)


def write(path: Path, samples: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    x = np.clip(samples, -1.0, 1.0)
    ch = 1 if x.ndim == 1 else x.shape[1]
    pcm = (x * 32767.0).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)


def duration(path: Path) -> float:
    p = run([ffprobe(), "-v", "error", "-show_entries", "format=duration", "-of", "json", path])
    return float(json.loads(p.stdout)["format"]["duration"])


def speech_bounds(x: np.ndarray, thresh_db: float = -40.0, win: int = 480) -> tuple[int, int]:
    """First/last sample whose 10 ms RMS exceeds thresh_db (mono)."""
    if x.ndim > 1:
        x = x.mean(axis=1)
    n = len(x) // win
    if n == 0:
        return 0, len(x)
    rms = np.sqrt(np.mean(x[: n * win].reshape(n, win) ** 2, axis=1) + 1e-12)
    loud = np.nonzero(20 * np.log10(rms) > thresh_db)[0]
    if len(loud) == 0:
        return 0, len(x)
    return int(loud[0] * win), int(min((loud[-1] + 1) * win, len(x)))


def loudness(path: Path) -> dict:
    """Integrated loudness, LRA and true peak (ffmpeg ebur128 with peak=true)."""
    p = subprocess.run([ffmpeg(), "-hide_banner", "-nostats", "-i", str(path), "-filter_complex", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = p.stderr[p.stderr.rfind("Summary:"):]
    out = {}
    for key, label in (("integrated_lufs", "I:"), ("lra", "LRA:"), ("true_peak_dbtp", "Peak:")):
        i = tail.find(label)
        if i >= 0:
            try:
                out[key] = float(tail[i + len(label):].split()[0])
            except ValueError:
                out[key] = None
    return out
