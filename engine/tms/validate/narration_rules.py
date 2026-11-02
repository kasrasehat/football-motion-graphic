"""NS — narration_script rules."""
from __future__ import annotations

import re

from tms.validate.registry import rule

RAW_ID = re.compile(r"\b([HA](1[01]|[1-9])|[ESNPTRWC]\d{1,2}|KB\d|TB\d)\b")
FORMATION = re.compile(r"\b\d(-\d){1,4}\b")
FILLER = re.compile(r"\b(basically|actually|really|very|kind of|sort of|just)\b", re.I)
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
NUMBER = re.compile(r"(?<![\w-])(\d+(?:\.\d+)?)(%?)(?![\w-])")


def words(text: str) -> list[str]:
    return [w for w in re.split(r"\s+", text.strip()) if w]


def sentences(text: str) -> list[str]:
    return [s for s in SENT_SPLIT.split(text.strip()) if s]


def estimate_s(text: str, p) -> float:
    if not text.strip():
        return 0.0
    return len(words(text)) / p["wps"] + p["pause"] * max(len(sentences(text)) - 1, 0)


def _spoken(doc):
    return [ln for ln in doc["lines"] if not ln["silent"]]


@rule("NS-01")
def one_line_per_scene(doc, ctx, p):
    plan = ctx.other("scene_plan")
    if plan:
        want = [s["id"] for s in plan["scenes"]]
        got = [ln["scene"] for ln in doc["lines"]]
        if got != want:
            yield "lines", f"lines are for scenes {got}; scene_plan has {want} (one line each, same order)"
    silent = sum(1 for ln in doc["lines"] if ln["silent"])
    if silent > p["max_silent"]:
        yield "lines", f"{silent} silent lines (max {p['max_silent']})"
    for ln in doc["lines"]:
        if ln["silent"] and ln["text"].strip():
            yield ln["scene"], "silent line must have empty text"


@rule("NS-02")
def no_raw_ids(doc, ctx, p):
    for ln in _spoken(doc):
        m = RAW_ID.search(ln["text"])
        if m:
            yield ln["scene"], f"raw id {m.group(0)!r} in spoken text — say the role or name instead"


@rule("NS-03")
def speech_fits(doc, ctx, p):
    choreo = ctx.other("choreography")
    lens = {s["id"]: s["len"] for s in choreo["scenes"]} if choreo else {}
    total = 0.0
    for ln in _spoken(doc):
        est = estimate_s(ln["text"], p)
        total += est
        L = lens.get(ln["scene"])
        if L is not None and est > p["scene_factor"] * L + p["scene_slack"]:
            yield ln["scene"], f"~{est:.1f} s of speech for a {L:.1f} s scene (max {p['scene_factor'] * L + p['scene_slack']:.1f} s): cut words or lengthen the scene"
    brief = ctx.other("brief")
    if brief:
        tgt = brief["target_duration_s"]
        if not p["total_lo"] * tgt <= total <= p["total_hi"] * tgt:
            yield "lines", f"~{total:.0f} s of narration for a {tgt} s video (allowed {p['total_lo']}-{p['total_hi']} x)"


@rule("NS-04")
def hook_short(doc, ctx, p):
    sp = _spoken(doc)
    if sp:
        first = sentences(sp[0]["text"])[0]
        if len(words(first)) > p["max_words"]:
            yield sp[0]["scene"], f"hook has {len(words(first))} words (max {p['max_words']}): open with a punchier line"


@rule("NS-05")
def sentence_lengths(doc, ctx, p):
    for ln in _spoken(doc):
        if len(words(ln["text"])) > p["line"]:
            yield ln["scene"], f"line has {len(words(ln['text']))} words (max {p['line']})"
        for s in sentences(ln["text"]):
            if len(words(s)) > p["sentence"]:
                yield ln["scene"], f"sentence of {len(words(s))} words (max {p['sentence']}): split it"


