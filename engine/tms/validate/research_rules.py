"""WC / MD / MA rules."""
from __future__ import annotations

import fnmatch
from datetime import timedelta

from tms import jsonio
from tms.research import facts as FX
from tms.validate.registry import rule


# ------------------------------------------------------------------ web_claims
@rule("WC-01")
def sources_usable(doc, ctx, p):
    for c in doc["claims"]:
        for s in c["sources"]:
            if s["kind"] == "collector":
                yield c["id"], "collector sources come from `tms research scrape`, not from web_claims"
            if s["kind"] == "web" and FX.blocked(s["url"]):
                yield c["id"], f"{FX.domain(s['url'])} is not an acceptable source (social media / user content)"
            if jsonio.parse_iso(s["retrieved_at"]) > ctx.now + timedelta(minutes=5):
                yield c["id"], "retrieved_at is in the future"


@rule("WC-02")
def fact_keys_valid(doc, ctx, p):
    for c in doc["claims"]:
        if c["fact_key"]:
            prob = FX.type_problem(c["fact_key"], c["value"])
            if prob:
                yield c["id"], prob


@rule("WC-03")
def tiers_plausible(doc, ctx, p):
    for c in doc["claims"]:
        for s in c["sources"]:
            if s["kind"] == "web" and s.get("tier", 3) < FX.tier_of(s["url"]):
                yield c["id"], f"{FX.domain(s['url'])} declared tier {s['tier']} but is not on the tier list"


@rule("WC-04")
def ids_unique(doc, ctx, p):
    ids = [c["id"] for c in doc["claims"]]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        yield "claims", f"duplicate claim ids {dup}"


@rule("WC-05")
def rumours_labelled(doc, ctx, p):
    for c in doc["claims"]:
        if ".rumour." not in (c["fact_key"] or ""):
            continue
        if c["confidence"] == "high":
            yield c["id"], "a rumour is never high confidence"
        if not any(s["kind"] == "web" and FX.tier_of(s["url"]) <= 2 for s in c["sources"]):
            yield c["id"], "a rumour needs a tier 1 or 2 source"


# ------------------------------------------------------------------ match_dossier
@rule("MD-01")
def fact_types(doc, ctx, p):
    for key, f in doc["facts"].items():
        prob = FX.type_problem(key, f["value"])
        if prob:
            yield key, prob


@rule("MD-02")
def key_fact_support(doc, ctx, p):
    claims = {c["id"]: c for c in doc["claims"]}
    web = ctx.other("web_claims")
    flagged = {w["id"] for w in (web or {}).get("claims", []) if w.get("single_source")}
    for key, f in doc["facts"].items():
        sp = FX.spec(key) or {}
        if not sp.get("key"):
            continue
        cs = [claims[i] for i in f["claim_ids"] if i in claims]
        if any(c["origin"] == "api" for c in cs):
            continue
        domains = {FX.domain(s["url"]) for c in cs for s in c["sources"] if s["kind"] in ("web", "collector")}
        if len(domains) >= 2:
            continue
        if any(c["web_id"] in flagged for c in cs):
            continue
        yield key, f"key fact has only {len(domains)} independent source(s): add a second source or flag single_source"


@rule("MD-03")
def freshness(doc, ctx, p):
    built = jsonio.parse_iso(doc["built_at"])
    for key, f in doc["facts"].items():
        sp = FX.spec(key) or {}
        when = f["as_of"]
        if not when:
            continue
        age = built - jsonio.parse_iso(when)
        if sp.get("freshness") == "news" and age > timedelta(hours=p["news_h"]):
            yield key, f"news fact is {age.total_seconds() / 3600:.0f} h old (> {p['news_h']} h): refresh it"
        elif sp.get("freshness") == "stats" and age > timedelta(days=p["stats_days"]):
            yield key, f"stats fact is {age.days} days old (> {p['stats_days']})"


@rule("MD-04")
def conflicts_resolved(doc, ctx, p):
    for c in doc["conflicts"]:
        if not c["resolution"]:
            yield c["fact_key"], f"sources disagree ({', '.join(c['claim_ids'])}) — verify which is right and drop or correct the wrong claim"


