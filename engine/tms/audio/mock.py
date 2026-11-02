"""Offline providers for dry runs and tests: flite TTS (ffmpeg) with synthetic word alignment, and a synth music bed.
flite reads the text from a file next to the cwd, so no text or path ever goes into a filtergraph argument."""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from tms.audio import wav


def tts(text: str, out_wav: Path) -> dict:
    """Synthesize `text` to a 48 kHz mono wav. Returns an alignment dict shaped like ElevenLabs'
    (characters + start/end seconds), distributed over the voiced span proportionally to characters."""
    with tempfile.TemporaryDirectory(prefix="tms flite ") as td:
        tdp = Path(td)
        (tdp / "line.txt").write_text(text, encoding="ascii", errors="replace")
        wav.run([wav.ffmpeg(), "-v", "error", "-y", "-f", "lavfi", "-i", "flite=textfile=line.txt:voice=slt",
                 "-ar", wav.SR, "-ac", 1, "-c:a", "pcm_s16le", "raw.wav"], cwd=tdp)
        x = wav.read(tdp / "raw.wav")
    wav.write(out_wav, x)
    a, b = wav.speech_bounds(x)
    t0, t1 = a / wav.SR, b / wav.SR
    chars = list(text)
    weights = np.array([0.4 if c == " " else (1.6 if c in ",.;:!?" else 1.0) for c in chars], dtype=float)
    edges = t0 + (t1 - t0) * np.concatenate([[0.0], np.cumsum(weights) / weights.sum()])
    return {"characters": chars, "character_start_times_seconds": [round(v, 4) for v in edges[:-1]],
            "character_end_times_seconds": [round(v, 4) for v in edges[1:]]}


def music(seconds: float, out_wav: Path, seed: int = 7) -> None:
    """Deterministic instrumental bed: soft chord pad + kick/hat pulse at 100 bpm (stereo, 48 kHz)."""
    n = int(seconds * wav.SR)
    t = np.arange(n) / wav.SR
    chords = [(220.0, 277.18, 329.63), (196.0, 246.94, 293.66), (174.61, 220.0, 261.63), (196.0, 246.94, 329.63)]
    bar = 2.4  # seconds per chord (100 bpm, 4 beats)
    pad = np.zeros(n)
    for k, ch in enumerate(chords):
        mask = ((t // bar) % len(chords)) == k
        for f in ch:
            pad[mask] += np.sin(2 * np.pi * f * t[mask]) * 0.06
    beat = 0.6
    phase = t % beat
    kick = np.exp(-phase * 18) * np.sin(2 * np.pi * 55 * phase) * 0.35
    rng = np.random.default_rng(seed)
    hat_env = np.exp(-((t + beat / 2) % beat) * 60)
    hat = rng.standard_normal(n) * hat_env * 0.03
    mono = pad + kick + hat
    stereo = np.stack([mono * 0.95, mono * 0.9 + hat * 0.3], axis=1)
    wav.write(out_wav, stereo.astype(np.float32))