def _scene_refs(plan, scene_id) -> set[str]:
    s = next((x for x in plan["scenes"] if x["id"] == scene_id), None)
    if s is None:
        return set()
    refs = set()
    if s["kind"] == "graphic":
        return {r["id"] for r in s.get("reveals", [])}
    counters: dict = {}
    for a in s.get("actions", []):
        if "id" in a:
            refs.add(a["id"])
        if a["type"] in ("move", "carry", "press", "mark", "duel"):
            pid = a["player"] if a["type"] != "duel" else a["players"][0]
            key = (pid, a["type"])
            counters[key] = counters.get(key, 0) + 1
            refs.add(f"{pid}@{a['type']}#{counters[key]}")
    return refs


@rule("NS-06")
def anchors_valid(doc, ctx, p):
    plan = ctx.other("scene_plan")
    for ln in doc["lines"]:
        toks = [w.lower() for w in words(ln["text"])]
        for an in ln["anchors"]:
            if toks.count(an["word"].lower()) < an["occurrence"]:
                yield ln["scene"], f"anchor word {an['word']!r} (occurrence {an['occurrence']}) not in the line"
            if plan is not None:
                base = an["ref"].rsplit(".", 1)[0] if an["ref"].endswith((".start", ".end")) else an["ref"]
                if base not in _scene_refs(plan, ln["scene"]):
                    yield ln["scene"], f"anchor ref {an['ref']!r} does not exist in scene {ln['scene']}"
    if plan is not None:
        key = [s["id"] for s in plan["scenes"] if s["kind"] == "pitch" and s["purpose"] in ("explain", "demonstrate", "exploit", "battle")]
        if key:
            anchored = sum(1 for ln in doc["lines"] if ln["scene"] in key and ln["anchors"])
            if anchored / len(key) < p["share"]:
                yield "lines", f"only {anchored}/{len(key)} key scenes anchor narration to on-screen events"


@rule("NS-07")
def pronunciations_used(doc, ctx, p):
    text = " ".join(ln["text"] for ln in _spoken(doc))
    for k in doc["pronunciations"]:
        if not re.search(rf"\b{re.escape(k)}\b", text):
            yield f"pronunciations/{k}", f"{k!r} never occurs in the narration"


@rule("NS-08")
def formations_spelled(doc, ctx, p):
    for ln in _spoken(doc):
        m = FORMATION.search(ln["text"])
        if m:
            yield ln["scene"], f"write {m.group(0)!r} as words for the voice"


@rule("NS-09")
def no_filler(doc, ctx, p):
    for ln in _spoken(doc):
        m = FILLER.search(ln["text"])
        if m:
            yield ln["scene"], f"filler word {m.group(0)!r}"


def _resolve(ref: str, ctx):
    if ref.startswith("prediction."):
        cur = ctx.other("prediction")
        for part in ref.split(".")[1:]:
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
        return cur
    dossier = ctx.other("match_dossier")
    if dossier and ref in dossier["facts"]:
        return dossier["facts"][ref]["value"]
    return None


def _matches(spoken: float, pct: bool, value, p) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    cands = [float(value)]
    if 0 <= value <= 1:
        cands.append(value * 100)  # probabilities spoken as percentages
    tol = p["pct_tol"] if pct else max(p["abs_tol"], abs(float(value)) * 0.005)
    return any(abs(spoken - c) <= tol + 0.5 * (pct or c >= 10) for c in cands)


@rule("NS-10")
def numbers_bound(doc, ctx, p):
    if ctx.mode != "match_preview":
        return
    for ln in _spoken(doc):
        declared = {n["text"]: n["ref"] for n in ln.get("numbers", [])}
        for m in NUMBER.finditer(ln["text"]):
            tok = m.group(0)
            ref = declared.get(tok) or declared.get(m.group(1))
            if ref is None:
                yield ln["scene"], f"number {tok!r} is not declared in `numbers` with its source ref"
                continue
            val = _resolve(ref, ctx)
            if val is None:
                yield ln["scene"], f"{tok!r} refers to {ref!r}, which does not exist"
            elif not _matches(float(m.group(1)), bool(m.group(2)), val, p):
                yield ln["scene"], f"{tok!r} does not match {ref} = {val}"
