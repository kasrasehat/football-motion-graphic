"""TS — tactic_spec rules."""
from __future__ import annotations

from tms.tactic import formations as F
from tms.tactic.geometry import LENGTH, WIDTH, dist, parse_formation, side_of_role, to_abs
from tms.validate.registry import rule

IDS = {t: {f"{t}{i}" for i in range(1, 12)} for t in "HA"}
LEFT_WIDE = {"LB", "LWB", "LM", "LW"}
RIGHT_WIDE = {"RB", "RWB", "RM", "RW"}


def _players(doc, team):
    return doc["teams"][team]["players"]


def _all_ids(doc):
    return {p["id"] for t in "HA" for p in _players(doc, t)}


def _team_of(pid: str) -> str:
    return pid[0]


@rule("TS-01")
def ids_exact(doc, ctx, p):
    for t in "HA":
        got = [x["id"] for x in _players(doc, t)]
        if set(got) != IDS[t] or len(got) != 11:
            yield f"teams/{t}", f"ids must be {t}1-{t}11 exactly once; got {sorted(got)}"


@rule("TS-02")
def one_goalkeeper(doc, ctx, p):
    for t in "HA":
        gks = [x for x in _players(doc, t) if x["role"] == "GK"]
        line0 = [x for x in _players(doc, t) if x["line"] == 0]
        if len(gks) != 1 or len(line0) != 1 or gks[0]["line"] != 0:
            yield f"teams/{t}", "exactly one GK, alone on line 0"


@rule("TS-03")
def formation_sums(doc, ctx, p):
    for t in "HA":
        for key in ("formation_base", "formation_phase"):
            f = doc["teams"][t][key]
            if sum(parse_formation(f)) != 10:
                yield f"teams/{t}/{key}", f"{f} does not sum to 10 outfield players"


@rule("TS-04")
def lines_match_formation(doc, ctx, p):
    for t in "HA":
        counts = parse_formation(doc["teams"][t]["formation_phase"])
        for line, n in enumerate(counts, 1):
            got = sum(1 for x in _players(doc, t) if x["line"] == line)
            if got != n:
                yield f"teams/{t}", f"line {line} has {got} players but formation_phase says {n}"
        extra = [x["id"] for x in _players(doc, t) if x["line"] > len(counts)]
        if extra:
            yield f"teams/{t}", f"players on lines beyond the formation: {extra}"


@rule("TS-05")
def lines_ordered(doc, ctx, p):
    for t in "HA":
        means = {}
        for x in _players(doc, t):
            means.setdefault(x["line"], []).append(x["pos"][0])
        lines = sorted(means)
        for a, b in zip(lines, lines[1:]):
            ma, mb = sum(means[a]) / len(means[a]), sum(means[b]) / len(means[b])
            if mb < ma + p["min_gap_m"]:
                yield f"teams/{t}", f"line {b} (mean x {mb:.1f}) not >= {p['min_gap_m']} m ahead of line {a} (mean x {ma:.1f})"


@rule("TS-06")
def sides_ordered(doc, ctx, p):
    rank = {"L": 0, "C": 1, "R": 2}
    for t in "HA":
        by_line = {}
        for x in _players(doc, t):
            by_line.setdefault(x["line"], []).append(x)
        for line, ps in by_line.items():
            for a in ps:
                for b in ps:
                    ra, rb = rank[side_of_role(a["role"])], rank[side_of_role(b["role"])]
                    if ra < rb and not a["pos"][1] < b["pos"][1]:
                        yield f"teams/{t}/line {line}", f"{a['id']} ({a['role']}, y={a['pos'][1]}) should be left of {b['id']} ({b['role']}, y={b['pos'][1]})"


@rule("TS-07")
def role_bands(doc, ctx, p):
    named = {pid for pr in doc["principles"] for pid in pr["players"]}
    for t in "HA":
        for x in _players(doc, t):
            if x["id"] in named or x.get("note"):
                continue
            y = x["pos"][1]
            if x["role"] in LEFT_WIDE and y > p["left_max"]:
                yield f"{x['id']}", f"{x['role']} at y={y} is far from the left flank (> {p['left_max']})"
            elif x["role"] in RIGHT_WIDE and y < p["right_min"]:
                yield f"{x['id']}", f"{x['role']} at y={y} is far from the right flank (< {p['right_min']})"
            elif x["role"] not in LEFT_WIDE | RIGHT_WIDE and side_of_role(x["role"]) == "C" and not p["central_min"] <= y <= p["central_max"]:
                yield f"{x['id']}", f"central role {x['role']} at y={y} outside [{p['central_min']}, {p['central_max']}]"


@rule("TS-08")
def in_bounds(doc, ctx, p):
    m = p["margin"]
    for t in "HA":
        for x in _players(doc, t):
            px, py = x["pos"]
            if not (m <= px <= LENGTH - m and m <= py <= WIDTH - m):
                yield x["id"], f"position {x['pos']} outside the pitch"


