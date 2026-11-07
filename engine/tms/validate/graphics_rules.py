"""GS — graphic-scene rules on scene_plan."""
from __future__ import annotations

import re

from tms.props.builder import _graphic_data, resolve_ref
from tms.validate.registry import rule

REQUIRED = {
    "title_card": ["headline"], "text_card": ["headline"],
    "stat_compare": ["labels", "home", "away"], "form_guide": ["home", "away"], "h2h_strip": ["results"],
    "lineup_board": ["home", "away"], "team_news": ["home", "away"], "key_player_duel": ["battle"],
    "probability_bar": ["home", "draw", "away"], "scoreline_grid": ["scorelines"],
    "prediction_card": ["result", "scoreline", "confidence"], "pattern_compare": ["home", "away"],
}
DATA_TEMPLATES = set(REQUIRED) - {"title_card", "text_card"}


def _graphics(doc):
    return [s for s in doc["scenes"] if s["kind"] == "graphic"]


def _refs(scene):
    for slot, ref in scene["bind"].items():
        for r in (ref if isinstance(ref, list) else [ref]):
            yield slot, r


@rule("GS-01")
def required_slots(doc, ctx, p):
    for s in _graphics(doc):
        missing = [k for k in REQUIRED[s["template"]] if k not in s["bind"]]
        if missing:
            yield s["id"], f"{s['template']} needs bind slots {missing}"


@rule("GS-02")
def refs_resolve(doc, ctx, p):
    dossier, pred, analysis = ctx.other("match_dossier"), ctx.other("prediction"), ctx.other("match_analysis")
    kbs = {k["id"] for k in (analysis or {}).get("key_battles", [])}
    for s in _graphics(doc):
        for slot, r in _refs(s):
            if r.startswith("text:"):
                continue
            if r.startswith("KB"):
                if r not in kbs:
                    yield s["id"], f"{slot}: key battle {r} not in match_analysis"
            elif resolve_ref(r, dossier, pred) is None:
                yield s["id"], f"{slot}: {r!r} does not resolve to dossier/prediction data"


def _prob(v):
    return isinstance(v, (int, float)) and 0 <= v <= 1


@rule("GS-03")
def values_fit(doc, ctx, p):
    dossier, pred = ctx.other("match_dossier"), ctx.other("prediction")
    if dossier is None and pred is None:
        return
    for s in _graphics(doc):
        d = _graphic_data(s, dossier, pred, ctx.other("match_analysis"), ctx.other("tactic_spec"))
        t = s["template"]
        if t == "probability_bar" and not all(_prob(d.get(k)) for k in ("home", "draw", "away")):
            yield s["id"], "probability_bar values must be probabilities 0-1"
        if t == "form_guide" and not all(isinstance(d.get(k), list) and set(d[k]) <= {"W", "D", "L"} for k in ("home", "away")):
            yield s["id"], "form_guide needs W/D/L lists"
        if t == "lineup_board" and not all(isinstance(d.get(k), list) and len(d[k]) == 11 for k in ("home", "away")):
            yield s["id"], "lineup_board needs two 11-player line-ups"
        if t == "stat_compare" and not (isinstance(d.get("labels"), list) and len(d["labels"]) == len(d.get("home") or []) == len(d.get("away") or [])):
            yield s["id"], "stat_compare labels/home/away must have equal lengths"
        if t == "text_card" and "bullets" in d and not (isinstance(d["bullets"], list) and all(isinstance(b, str) for b in d["bullets"])):
            yield s["id"], "text_card bullets must be a list of text: labels or string facts (the card cannot show anything else)"
        if t == "pattern_compare" and not all(isinstance(d.get(k), dict) for k in ("home", "away")):
            yield s["id"], "pattern_compare home/away must each bind one split record, such as H.split.overall"


@rule("GS-04")
def tactic_mode_text_only(doc, ctx, p):
    if ctx.mode == "tactic":
        for s in _graphics(doc):
            if s["template"] in DATA_TEMPLATES:
                yield s["id"], f"{s['template']} needs match data; tactic explainers use title_card/text_card"


@rule("GS-05")
def readable_timing(doc, ctx, p):
    for s in _graphics(doc):
        L = s["length_s"] or 4.0
        if L < p["min_len"]:
            yield s["id"], f"graphic lasts {L} s (< {p['min_len']})"
        for r in s["reveals"]:
            if L - r["at"] < p["min_visible"]:
                yield s["id"], f"reveal {r['id']} at {r['at']} s leaves {L - r['at']:.1f} s on screen"


@rule("GS-06")
def prediction_shown(doc, ctx, p):
    if ctx.mode != "match_preview":
        return
    if not any(s["template"] in ("probability_bar", "prediction_card") for s in _graphics(doc)):
        yield "scenes", "a match preview must show its prediction (probability_bar or prediction_card)"


@rule("GS-07")
def no_literal_numbers(doc, ctx, p):
    for s in _graphics(doc):
        for slot, r in _refs(s):
            if r.startswith("text:") and re.search(r"\d", r) and not re.fullmatch(r"text:[^\d]*\d(-\d){1,4}[^\d]*", r):
                yield s["id"], f"{slot}: literal {r!r} contains a number — bind it to data instead"
