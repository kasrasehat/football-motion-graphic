"""`tms intake template` — a brief skeleton with project defaults (the author fills the request specifics)."""
from __future__ import annotations

import json
from pathlib import Path

from tms import envfile, jsonio, manifest, theme
from tms.commands.common import add_project_arg, handled
from tms.state import project as P
from tms.state.project import ProjectError

MUSIC_MOOD = {
    "tactic": "modern broadcast tactics analysis bed, driving minimal electronic, 100 bpm, no vocals",
    "match_preview": "cinematic big-match build-up, pulsing strings and drums, 110 bpm, no vocals",
}


def _team(name: str, short: str, palette: str) -> dict:
    fill, ring, text = theme.kit_colours(palette) if palette.startswith("#") else theme.palette(palette)
    return {"name": name, "short": short, "fill": fill, "ring": ring, "text": text}


def template(pr: P.Project, home: str, away: str, home_short: str, away_short: str, home_pal: str, away_pal: str) -> dict:
    lo, hi, default = manifest.duration_range(pr.mode)
    caps = {k: int(envfile.get(k) or d) for k, d in
            (("TMS_MAX_TTS_CHARS", 6000), ("TMS_MAX_MUSIC_SECONDS", 200), ("TMS_MAX_API_FOOTBALL_CALLS_PER_PROJECT", 40))}
    brief = {
        "version": "1", "project_id": pr.id, "mode": pr.mode, "created_at": jsonio.now_iso(), "language": "en",
        "audience": "intermediate", "target_duration_s": default, "aspect": "16:9", "fps": 30,
        "teams": {"H": _team(home, home_short, home_pal), "A": _team(away, away_short, away_pal)},
        "focus_team": "H" if pr.mode == "tactic" else "both",
        "voice": {"voice_id": envfile.get("TMS_DEFAULT_VOICE_ID"), "model_id": "eleven_multilingual_v2",
                  "stability": 0.55, "similarity_boost": 0.8, "style": 0.15, "speed": 1.0, "seed": 1234},
        "music": {"source": "generate", "mood": MUSIC_MOOD[pr.mode], "file": None},
        "captions": True, "show_names": pr.mode == "match_preview",
        "budget": {"tts_chars_max": min(caps["TMS_MAX_TTS_CHARS"], int(default * 16 * 2)),
                   "music_s_max": min(caps["TMS_MAX_MUSIC_SECONDS"], default + 30),
                   "api_calls_max": caps["TMS_MAX_API_FOOTBALL_CALLS_PER_PROJECT"] if pr.mode == "match_preview" else 0},
    }
    if pr.mode == "tactic":
        brief["tactic"] = {"source": "user", "request_verbatim": "", "tactic_text": None, "topic": None}
    else:
        brief["match"] = {"query": "", "home": home, "away": away, "competition": "", "kickoff_utc": "",
                          "local_timezone": "", "venue": None, "fixture_id": None,
                          "resolution": {"method": "web", "resolved_at": jsonio.now_iso(), "sources": []}}
    return brief


@handled
def cmd_template(a):
    pr = P.load(a.project)
    try:
        doc = template(pr, a.home, a.away, a.home_short, a.away_short, a.home_colours, a.away_colours)
    except KeyError as e:
        raise ProjectError(f"unknown palette {e}; choose from {', '.join(theme.config()['palettes'])}, or give kit colours as #RRGGBB[,#RRGGBB]")
    except ValueError as e:
        raise ProjectError(str(e))
    if a.out:
        out = Path(a.out)
        if out.exists() and not a.force:
            raise ProjectError(f"{out} exists; pass --force to overwrite")
        jsonio.write_json(out, doc)
        print(f"wrote {out} — fill the request fields, then `.venv/Scripts/tms validate brief`")
    else:
        print(json.dumps(doc, indent=2))


def register(sub) -> None:
    p = sub.add_parser("intake", help="brief helpers")
    isub = p.add_subparsers(dest="intake_action", required=True)
    t = isub.add_parser("template", help="print/write a brief skeleton with defaults for the active project")
    add_project_arg(t)
    t.add_argument("--home", default="Home")
    t.add_argument("--away", default="Away")
    t.add_argument("--home-short", default="HOM")
    t.add_argument("--away-short", default="AWY")
    t.add_argument("--home-colours", default="red", help="palette name from config/themes.yaml")
    t.add_argument("--away-colours", default="blue")
    t.add_argument("--out", help="e.g. projects/<slug>/artifacts/brief.json")
    t.add_argument("--force", action="store_true")
    t.set_defaults(func=cmd_template)