@rule("TS-09")
def spacing(doc, ctx, p):
    ps = [(x["id"], t, to_abs(t, tuple(x["pos"]))) for t in "HA" for x in _players(doc, t)]
    for i, (a, ta, pa) in enumerate(ps):
        for b, tb, pb in ps[i + 1:]:
            d = dist(pa, pb)
            if ta == tb and d < p["teammates_min"]:
                yield f"{a}/{b}", f"teammates {a} and {b} only {d:.1f} m apart (< {p['teammates_min']})"
            elif ta != tb and d < p["opponents_min"]:
                yield f"{a}/{b}", f"{a} and {b} overlap ({d:.1f} m < {p['opponents_min']})"
            elif ta != tb and d < p["opponents_warn"]:
                yield f"{a}/{b}", f"{a} and {b} very close ({d:.1f} m) — tokens will touch", "warning"


@rule("TS-10")
def goalkeeper_depth(doc, ctx, p):
    for t in "HA":
        for x in _players(doc, t):
            if x["role"] == "GK":
                if x["pos"][0] > p["max_x"]:
                    yield x["id"], f"GK {x['pos'][0]} m from goal (> {p['max_x']})"
                elif x["pos"][0] > p["warn_x"]:
                    yield x["id"], f"GK {x['pos'][0]} m from goal (> {p['warn_x']})", "warning"


@rule("TS-11")
def numbers_unique(doc, ctx, p):
    for t in "HA":
        nums = [x["number"] for x in _players(doc, t)]
        dup = sorted({n for n in nums if nums.count(n) > 1})
        if dup:
            yield f"teams/{t}", f"duplicate shirt numbers {dup}"


@rule("TS-12")
def principle_count(doc, ctx, p):
    brief = ctx.other("brief")
    target = brief["target_duration_s"] if brief else 75
    hi = max(2, min(p["max"], target // p["seconds_per_principle"]))
    n = len(doc["principles"])
    if not 1 <= n <= hi:
        yield "principles", f"{n} principles for a {target} s video; allowed 1..{hi}"


def possession_team(doc) -> str | None:
    if doc["focus_team"] == "both":
        return None
    in_poss = doc["phase"] in F.config()["in_possession_phases"]
    return doc["focus_team"] if in_poss else ("A" if doc["focus_team"] == "H" else "H")


@rule("TS-13")
def holder_matches_phase(doc, ctx, p):
    want = possession_team(doc)
    holder = doc["ball"]["holder"]
    if want is not None and _team_of(holder) != want:
        yield "ball/holder", f"phase {doc['phase']} with focus {doc['focus_team']} means team {want} has the ball, not {holder}"


@rule("TS-14")
def defending_block(doc, ctx, p):
    dfd = "A" if _team_of(doc["ball"]["holder"]) == "H" else "H"
    out = [x for x in _players(doc, dfd) if x["role"] != "GK"]
    xs, ys = [x["pos"][0] for x in out], [x["pos"][1] for x in out]
    depth, width = max(xs) - min(xs), max(ys) - min(ys)
    if not p["depth_min"] <= depth <= p["depth_max"]:
        yield f"teams/{dfd}", f"defending block depth {depth:.1f} m outside [{p['depth_min']}, {p['depth_max']}]"
    if not p["width_min"] <= width <= p["width_max"]:
        yield f"teams/{dfd}", f"defending block width {width:.1f} m outside [{p['width_min']}, {p['width_max']}]"


@rule("TS-15")
def offside_snapshot(doc, ctx, p):
    att = _team_of(doc["ball"]["holder"])
    dfd = "A" if att == "H" else "H"
    holder = next(x for x in _players(doc, att) if x["id"] == doc["ball"]["holder"])
    ball_x = holder["pos"][0]  # team-normalized frame of the attacking team: attacking +x
    def_xs = sorted((LENGTH - x["pos"][0] for x in _players(doc, dfd)), reverse=True)  # defenders in attacker frame
    second_last = def_xs[1]
    for x in _players(doc, att):
        if x["id"] == holder["id"]:
            continue
        px = x["pos"][0]
        if px > LENGTH / 2 and px > ball_x and px > second_last + 0.1:
            yield x["id"], f"{x['id']} is offside (x={px:.1f} beyond second-last defender {second_last:.1f})"


@rule("TS-16")
def cross_refs(doc, ctx, p):
    ids = _all_ids(doc)
    pids = {pr["id"] for pr in doc["principles"]}
    wids = {w["id"] for w in doc["weaknesses"]}
    for kind in ("principles", "triggers", "strengths", "weaknesses"):
        for item in doc[kind]:
            for pid in item.get("players", []):
                if pid not in ids:
                    yield f"{kind}/{item['id']}", f"unknown player {pid}"
            for pr in item.get("principles", []):
                if pr not in pids:
                    yield f"{kind}/{item['id']}", f"unknown principle {pr}"
    for c in doc["counters"]:
        if c["targets"] not in wids:
            yield f"counters/{c['id']}", f"targets unknown weakness {c['targets']}"
    if doc["ball"]["holder"] not in ids:
        yield "ball/holder", f"unknown player {doc['ball']['holder']}"
    for kind in ("principles", "triggers", "strengths", "weaknesses", "counters"):
        seen = [i["id"] for i in doc[kind]]
        if len(seen) != len(set(seen)):
            yield kind, f"duplicate ids in {kind}"


@rule("TS-17")
def focus_matches_brief(doc, ctx, p):
    brief = ctx.other("brief")
    if brief and brief["focus_team"] != doc["focus_team"]:
        yield "focus_team", f"focus_team {doc['focus_team']} differs from the brief ({brief['focus_team']})"