@rule("MD-05")
def fixture_matches_brief(doc, ctx, p):
    brief = ctx.other("brief")
    if not brief or brief.get("mode") != "match_preview":
        return
    m = brief["match"]
    fx = doc["fixture"]
    if {fx["home"].lower(), fx["away"].lower()} != {m["home"].lower(), m["away"].lower()}:
        yield "fixture", f"dossier fixture {fx['home']} v {fx['away']} differs from the brief"
    dt = abs(jsonio.parse_iso(fx["kickoff_utc"]) - jsonio.parse_iso(m["kickoff_utc"]))
    if dt > timedelta(hours=p["ko_tol_h"]):
        yield "fixture/kickoff_utc", f"kickoff differs from the brief by {dt}"


@rule("MD-06")
def required_facts(doc, ctx, p):
    keys = list(doc["facts"])
    for pattern, level in FX.required_keys():
        present = any(fnmatch.fnmatchcase(k, pattern) for k in keys) if "*" in pattern else pattern in doc["facts"]
        if not present:
            yield pattern, f"missing fact {pattern}", "error" if level == "error" else "warning"


@rule("MD-07")
def coverage(doc, ctx, p):
    for cat, n in FX.config()["coverage_min"].items():
        if doc["coverage"].get(cat, 0) < n:
            yield f"coverage/{cat}", f"{doc['coverage'].get(cat, 0)} {cat} claims (need >= {n})"


# ------------------------------------------------------------------ match_analysis
def _known_refs(ctx) -> set[str]:
    d = ctx.other("match_dossier") or {"facts": {}, "claims": []}
    return set(d["facts"]) | {c["id"] for c in d["claims"]} | {c["web_id"] for c in d["claims"] if c["web_id"]}


@rule("MA-01")
def refs_exist(doc, ctx, p):
    known = _known_refs(ctx)
    items = [(f"sections/{s['id']}", r) for s in doc["sections"] for a in s["assertions"] for r in a["refs"]]
    items += [(kb["id"], r) for kb in doc["key_battles"] for r in kb["refs"]]
    items += [(tb["id"], r) for tb in doc["tactical_battles"] for r in tb["refs"]]
    items += [(f"adjust/{a['outcome']}", r) for a in doc["prediction_adjustments"] for r in a["refs"]]
    for where, r in items:
        if r not in known:
            yield where, f"ref {r!r} is not in the dossier"


@rule("MA-02")
def key_battles_valid(doc, ctx, p):
    spec = ctx.other("tactic_spec")
    dossier = ctx.other("match_dossier") or {"facts": {}}
    if not spec:
        return
    names = {pl["id"]: (pl.get("name") or "") for t in "HA" for pl in spec["teams"][t]["players"]}
    xi = {t: {str(x.get("name", "")).lower() for x in dossier["facts"].get(f"{t}.predicted_xi", {}).get("value", [])} for t in "HA"}
    for kb in doc["key_battles"]:
        h, a = kb["home_player"], kb["away_player"]
        if h[0] != "H" or a[0] != "A":
            yield kb["id"], "home_player must be an H id and away_player an A id"
        for pid in (h, a):
            if pid not in names:
                yield kb["id"], f"{pid} not in tactic_spec"
            elif xi[pid[0]] and names[pid].lower() not in xi[pid[0]]:
                yield kb["id"], f"{names[pid] or pid} is not in the predicted XI"


@rule("MA-03")
def battles_cite_principles(doc, ctx, p):
    spec = ctx.other("tactic_spec")
    if not spec:
        return
    known = {pr["id"] for pr in spec["principles"]}
    used = set()
    for tb in doc["tactical_battles"]:
        for pr in tb["principles"]:
            if pr not in known:
                yield tb["id"], f"principle {pr} not in tactic_spec"
            used.add(pr)
    for pr in known - used:
        yield "tactical_battles", f"tactic_spec principle {pr} is not used by any tactical battle"


@rule("MA-04")
def sections_complete(doc, ctx, p):
    ids = {s["id"] for s in doc["sections"]}
    for need in ("tactical", "outlook"):
        if need not in ids:
            yield "sections", f"missing section {need!r}"
    dossier = ctx.other("match_dossier") or {"facts": {}}
    single = [k for k, f in dossier["facts"].items() if f["status"] == "single_source" and (FX.spec(k) or {}).get("key")]
    if single and not doc["uncertainties"]:
        yield "uncertainties", f"key facts rest on a single source ({', '.join(single[:3])}) — say so in uncertainties"
