"""Final mix: sample-exact voice stem + envelope-ducked music + two-pass loudnorm (-14 LUFS, -1.5 dBTP)."""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import numpy as np

from tms.audio import wav
from tms.timeline import SPF

TARGET_I, TARGET_TP, TARGET_LRA = -14.0, -1.5, 11.0


def vo_stem(project_dir: Path, timeline: dict) -> np.ndarray:
    total = timeline["frames"] * SPF
    stem = np.zeros(total, dtype=np.float32)
    for v in timeline["vo"]:
        x = wav.read(project_dir / v["file"])
        a = v["from"] * SPF  # sample-exact placement: frame * 1600
        b = min(a + len(x), total)
        stem[a:b] += x[: b - a]
    return stem


def duck_envelope(timeline: dict) -> np.ndarray:
    """Gain (linear) per sample: depth_db inside VO windows with attack/release ramps in dB."""
    total = timeline["frames"] * SPF
    d = timeline["duck"]
    g_db = np.zeros(total, dtype=np.float32)
    att = int(d["attack_ms"] / 1000 * wav.SR)
    rel = int(d["release_ms"] / 1000 * wav.SR)
    for a, b in d["windows"]:
        sa, sb = a * SPF, min(b * SPF, total)
        lo = max(sa - att, 0)
        g_db[lo:sa] = np.minimum(g_db[lo:sa], np.linspace(0, d["depth_db"], sa - lo))
        g_db[sa:sb] = d["depth_db"]
        hi = min(sb + rel, total)
        g_db[sb:hi] = np.minimum(g_db[sb:hi], np.linspace(d["depth_db"], 0, hi - sb))
    return (10 ** (g_db / 20)).astype(np.float32)


def _loudnorm_measure(src: Path) -> dict:
    p = wav.run([wav.ffmpeg(), "-hide_banner", "-nostats", "-i", src, "-af",
                 f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr, re.S)
    return json.loads(m.group(0))


def loudnorm(src: Path, dst: Path) -> dict:
    """Two-pass linear loudnorm; falls back to gain + limiter if ffmpeg would switch to dynamic mode."""
    m = _loudnorm_measure(src)
    filt = (f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
            f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true:"
            f"print_format=json")
    p = wav.run([wav.ffmpeg(), "-hide_banner", "-nostats", "-y", "-i", src, "-af", filt, "-ar", wav.SR, "-ac", 2, "-c:a", "pcm_s16le", dst])
    out = re.search(r"\{[^{}]*\"normalization_type\"[^{}]*\}", p.stderr, re.S)
    info = json.loads(out.group(0)) if out else {}
    if info.get("normalization_type") != "linear":
        gain = TARGET_I - float(m["input_i"])
        wav.run([wav.ffmpeg(), "-hide_banner", "-nostats", "-y", "-i", src, "-af",
                 f"volume={gain:.2f}dB,alimiter=limit=0.83:level=false", "-ar", wav.SR, "-ac", 2, "-c:a", "pcm_s16le", dst])
        info["normalization_type"] = "gain+limiter"
    return info


def mix(project_dir: Path, timeline: dict, music_manifest: dict, out_wav: Path) -> dict:
    vo = vo_stem(project_dir, timeline)
    total = len(vo)
    if music_manifest.get("fitted_file"):
        mu = wav.read(project_dir / music_manifest["fitted_file"])
        if len(mu) != total:
            raise ValueError(f"music bed has {len(mu)} samples, timeline needs {total}")
        mu_d = mu * duck_envelope(timeline)[:, None]
    else:
        mu_d = np.zeros((total, 2), dtype=np.float32)
    pre = mu_d + vo[:, None] * 0.9
    with tempfile.TemporaryDirectory(prefix="tms mix ") as td:
        pre_path = Path(td) / "premix.wav"
        wav.write(pre_path, pre)
        info = loudnorm(pre_path, out_wav)
    # VO-over-music margin inside VO windows (stems before normalisation; gain applies to both equally)
    margin = None
    win = [(a * SPF, b * SPF) for a, b in timeline["duck"]["windows"]]
    if win and music_manifest.get("fitted_file"):
        v = np.concatenate([vo[a:b] for a, b in win])
        m = np.concatenate([mu_d[a:b].mean(axis=1) for a, b in win])
        voiced = np.abs(v) > 1e-3
        rv = np.sqrt(np.mean(v[voiced] ** 2)) if voiced.any() else 1e-9
        rm = np.sqrt(np.mean(m ** 2)) + 1e-9
        margin = round(float(20 * np.log10(rv / rm)), 2)
    return {"normalization": info.get("normalization_type"), "vo_music_margin_db": margin, **wav.loudness(out_wav)}
