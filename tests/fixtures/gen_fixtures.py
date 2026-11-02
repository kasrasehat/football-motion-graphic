"""Regenerates the engine-built fixtures in tests/fixtures/artifacts/ deterministically.

Run:  .venv/Scripts/python tests/fixtures/gen_fixtures.py
The render_props fixture is a real 90-frame clip derived from tactic_spec.json (the M3 renderer test input).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent / "artifacts"
Z = "0" * 64
FRAMES = 90


def dump(name: str, doc: dict) -> None:
    (HERE / f"{name}.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")


def to_abs(team: str, xy: list[float]) -> tuple[float, float]:
    x, y = xy
    return (x, y) if team == "H" else (105 - x, 68 - y)


def smooth(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def main() -> None:
    spec = json.loads((HERE / "tactic_spec.json").read_text(encoding="utf-8"))
    players = {}
    for team in ("H", "A"):
        for p in spec["teams"][team]["players"]:
            players[p["id"]] = (team, p["number"], to_abs(team, p["pos"]))
    # H2 runs from the right half-space (38,50) into the pivot (40,39) between frames 15 and 75 (peak ~8 m/s).
    start_h2, end_h2 = (38.0, 50.0), players["H2"][2]
    tracks = {}
    for pid, (team, _, (x, y)) in players.items():
        arr = []
        for f in range(FRAMES):
            if pid == "H2":
                k = smooth((f - 15) / 60)
                px, py = start_h2[0] + (end_h2[0] - start_h2[0]) * k, start_h2[1] + (end_h2[1] - start_h2[1]) * k
            else:
                px = x + 0.25 * math.sin(f / 14 + len(pid))
                py = y + 0.25 * math.cos(f / 17 + len(pid))
            arr += [round(px * 100), round(py * 100)]
        tracks[pid] = arr
    h4 = players["H4"][2]
    ball = []
    for f in range(FRAMES):
        ball += [round((h4[0] + 0.8) * 100), round(h4[1] * 100), 11]
    camera = []
    for f in range(FRAMES):
        k = smooth((f - 40) / 30)
        cx, cy, w = 52.5 + (40 - 52.5) * k, 34 + (40 - 34) * k, 125.7 + (60 - 125.7) * k
        camera += [round(cx * 100), round(cy * 100), round(w * 100)]
    words = [("The", 20, 26), ("right-back", 26, 38), ("steps", 38, 46), ("inside.", 46, 60)]
    props = {
        "version": "1", "project_id": "fx-ifb-442", "inputs": {"timeline": Z, "choreography": Z, "brief": Z},
        "fps": 30, "width": 1920, "height": 1080, "durationInFrames": FRAMES, "orientation": "landscape",
        "theme": {
            "pitch": {"grass": "#2e7d32", "stripe": "#2b7330", "line": "#e8f5e9"},
            "teams": {"H": {"fill": "#c8102e", "ring": "#ffffff", "text": "#ffffff", "short": "RED", "name": "Reds"},
                      "A": {"fill": "#1d428a", "ring": "#ffffff", "text": "#ffffff", "short": "BLU", "name": "Blues"}},
            "accent": "#ffd54f", "warn": "#ff5252", "ink": "#ffffff", "panel": "#0b1a12",
        },
        "entities": [{"id": pid, "team": t, "number": n, "label": None} for pid, (t, n, _) in sorted(players.items())],
        "tracks": {"unit": "cm", "players": tracks, "ball": ball},
        "camera": camera,
        "pitchVisible": [[0, FRAMES]],
        "freeze": [[75, 82]],
        "scenes": [{"id": "S01", "kind": "pitch", "from": 0, "to": FRAMES, "title": "The full-back steps in"}],
        "overlays": [
            {"id": "N01", "kind": "run_arrow", "from": 5, "to": 70, "inAnim": {"anim": "draw", "frames": 10},
             "outAnim": {"anim": "fade", "frames": 8}, "geom": {"static": [[38, 50], [39.4, 44.5], [40, 39]]},
             "style": {"color": "accent", "dash": True, "fill": False, "curved": True}, "label": None},
            {"id": "N02", "kind": "ring", "from": 60, "to": FRAMES, "inAnim": {"anim": "pop", "frames": 8},
             "outAnim": {"anim": "none", "frames": 0}, "geom": {"static": [list(end_h2), list(players["H6"][2])]},
             "style": {"color": "accent", "dash": False, "fill": False}, "label": None},
            {"id": "N03", "kind": "label", "from": 62, "to": FRAMES, "inAnim": {"anim": "fade", "frames": 8},
             "outAnim": {"anim": "none", "frames": 0}, "geom": {"static": [[40, 33]]},
             "style": {"color": "ink", "dash": False, "fill": True}, "label": "2-man pivot"},
            {"id": "N04", "kind": "zone", "from": 30, "to": FRAMES, "inAnim": {"anim": "fade", "frames": 10},
             "outAnim": {"anim": "none", "frames": 0},
             "geom": {"static": [[61, 40], [63, 28], [75, 12], [75, 56]]},
             "style": {"color": "warn", "dash": False, "fill": True}, "label": "Between the lines"},
            {"id": "N05", "kind": "pass_line", "from": 70, "to": FRAMES, "inAnim": {"anim": "draw", "frames": 8},
             "outAnim": {"anim": "none", "frames": 0}, "geom": {"static": [list(h4), list(players["H6"][2])]},
             "style": {"color": "ink", "dash": True, "fill": False}, "label": None},
        ],
        "graphics": [],
        "captions": [{"from": 20, "to": 64, "lines": ["The right-back steps inside."],
                      "words": [{"t": w, "from": a, "to": b, "line": 0} for w, a, b in words], "place": "bottom"}],
        "titleCard": None,
        "endCard": None,
        "debug": {"overlay": False},
    }
    dump("render_props", props)

    dump("choreography", {
        "version": "1", "project_id": "fx-ifb-442", "inputs": {"scene_plan": Z, "tactic_spec": Z}, "hz": 30,
        "scenes": [{"id": "S01", "kind": "pitch", "tau0": 0.0, "len": 3.0, "transition": "continue", "holds": []}],
        "events": [], "actions": [],
        "possession": [{"tau0": 0.0, "tau1": 3.0, "state": "held", "by": "H4", "event": None}],
        "tracks": {"unit": "cm", "n": 2, "players": {"H4": [2500, 2200, 2500, 2200]}, "ball": [2580, 2200, 11, 2580, 2200, 11]},
        "overlays": [], "camera_keys": [{"tau": 0.0, "mode": "full"}], "aspect": "16:9",
        "camera_track": [5250, 3400, 12575, 5250, 3400, 12575],
        "report": {"errors": [], "warnings": []},
    })
    dump("voiceover_manifest", {
        "version": "1", "project_id": "fx-ifb-442", "inputs": {"narration_script": Z}, "provider": "mock_flite",
        "voice_id": "mock", "model_id": "flite", "chars_billed_total": 0,
        "clips": [{"id": "V01", "scene": "S01", "text": "Watch this.", "tts_text": "Watch this.", "request_hash": Z,
                   "cached": False, "file": "media/vo/V01.wav", "sample_rate": 48000, "samples": 48000, "duration_s": 1.0,
                   "onset_correction_s": 0.0, "chars_billed": 0,
                   "words": [{"i": 0, "display": "Watch", "spoken": "Watch", "start_s": 0.05, "end_s": 0.4},
                             {"i": 1, "display": "this.", "spoken": "this.", "start_s": 0.45, "end_s": 0.9}]}],
    })
    dump("timeline", {
        "version": "1", "project_id": "fx-ifb-442", "inputs": {"choreography": Z, "voiceover_manifest": Z}, "fps": 30, "sr": 48000,
        "frames": 120, "intro": {"from": 0, "to": 15}, "outro": {"from": 105, "to": 120},
        "scenes": [{"id": "S01", "from": 15, "to": 105, "vo": "V01", "warp": [[0.0, 0], [3.0, 90]]}],
        "vo": [{"id": "V01", "scene": "S01", "from": 21, "samples": 48000, "file": "media/vo/V01.wav"}],
        "words": [{"i": 0, "clip": "V01", "display": "Watch", "from": 22, "to": 33}, {"i": 1, "clip": "V01", "display": "this.", "from": 34, "to": 48}],
        "anchors": [],
        "captions": [{"id": "C01", "from": 22, "to": 60, "lines": ["Watch this."], "words": [0, 1], "place": "bottom"}],
        "duck": {"windows": [[21, 51]], "depth_db": -10, "attack_ms": 150, "release_ms": 450},
    })
    dump("music_manifest", {
        "version": "1", "project_id": "fx-ifb-442", "inputs": {"timeline": Z}, "source": "generate", "provider": "mock_synth",
        "request_hash": None, "cached": False, "raw_file": "media/music/raw.wav", "raw_duration_s": 8.0,
        "fitted_file": "media/music/bed_fit.wav", "samples": 192000, "body": {"start_s": 0.0, "end_s": 8.0},
        "fade_in_frames": 15, "fade_out_frames": 60, "plan_tier": None, "music_s_billed": 0,
    })
    dump("render_report", {
        "version": "1", "project_id": "fx-ifb-442", "inputs": {"render_props": Z},
        "output": {"file": "renders/final.mp4", "captions_file": "renders/captions.srt", "width": 1920, "height": 1080,
                   "fps": "30/1", "frames": 120, "duration_s": 4.0, "size_bytes": 123456},
        "audio": {"integrated_lufs": -14.1, "true_peak_dbtp": -1.6, "lra": 5.2, "vo_music_margin_db": 11.0},
        "checks": [{"rule": r, "ok": True, "severity": "warning" if r in ("FQ-07", "FQ-08") else "error", "detail": "ok"}
                   for r in ("FQ-01", "FQ-02", "FQ-03", "FQ-04", "FQ-05", "FQ-06", "FQ-07", "FQ-08")],
        "qa_frames": ["renders/qa/f0060.png"], "mock_audio": True, "verdict": "pass",
    })


if __name__ == "__main__":
    main()
