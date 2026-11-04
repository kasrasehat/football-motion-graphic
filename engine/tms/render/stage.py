"""Render stage: render_props -> silent Remotion video -> mix -> mux -> captions.srt -> FQ checks -> render_report."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

from tms import jsonio, remotion
from tms.audio import wav
from tms.audio.mix import mix
from tms.choreo.cli import contact_sheet
from tms.finalize import mux, probe
from tms.props.builder import build as build_props
from tms.render.projection import project_player, token_radius_px
from tms.validate.colour import delta_e2000
from tms.timeline import FPS

QA_TARGETS = {"lufs": (-15.0, -13.0), "tp_max": -1.0, "lra_max": 11.0, "margin_min": 9.0, "bitrate": (4e6, 20e6)}
CAPTION_BOX_TOP = 0.815  # top edge of a two-line bottom caption, as a share of the frame height


def _h(pr, *names):
    return {n: jsonio.sha256_file(pr.artifact_path(n)) for n in names}


def build_render_props(pr, scale: float = 1.0) -> dict:
    a = {n: pr.load_artifact(n) for n in ("choreography", "timeline", "brief", "narration_script", "scene_plan", "tactic_spec")}
    props = build_props(a["choreography"], a["timeline"], a["brief"], a["narration_script"], a["scene_plan"], a["tactic_spec"],
                        scale=scale, dossier=pr.load_artifact("match_dossier"), prediction=pr.load_artifact("prediction"),
                        analysis=pr.load_artifact("match_analysis"),
                        inputs=_h(pr, "choreography", "timeline", "brief", "voiceover_manifest", "music_manifest"))
    for c in props["captions"]:
        c["place"] = caption_place(props, c)
    return props


def caption_place(props: dict, cap: dict) -> str:
    """Move a caption to the top only if the ball enters the bottom caption box while it is up. A top caption covers
    whatever the camera has framed there, so a ball merely low in the frame is not reason enough."""
    from tms.render.projection import project_ball
    frames = [f for f in range(cap["from"], cap["to"], 3) if any(a <= f < b for a, b in props["pitchVisible"])]
    try:
        lowest = max((project_ball(props, f, 1.0)[1] for f in frames), default=0.0)
    except Exception:  # noqa: BLE001 — placement is cosmetic; never fail the render on it
        return "bottom"
    return "top" if lowest > props["height"] * CAPTION_BOX_TOP else "bottom"


def srt(timeline: dict) -> str:
    def ts(f: int) -> str:
        ms = round(f / FPS * 1000)
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    out = []
    for k, c in enumerate(timeline["captions"], 1):
        out += [str(k), f"{ts(c['from'])} --> {ts(c['to'])}", *c["lines"], ""]
    return "\n".join(out)


def _frame_rgb(video: Path, frame: int, width: int, height: int) -> np.ndarray:
    p = subprocess.run([wav.ffmpeg(), "-v", "error", "-ss", f"{frame / FPS + 0.001:.4f}", "-i", str(video), "-frames:v", "1",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    return np.frombuffer(p.stdout, dtype=np.uint8)[: width * height * 3].reshape(height, width, 3)


def pixel_probes(video: Path, props: dict, scale: float, n_frames: int = 6) -> tuple[bool, str]:
    W, H = props["width"], props["height"]  # props are already at the render size
    pitch = [s for s in props["scenes"] if s["kind"] == "pitch"]
    frames = [(s["from"] + s["to"]) // 2 for s in pitch][:n_frames]
    fills = {t: props["theme"]["teams"][t]["fill"] for t in "HA"}
    ok = total = 0
    for f in frames:
        img = _frame_rgb(video, f, W, H)
        from tms.render.projection import camera_at
        r = token_radius_px(camera_at(props, f)[2], W, H, props["orientation"])
        for team in "HA":
            for pid in [e["id"] for e in props["entities"] if e["team"] == team][1:4]:
                x, y = project_player(props, pid, f, 1.0)
                if not (r * 3 < x < W - r * 3 and r * 3 < y < H - r * 3):
                    continue
                hits = 0
                for dx, dy in ((0.6, 0), (-0.6, 0), (0, 0.6), (0, -0.6)):
                    px, py = int(x + dx * r), int(y + dy * r)
                    rgb = img[py, px]
                    if delta_e2000(fills[team], "#%02x%02x%02x" % tuple(int(v) for v in rgb)) < 12:
                        hits += 1
                total += 1
                ok += hits >= 2
    if total == 0:
        return False, "no probe-able tokens on screen"
    share = ok / total
    return share >= 0.7, f"{ok}/{total} token probes match team colours ({share:.0%})"


def black_frames(video: Path, props: dict) -> list[tuple[float, float]]:
    p = subprocess.run([wav.ffmpeg(), "-hide_banner", "-i", str(video), "-vf", "blackdetect=d=0.1:pix_th=0.04:pic_th=0.98",
                        "-an", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = []
    for line in p.stderr.splitlines():
        if "black_start" in line:
            parts = dict(kv.split(":") for kv in line.split()[3:] if ":" in kv)
            a, b = float(parts["black_start"]), float(parts["black_end"])
            # black is only a fault inside pitch scenes (cards and fades may be dark on purpose)
            if any(s["from"] / FPS <= a < s["to"] / FPS for s in props["scenes"] if s["kind"] == "pitch"):
                out.append((a, b))
    return out


def run_final(pr, scale: float = 1.0) -> dict:
    props = build_render_props(pr, scale)
    jsonio.write_json(pr.artifact_path("render_props"), props, compact=True)
    rdir = pr.dir / "renders"
    silent = rdir / "video_silent.mp4"
    remotion.render("TacticVideo", silent, props=pr.artifact_path("render_props"), timeout=7200)
    tl, mm, vo = pr.load_artifact("timeline"), pr.load_artifact("music_manifest"), pr.load_artifact("voiceover_manifest")
    mix_info = mix(pr.dir, tl, mm, pr.dir / "media" / "mix.wav")
    final = rdir / "final.mp4"
    mux(silent, pr.dir / "media" / "mix.wav", final)
    (rdir / "captions.srt").write_text(srt(tl), encoding="utf-8", newline="\n")
    pr_ = probe(final)
    v, a, fmt = pr_["video"], pr_["audio"], pr_["format"]
    frames = int(v.get("nb_read_frames", 0))
    final_loud = wav.loudness(final)
    checks = []

    def check(rule, ok, detail, severity="error"):
        checks.append({"rule": rule, "ok": bool(ok), "severity": severity, "detail": detail})
    check("FQ-01", v.get("codec_name") == "h264" and v.get("profile") == "High" and v.get("pix_fmt") == "yuv420p"
          and v.get("width") == props["width"] and v.get("height") == props["height"] and v.get("r_frame_rate") == "30/1"
          and frames == tl["frames"],
          f"{v.get('codec_name')} {v.get('profile')} {v.get('pix_fmt')} {v.get('width')}x{v.get('height')} {v.get('r_frame_rate')} "
          f"{frames} frames (timeline {tl['frames']})")
    a_dur = float(a.get("duration") or 0)
    check("FQ-02", a.get("codec_name") == "aac" and a.get("sample_rate") == "48000" and a.get("channels") == 2
          and abs(a_dur - tl["frames"] / FPS) <= 1 / FPS + 0.03,
          f"{a.get('codec_name')} {a.get('sample_rate')} Hz {a.get('channels')} ch, {a_dur:.3f}s vs {tl['frames'] / FPS:.3f}s")
    lo, hi = QA_TARGETS["lufs"]
    I, TP, LRA = final_loud.get("integrated_lufs"), final_loud.get("true_peak_dbtp"), final_loud.get("lra")
    check("FQ-03", I is not None and lo <= I <= hi and TP is not None and TP <= QA_TARGETS["tp_max"] and (LRA or 0) <= QA_TARGETS["lra_max"],
          f"{I} LUFS, true peak {TP} dBTP, LRA {LRA} ({mix_info.get('normalization')})")
    margin = mix_info.get("vo_music_margin_db")
    check("FQ-04", margin is None or margin >= QA_TARGETS["margin_min"], f"voice {margin} dB over ducked music" if margin is not None else "no music")
    blacks = black_frames(final, props)
    check("FQ-05", not blacks, "no black frames in pitch scenes" if not blacks else f"black at {blacks[:3]}")
    ok, detail = pixel_probes(final, props, scale)
    check("FQ-06", ok, detail)
    mock = vo["provider"] != "elevenlabs"
    check("FQ-07", True, "speech-to-text QA not run (mock voice)" if mock else "run `tms qa stt` for the live check", "warning")
    br = float(fmt.get("bit_rate") or 0)
    blo, bhi = QA_TARGETS["bitrate"]
    check("FQ-08", blo * (scale ** 2) <= br <= bhi, f"{br / 1e6:.1f} Mb/s", "warning")
    qa_frames = []
    qdir = rdir / "qa"
    qdir.mkdir(parents=True, exist_ok=True)
    marks = [(s["from"] + s["to"]) // 2 for s in props["scenes"]]
    contact_sheet(final, marks, rdir / "final_contact_sheet.png")
    for f in marks:
        out = qdir / f"f{f:05d}.png"
        wav.run([wav.ffmpeg(), "-v", "error", "-y", "-ss", f"{f / FPS + 0.001:.4f}", "-i", final, "-frames:v", "1", out])
        qa_frames.append(out.relative_to(pr.dir).as_posix())
    verdict = "pass" if all(c["ok"] for c in checks if c["severity"] == "error") else "fail"
    report = {"version": "1", "project_id": pr.id, "inputs": _h(pr, "render_props", "timeline", "music_manifest", "voiceover_manifest"),
              "output": {"file": "renders/final.mp4", "captions_file": "renders/captions.srt", "width": v.get("width", 0),
                         "height": v.get("height", 0), "fps": v.get("r_frame_rate", ""), "frames": frames,
                         "duration_s": round(float(fmt.get("duration") or 0), 3), "size_bytes": int(fmt.get("size") or 0)},
              "audio": {"integrated_lufs": I, "true_peak_dbtp": TP, "lra": LRA, "vo_music_margin_db": margin},
              "checks": checks, "qa_frames": qa_frames, "mock_audio": mock, "verdict": verdict}
    jsonio.write_json(pr.artifact_path("render_report"), report)
    return report


def summary(report: dict) -> str:
    lines = [f"final: {report['output']['file']} {report['output']['width']}x{report['output']['height']} "
             f"{report['output']['duration_s']}s  verdict={report['verdict'].upper()}"]
    for c in report["checks"]:
        lines.append(f"  [{'PASS' if c['ok'] else ('WARN' if c['severity'] == 'warning' else 'FAIL')}] {c['rule']} {c['detail']}")
    return "\n".join(lines)


def to_json(report: dict) -> str:
    return json.dumps(report, indent=2)
