"""Music bed: generate (ElevenLabs Music) / user file / mock synth, then fit frame-exactly to the timeline."""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from tms.audio import mock, wav
from tms.audio.elevenlabs import Client
from tms.state.project import GateViolation, Project, ProjectError
from tms.timeline import SPF

FADE_IN_F, FADE_OUT_F = 15, 75
EXTRA_S = 4.0       # generate a little longer: models add their own intro/outro
XFADE_S = 2.0
BED_RMS = 0.06      # music bed level before ducking (was 0.08: the user found the music a little loud)


def _body_start(x: np.ndarray, max_skip_s: float = 4.0) -> int:
    """Skip a quiet intro: first 100 ms window within 6 dB of the median loudness (max 4 s)."""
    mono = x.mean(axis=1) if x.ndim > 1 else x
    win = wav.SR // 10
    n = len(mono) // win
    if n < 5:
        return 0
    rms = 20 * np.log10(np.sqrt(np.mean(mono[: n * win].reshape(n, win) ** 2, axis=1)) + 1e-9)
    med = np.median(rms)
    for k in range(min(n, int(max_skip_s * 10))):
        if rms[k] >= med - 6:
            return k * win
    return int(max_skip_s * wav.SR)


def _body_end(x: np.ndarray, max_trim_s: float = 8.0) -> int:
    """Drop a quiet outro: end after the last 100 ms window within 6 dB of the median loudness (trim at most 8 s)."""
    mono = x.mean(axis=1) if x.ndim > 1 else x
    win = wav.SR // 10
    n = len(mono) // win
    if n < 5:
        return len(mono)
    rms = 20 * np.log10(np.sqrt(np.mean(mono[: n * win].reshape(n, win) ** 2, axis=1)) + 1e-9)
    med = np.median(rms)
    for k in range(n - 1, max(-1, n - 1 - int(max_trim_s * 10)), -1):
        if rms[k] >= med - 6:
            return min(len(mono), (k + 1) * win)
    return len(mono) - int(max_trim_s * wav.SR)


def fit(raw: np.ndarray, frames: int) -> tuple[np.ndarray, dict]:
    """Exactly frames*SPF stereo samples; loops with a 2 s crossfade when too short; fades; ~-22 LUFS-ish level."""
    if raw.ndim == 1:
        raw = np.stack([raw, raw], axis=1)
    need = frames * SPF
    start = _body_start(raw)
    body = raw[start:_body_end(raw)]
    splices = 0
    xf = int(XFADE_S * wav.SR)
    out = body.copy()
    while len(out) < need:
        if len(body) <= xf * 2:
            raise ProjectError("music file too short to loop")
        ramp = np.linspace(0, 1, xf)[:, None]
        out = np.concatenate([out[:-xf], out[-xf:] * (1 - ramp) + body[:xf] * ramp, body[xf:]])
        splices += 1
    out = out[:need].copy()
    out[:FADE_IN_F * SPF] *= np.linspace(0, 1, FADE_IN_F * SPF)[:, None]
    out[-FADE_OUT_F * SPF:] *= np.linspace(1, 0, FADE_OUT_F * SPF)[:, None]
    rms = np.sqrt(np.mean(out ** 2)) + 1e-9
    out *= min(BED_RMS / rms, 4.0)  # bed level well under the voice before ducking
    return out.astype(np.float32), {"start_s": round(start / wav.SR, 3), "end_s": round((start + min(len(body), need)) / wav.SR, 3),
                                     "splices": splices}


def music_request_s(seconds: float, cap_s: float) -> float:
    """Seconds of music to generate: the video plus EXTRA_S, but never beyond the approved budget. When the cap is
    shorter, `fit` loops the remainder with a crossfade; refuse only if that would need more than one loop (2x)."""
    want = seconds + EXTRA_S
    if want <= cap_s:
        return want
    if cap_s * 2 < seconds + XFADE_S:
        raise GateViolation(f"music budget: {want:.0f}s needed, approved {cap_s}s is too short even to loop once")
    return float(cap_s)


def build(pr: Project, timeline: dict, inputs: dict, client: Client | None = None) -> dict:
    brief = pr.load_artifact("brief")
    mu = brief["music"]
    frames = timeline["frames"]
    seconds = frames / 30
    base = {"version": "1", "project_id": pr.id, "inputs": inputs, "request_hash": None, "cached": False,
            "plan_tier": None, "music_s_billed": 0, "fade_in_frames": FADE_IN_F, "fade_out_frames": FADE_OUT_F}
    if mu["source"] == "none":
        return {**base, "source": "none", "provider": "none", "raw_file": None, "raw_duration_s": 0.0, "fitted_file": None,
                "samples": 0, "body": {"start_s": 0.0, "end_s": 0.0}, "fade_in_frames": 0, "fade_out_frames": 0}
    raw_rel = "media/music/raw.wav"
    raw_path = pr.dir / raw_rel
    h, cached, billed, provider = None, False, 0.0, "mock_synth"
    if mu["source"] == "file":
        src = Path(mu["file"]) if Path(mu["file"]).is_absolute() else pr.dir / mu["file"]
        wav.to_wav48(src, raw_path, channels=2)
        provider = "file"
    elif pr.dry_run:
        mock.music(seconds + EXTRA_S, raw_path)
    else:
        req_s = music_request_s(seconds, brief["budget"]["music_s_max"])
        client = client or Client()
        audio, h, cached = client.music(mu["mood"], int(req_s * 1000), seed=brief["voice"]["seed"])
        with tempfile.TemporaryDirectory(prefix="tms music ") as td:
            (Path(td) / "raw.mp3").write_bytes(audio)
            wav.to_wav48(Path(td) / "raw.mp3", raw_path, channels=2)
        provider = "elevenlabs"
        billed = 0.0 if cached else round(req_s, 1)
    raw = wav.read(raw_path)
    fitted, body = fit(raw, frames)
    fit_rel = "media/music/bed_fit.wav"
    wav.write(pr.dir / fit_rel, fitted)
    return {**base, "source": mu["source"], "provider": provider, "request_hash": h, "cached": cached,
            "raw_file": raw_rel, "raw_duration_s": round(len(raw) / wav.SR, 3), "fitted_file": fit_rel,
            "samples": int(len(fitted)), "body": {"start_s": body["start_s"], "end_s": body["end_s"]}, "music_s_billed": billed}
