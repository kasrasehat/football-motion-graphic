"""BR — brief rules."""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from tms import jsonio, manifest, proc
from tms.validate.colour import contrast_ratio, delta_e2000
from tms.validate.registry import rule


@rule("BR-01")
def duration_in_mode_range(doc, ctx, p):
    lo, hi, _ = manifest.duration_range(doc["mode"])
    if not lo <= doc["target_duration_s"] <= hi:
        yield "target_duration_s", f"{doc['target_duration_s']} s outside {doc['mode']} range [{lo}, {hi}]"


@rule("BR-02")
def team_colours_distinct(doc, ctx, p):
    de = delta_e2000(doc["teams"]["H"]["fill"], doc["teams"]["A"]["fill"])
    if de < p["min_delta_e"]:
        yield "teams", f"home/away fills too similar: dE2000={de:.1f} < {p['min_delta_e']}"


@rule("BR-03")
def number_contrast(doc, ctx, p):
    for t in ("H", "A"):
        s = doc["teams"][t]
        cr = contrast_ratio(s["fill"], s["text"])
        if cr < p["min_contrast"]:
            yield f"teams/{t}", f"text {s['text']} on fill {s['fill']}: contrast {cr:.2f} < {p['min_contrast']}"


@rule("BR-04")
def short_codes_distinct(doc, ctx, p):
    if doc["teams"]["H"]["short"] == doc["teams"]["A"]["short"]:
        yield "teams", "home and away short codes are identical"


@rule("BR-05")
def tactic_source_consistent(doc, ctx, p):
    if doc["mode"] != "tactic":
        return
    t = doc["tactic"]
    if t["source"] == "user" and len((t["tactic_text"] or "").strip()) < p["min_tactic_text"]:
        yield "tactic/tactic_text", f"source=user requires the user's tactic text (>= {p['min_tactic_text']} chars)"
    if t["source"] == "ai" and not (t["topic"] or "").strip():
        yield "tactic/topic", "source=ai requires a topic"


@rule("BR-06")
def match_fixture_sane(doc, ctx, p):
    if doc["mode"] != "match_preview":
        return
    m = doc["match"]
    if m["home"].strip().lower() == m["away"].strip().lower():
        yield "match", "home and away are the same team"
    ko = jsonio.parse_iso(m["kickoff_utc"])
    ref = jsonio.parse_iso(m["resolution"]["resolved_at"])
    if not (ref - timedelta(hours=p["before_h"]) <= ko <= ref + timedelta(days=p["after_days"])):
        yield "match/kickoff_utc", f"kickoff {m['kickoff_utc']} not within -{p['before_h']}h/+{p['after_days']}d of resolution time"


@rule("BR-07")
def music_file_ok(doc, ctx, p):
    mu = doc["music"]
    if mu["source"] != "file":
        return
    if not mu["file"]:
        yield "music/file", "music.source=file but no file given"
        return
    f = Path(mu["file"])
    if not f.is_absolute() and ctx.project_dir is not None:
        f = ctx.project_dir / f
    if not f.is_file():
        yield "music/file", f"music file not found: {mu['file']}"
        return
    r = proc.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(f)])
    try:
        dur = float(json.loads(r.out)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError):
        yield "music/file", "music file does not decode (ffprobe)"
        return
    if dur < p["min_s"]:
        yield "music/file", f"music file is {dur:.1f} s < {p['min_s']} s"


@rule("BR-08")
def budget_covers_duration(doc, ctx, p):
    need = int(doc["target_duration_s"] * p["chars_per_s"] * p["margin"])
    if doc["budget"]["tts_chars_max"] < need:
        yield "budget/tts_chars_max", f"{doc['budget']['tts_chars_max']} chars may not cover {doc['target_duration_s']} s (~{need})"


@rule("BR-09")
def match_resolution_evidence(doc, ctx, p):
    if doc["mode"] != "match_preview":
        return
    r = doc["match"]["resolution"]
    if r["method"] == "api" and doc["match"]["fixture_id"] is None:
        yield "match/fixture_id", "resolution.method=api requires fixture_id"
    if r["method"] == "web" and len(set(r["sources"])) < p["web_min_sources"]:
        yield "match/resolution/sources", f"web resolution needs >= {p['web_min_sources']} distinct sources"


@rule("BR-10")
def project_id_matches(doc, ctx, p):
    if ctx.project_dir is not None and doc["project_id"] != Path(ctx.project_dir).name:
        yield "project_id", f"project_id {doc['project_id']!r} != project folder {Path(ctx.project_dir).name!r}"


@rule("BR-11")
def mode_matches_project(doc, ctx, p):
    if ctx.mode is not None and doc["mode"] != ctx.mode:
        yield "mode", f"brief.mode={doc['mode']!r} but the project mode is {ctx.mode!r}"
