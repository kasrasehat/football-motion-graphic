"""`tms qa sync-test` — end-to-end A/V sync calibration through the real chain:
Remotion render (SyncCal) -> sample-exact clicks at frame*1600 -> mux (video copy + AAC) -> detect both -> compare."""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from tms import jsonio, remotion
from tms.audio import wav
from tms.finalize import mux
from tms.timeline import SPF

FLASHES = [30, 75, 121, 150]
FRAMES = 180


def _video_flash_frames(path: Path) -> list[int]:
    p = subprocess.run([wav.ffmpeg(), "-hide_banner", "-i", str(path), "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG",
                        "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    frames, cur = [], None
    for line in p.stderr.splitlines():
        m = re.search(r"frame:(\d+)", line)
        if m:
            cur = int(m.group(1))
        m = re.search(r"lavfi\.signalstats\.YAVG=([\d.]+)", line)
        if m and cur is not None and float(m.group(1)) > 128:
            frames.append(cur)
    return frames


def _audio_click_frames(path: Path, workdir: Path) -> list[int]:
    a = workdir / "decoded.wav"
    wav.run([wav.ffmpeg(), "-v", "error", "-y", "-i", path, "-vn", "-ac", 1, "-ar", wav.SR, "-c:a", "pcm_s16le", a])
    x = wav.read(a)
    n = len(x) // SPF
    rms = np.sqrt(np.mean(x[: n * SPF].reshape(n, SPF) ** 2, axis=1))
    loud = rms > 0.05
    return [f for f in range(n) if loud[f] and (f == 0 or not loud[f - 1])]


def run(workdir: Path | None = None) -> dict:
    with tempfile.TemporaryDirectory(prefix="tms sync ") as td:
        d = Path(workdir) if workdir else Path(td)
        d.mkdir(parents=True, exist_ok=True)
        props = d / "props.json"
        jsonio.write_json(props, {"durationInFrames": FRAMES, "flashes": FLASHES})
        video = d / "video.mp4"
        remotion.render("SyncCal", video, props=props, timeout=600)
        audio = np.zeros(FRAMES * SPF, dtype=np.float32)
        t = np.arange(int(0.02 * wav.SR)) / wav.SR
        click = (0.6 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
        for f in FLASHES:
            audio[f * SPF: f * SPF + len(click)] += click
        wav.write(d / "clicks.wav", np.stack([audio, audio], axis=1))
        out = d / "muxed.mp4"
        mux(video, d / "clicks.wav", out)
        vf = _video_flash_frames(out)
        af = _audio_click_frames(out, d)
        pairs = list(zip(vf, af))
        offsets = [a - v for v, a in pairs]
        ok = vf == FLASHES and len(af) == len(FLASHES) and all(abs(o) <= 1 for o in offsets)
        return {"ok": ok, "expected": FLASHES, "video_flash_frames": vf, "audio_click_frames": af, "offsets_frames": offsets,
                "max_abs_offset": max((abs(o) for o in offsets), default=None)}


def cmd_sync_test(a) -> int:
    res = run(Path(a.keep) if a.keep else None)
    print(f"video flashes at {res['video_flash_frames']}\naudio clicks at  {res['audio_click_frames']}\n"
          f"offsets (frames): {res['offsets_frames']}\nsync-test: {'PASS' if res['ok'] else 'FAIL'} (max |offset| {res['max_abs_offset']} frame, limit 1)")
    return 0 if res["ok"] else 1

