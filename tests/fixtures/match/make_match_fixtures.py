"""Builds the match-preview fixtures (fx-match) from SYNTHETIC API-Football responses + web claims.
Club names are real; every player name and number below is FICTIONAL test data, never published.

Run: .venv/Scripts/python tests/fixtures/match/make_match_fixtures.py
Writes: tests/fixtures/match/api_cassette.json, tests/fixtures/artifacts/{web_claims,match_dossier}.json
"""
from __future__ import annotations

import json
from pathlib import Path

from tms.research import api_football as AF
from tms.research.dossier import merge

HERE = Path(__file__).resolve().parent
ART = HERE.parent / "artifacts"
FID, RMA, ARS, LEAGUE, SEASON = 1234567, 541, 42, 2, 2026
T0 = "2026-11-02T12:10:00Z"

H_XI = [("Navarro", 1, "G"), ("Ortega", 2, "D"), ("Ibarra", 4, "D"), ("Molina", 22, "D"), ("Castro", 23, "D"),
        ("Serrano", 6, "M"), ("Vidal", 8, "M"), ("Delgado", 5, "M"), ("Romero", 11, "F"), ("Fuentes", 9, "F"), ("Herrera", 7, "F")]
A_XI = [("Hughes", 1, "G"), ("Clarke", 2, "D"), ("Walsh", 6, "D"), ("Gardner", 4, "D"), ("Lowe", 3, "D"),
        ("Fletcher", 41, "M"), ("Bennett", 8, "M"), ("Doyle", 29, "M"), ("Marsh", 7, "F"), ("Shaw", 9, "F"), ("Kerr", 11, "F")]


def fx(fid, date, home, away, gh, ga, league="UEFA Champions League", round_="League Stage - 4"):
    return {"fixture": {"id": fid, "referee": "A. Referee", "timezone": "UTC", "date": date,
                        "venue": {"id": 1456, "name": "Estadio Santiago Bernabeu", "city": "Madrid"}, "status": {"short": "NS"}},
            "league": {"id": LEAGUE, "name": league, "season": SEASON, "round": round_},
            "teams": {"home": {"id": home[0], "name": home[1]}, "away": {"id": away[0], "name": away[1]}},
            "goals": {"home": gh, "away": ga}}


def wrap(resp):
    return {"get": "", "parameters": {}, "errors": [], "results": len(resp) if isinstance(resp, list) else 1, "paging": {"current": 1, "total": 1}, "response": resp}


def stats(gf, ga, gfh, gah, gfa, gaa, cs, formation):
    return {"goals": {"for": {"average": {"home": str(gfh), "away": str(gfa), "total": str(gf)}},
                      "against": {"average": {"home": str(gah), "away": str(gaa), "total": str(ga)}}},
            "clean_sheet": {"total": cs}, "lineups": [{"formation": formation, "played": 9}, {"formation": "4-4-2", "played": 2}]}


def coaches(team: int, current: str) -> list:
    """Shape of the real /coachs answer: past managers come first and only the current one has an open spell."""
    return [{"name": "P. Predecessor", "career": [{"team": {"id": team}, "start": "2015-07-01", "end": "2021-05-01"}]},
            {"name": current, "career": [{"team": {"id": team}, "start": "2021-06-01", "end": None},
                                         {"team": {"id": 1}, "start": "2010-07-01", "end": "2015-06-30"}]}]


def cassette() -> dict:
    madrid, arsenal = (RMA, "Real Madrid"), (ARS, "Arsenal")
    other = [(529, "Barcelona"), (530, "Atletico Madrid"), (40, "Liverpool"), (50, "Manchester City"), (33, "Manchester United")]
    last_h = [fx(9001 + i, f"2026-10-{5 + 5 * i:02d}T19:00:00+00:00", madrid if i % 2 else other[i], other[i] if i % 2 else madrid, *g)
              for i, g in enumerate([(2, 1), (3, 1), (1, 1), (2, 0), (4, 2)])]
    last_a = [fx(9101 + i, f"2026-10-{4 + 5 * i:02d}T15:00:00+00:00", arsenal if i % 2 == 0 else other[i], other[i] if i % 2 == 0 else arsenal, *g)
              for i, g in enumerate([(2, 0), (1, 1), (3, 1), (0, 1), (2, 2)])]
    h2h = [fx(8001, "2025-04-16T19:00:00+00:00", madrid, arsenal, 1, 2), fx(8002, "2025-04-08T19:00:00+00:00", arsenal, madrid, 3, 0),
           fx(8003, "2006-03-08T19:45:00+00:00", arsenal, madrid, 0, 0)]
    standings = [{"league": {"standings": [[
        {"rank": 3, "team": {"id": RMA, "name": "Real Madrid"}, "points": 9, "all": {"played": 3}},
        {"rank": 5, "team": {"id": ARS, "name": "Arsenal"}, "points": 7, "all": {"played": 3}}]]}}]
    lineups: list = []  # not published yet (more than an hour before kick-off)
    injuries = [{"player": {"name": "Castillo", "type": "Missing Fixture", "reason": "Knee Injury"}, "team": {"id": RMA}},
                {"player": {"name": "Porter", "type": "Questionable", "reason": "Hamstring"}, "team": {"id": ARS}}]
    odds = [{"bookmakers": [{"bets": [{"name": "Match Winner", "values": [{"value": "Home", "odd": "2.05"}, {"value": "Draw", "odd": "3.60"},
                                                                          {"value": "Away", "odd": "3.40"}]}]}]}]
    return {
        "/fixtures?id=1234567": wrap([fx(FID, "2026-11-02T20:00:00+00:00", madrid, arsenal, None, None)]),
        f"/fixtures?last=5&team={RMA}": wrap(last_h), f"/fixtures?last=5&team={ARS}": wrap(last_a),
        f"/teams/statistics?league={LEAGUE}&season={SEASON}&team={RMA}": wrap(stats(2.3, 1.0, 2.6, 0.8, 2.0, 1.2, 4, "4-3-3")),
        f"/teams/statistics?league={LEAGUE}&season={SEASON}&team={ARS}": wrap(stats(1.9, 0.9, 2.2, 0.6, 1.6, 1.2, 5, "4-3-3")),
        f"/coachs?team={RMA}": wrap(coaches(RMA, "M. Coach")), f"/coachs?team={ARS}": wrap(coaches(ARS, "A. Manager")),
        f"/standings?league={LEAGUE}&season={SEASON}": wrap(standings),
        f"/fixtures/headtohead?h2h={RMA}-{ARS}": wrap(h2h),
        f"/injuries?fixture={FID}": wrap(injuries), f"/fixtures/lineups?fixture={FID}": wrap(lineups),
        f"/odds?bookmaker=8&fixture={FID}": wrap(odds),
        "/teams?search=Real Madrid": wrap([{"team": {"id": RMA, "name": "Real Madrid"}}]),
        "/teams?search=Arsenal": wrap([{"team": {"id": ARS, "name": "Arsenal"}}]),
        f"/fixtures/headtohead?from=2026-11-02&h2h={RMA}-{ARS}&to=2026-11-03": wrap([fx(FID, "2026-11-02T20:00:00+00:00", madrid, arsenal, None, None)]),
    }


class CassetteClient(AF.Client):
    def __init__(self, cas: dict):
        self.cas, self.calls, self.key = cas, 0, "cassette"

    def get(self, path, **params):
        key = path + ("?" + "&".join(f"{k}={params[k]}" for k in sorted(params)) if params else "")
        self.calls += 1
        if key not in self.cas:
            raise AF.ApiError(f"cassette has no {key}")
        return self.cas[key]


def web_claims() -> dict:
    def src(url, publisher, tier, quote, t="2026-11-02T12:15:00Z"):
        return {"kind": "web", "url": url, "title": publisher + " preview", "publisher": publisher, "tier": tier, "quote": quote, "retrieved_at": t}
    xi = lambda team: [{"name": n, "number": k, "position": pos} for n, k, pos in (H_XI if team == "H" else A_XI)]
    claims = [
        {"id": "W-001", "fact_key": "H.xg_for_avg", "category": "xg", "statement": "Real Madrid create 2.1 xG per match.", "value": 2.1,
         "unit": "xG/match", "as_of": "2026-11-01T00:00:00Z", "confidence": "medium",
         "sources": [src("https://fbref.com/en/squads/rma", "FBref", 2, "xG per 90: 2.10")]},
        {"id": "W-002", "fact_key": "H.xg_against_avg", "category": "xg", "statement": "Real Madrid concede 1.0 xG per match.", "value": 1.0,
         "unit": "xG/match", "as_of": "2026-11-01T00:00:00Z", "confidence": "medium",
         "sources": [src("https://fbref.com/en/squads/rma", "FBref", 2, "xGA per 90: 1.00")]},
        {"id": "W-003", "fact_key": "A.xg_for_avg", "category": "xg", "statement": "Arsenal create 1.8 xG per match.", "value": 1.8,
         "unit": "xG/match", "as_of": "2026-11-01T00:00:00Z", "confidence": "medium",
         "sources": [src("https://fbref.com/en/squads/ars", "FBref", 2, "xG per 90: 1.80")]},
        {"id": "W-004", "fact_key": "A.xg_against_avg", "category": "xg", "statement": "Arsenal concede 0.8 xG per match.", "value": 0.8,
         "unit": "xG/match", "as_of": "2026-11-01T00:00:00Z", "confidence": "medium",
         "sources": [src("https://fbref.com/en/squads/ars", "FBref", 2, "xGA per 90: 0.80")]},
        {"id": "W-005", "fact_key": "H.tactics.build_up", "category": "tactics", "statement": "Madrid build in a 4-3-3 and attack quickly in transition.",
         "value": "4-3-3 build-up, fast transitions", "unit": None, "as_of": None, "confidence": "high",
         "sources": [src("https://theanalyst.com/rma-tactics", "The Analyst", 2, "Madrid look to break quickly once they win the ball")]},
        {"id": "W-006", "fact_key": "A.tactics.pressing_style", "category": "tactics", "statement": "Arsenal press high, the eight jumping onto the holding midfielder.",
         "value": "high 4-4-2 press", "unit": None, "as_of": None, "confidence": "high",
         "sources": [src("https://theanalyst.com/ars-press", "The Analyst", 2, "the right eight steps up alongside the striker")]},
        {"id": "W-007", "fact_key": "H.predicted_xi", "category": "lineup", "statement": "Predicted Real Madrid XI.", "value": xi("H"),
         "unit": None, "as_of": "2026-11-02T10:00:00Z", "confidence": "medium",
         "sources": [src("https://www.marca.com/rma-xi", "Marca", 1, "Navarro; Ortega, Ibarra, Molina, Castro"),
                     src("https://www.espn.com/rma-xi", "ESPN", 1, "Navarro in goal behind a back four")]},
        {"id": "W-008", "fact_key": "A.predicted_xi", "category": "lineup", "statement": "Predicted Arsenal XI.", "value": xi("A"),
         "unit": None, "as_of": "2026-11-02T10:00:00Z", "confidence": "medium",
         "sources": [src("https://www.bbc.co.uk/ars-xi", "BBC", 1, "Hughes; Clarke, Walsh, Gardner, Lowe"),
                     src("https://www.skysports.com/ars-xi", "Sky Sports", 1, "Hughes starts in goal")]},
        {"id": "W-009", "fact_key": "H.suspensions", "category": "suspension", "statement": "No Madrid suspensions.", "value": [], "unit": None,
         "as_of": "2026-11-02T10:00:00Z", "confidence": "high", "single_source": True,
         "sources": [src("https://www.uefa.com/disciplinary", "UEFA", 1, "no suspended players for Real Madrid")]},
        {"id": "W-010", "fact_key": "A.suspensions", "category": "suspension", "statement": "No Arsenal suspensions.", "value": [], "unit": None,
         "as_of": "2026-11-02T10:00:00Z", "confidence": "high", "single_source": True,
         "sources": [src("https://www.uefa.com/disciplinary", "UEFA", 1, "no suspended players for Arsenal")]},
        {"id": "W-011", "fact_key": "fixture.stakes", "category": "news", "statement": "Both sides chase a top-eight league-stage finish.",
         "value": "top-eight race in the league stage", "unit": None, "as_of": "2026-11-02T09:00:00Z", "confidence": "medium",
         "sources": [src("https://www.uefa.com/preview", "UEFA", 1, "both clubs are in the race for the top eight")]},
    ]
    return {"version": "1", "project_id": "fx-match",
            "runs": [{"agent": "match-researcher", "scope": s, "finished_at": "2026-11-02T12:20:00Z"} for s in ("H", "A", "fixture")],
            "claims": claims}


def main() -> None:
    cas = cassette()
    (HERE / "api_cassette.json").write_text(json.dumps(cas, indent=1), encoding="utf-8", newline="\n")
    client = CassetteClient(cas)
    api_claims, _ = AF.pull(client, FID, T0)
    wc = web_claims()
    (ART / "web_claims.json").write_text(json.dumps(wc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    brief = json.loads((ART / "brief.match.json").read_text(encoding="utf-8"))
    doc = merge("fx-match", brief, api_claims, wc, "2026-11-02T12:30:00Z",
                {"brief": "0" * 64, "web_claims": "1" * 64}, client.calls)
    (ART / "match_dossier.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"api claims {len(api_claims)}, calls {client.calls}, facts {len(doc['facts'])}, conflicts {doc['conflicts']}")


if __name__ == "__main__":
    main()


def match_spec_and_analysis() -> tuple[dict, dict, dict]:
    """Expected shapes for the match (H builds up, A presses high) with names from the predicted XIs."""
    from tms.tactic.formations import Block
    from tms.tactic.scaffold import scaffold
    from tms.predict.build import compute
    s = scaffold("fx-match", "build_up", "both", "4-3-3", "4-4-2", home_block=Block(22, 34, 56, 0.2), away_block=Block(46, 30, 52, 0.35))
    order = {"G": 0, "D": 1, "M": 2, "F": 3}
    for t, xi in (("H", H_XI), ("A", A_XI)):
        players = sorted(s["teams"][t]["players"], key=lambda p: (p["line"], p["pos"][1]))
        names = sorted(xi, key=lambda n: order[n[2]])
        for p, (name, num, _) in zip(players, names):
            p["name"], p["number"] = name, num
    s.update(title="Madrid build-up v Arsenal press",
             summary="Real Madrid build from the back in a 4-3-3 while Arsenal press high from a 4-4-2, with an eight jumping onto Madrid's holding midfielder.")
    hid = {p["role"]: p["id"] for p in s["teams"]["H"]["players"]}
    aid = {p["role"]: p["id"] for p in s["teams"]["A"]["players"]}
    s["principles"] = [
        {"id": "P1", "name": "Arsenal's front-foot press", "statement": "Arsenal's strikers and an eight press Madrid's centre-backs and screen the holding midfielder.",
         "players": [aid["LS"], aid["RS"], aid["LCM"]], "visual_proof": "the eight leaves the midfield line to mark the six", "claim_refs": ["A.tactics.pressing_style"]},
        {"id": "P2", "name": "Madrid break in transition", "statement": "When Madrid escape the press, the wingers attack the space behind Arsenal's high line.",
         "players": [hid["LW"], hid["ST"], hid["RW"]], "visual_proof": "a vertical pass releases a winger behind the full-back", "claim_refs": ["H.tactics.build_up"]},
    ]
    s["triggers"] = [{"id": "T1", "team": "A", "cue": "Madrid's centre-back receives facing his own goal", "response": "the nearest striker presses and the eight jumps",
                      "players": [aid["LS"], aid["LCM"]], "principles": ["P1"]}]
    s["strengths"] = [{"id": "S1", "text": "Arsenal win the ball high and attack a disorganised defence", "principles": ["P1"]}]
    s["weaknesses"] = [{"id": "W1", "text": "Arsenal's high line leaves space behind the full-backs", "players": [aid["LB"], aid["RB"]]}]
    s["counters"] = [{"id": "C1", "text": "Madrid bypass the press with a direct ball to the wingers", "targets": "W1"}]
    s["assumptions"] = ["Line-ups are predicted, not confirmed"]
    analysis = {
        "version": "1", "project_id": "fx-match", "headline": "Madrid's runners against Arsenal's high press",
        "angle": "Arsenal's front-foot press meets Madrid's direct transitions: whoever controls the second balls controls the night.",
        "sections": [
            {"id": "form", "title": "Form", "assertions": [{"text": "Madrid score freely at home, averaging more than two goals a game.", "refs": ["H.home_goals_for_avg"]}]},
            {"id": "tactical", "title": "Tactical picture", "assertions": [{"text": "Arsenal press high with an eight jumping onto the holding midfielder.", "refs": ["A.tactics.pressing_style", "W-006"]}]},
            {"id": "outlook", "title": "Outlook", "assertions": [{"text": "Home advantage and chance quality give Madrid a slight edge.", "refs": ["H.xg_for_avg", "A.xg_against_avg"]}]}],
        "key_battles": [{"id": "KB1", "title": "Six under pressure", "home_player": hid["DM"], "away_player": aid["LCM"],
                         "why": "If Madrid's six turns away from Arsenal's eight, Madrid break into space behind the press.", "refs": ["A.tactics.pressing_style"]}],
        "tactical_battles": [
            {"id": "TB1", "title": "Arsenal press v Madrid build-up", "attacking_team": "A", "principles": ["P1"],
             "description": "Arsenal's front two and an eight press Madrid's back line.", "refs": ["A.tactics.pressing_style"]},
            {"id": "TB2", "title": "Madrid transitions", "attacking_team": "H", "principles": ["P2"],
             "description": "Madrid look for their wingers behind Arsenal's high line once the press is beaten.", "refs": ["H.tactics.build_up"]}],
        "prediction_adjustments": [{"outcome": "away", "delta_pp": 2.0, "reason": "Arsenal's only doubt is a squad player, while Madrid miss a starter.", "refs": ["H.injuries", "A.injuries"]}],
        "uncertainties": ["Line-ups are predicted until about an hour before kick-off."],
    }
    dossier = json.loads((ART / "match_dossier.json").read_text(encoding="utf-8"))
    pred = {"version": "1", "project_id": "fx-match", "inputs": {"match_dossier": "2" * 64, "match_analysis": "3" * 64},
            **compute(dossier, analysis)}
    pred["project_id"] = "fx-match"
    return s, analysis, pred


if __name__ == "__main__":
    spec, analysis, pred = match_spec_and_analysis()
    (HERE / "tactic_spec.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (ART / "match_analysis.json").write_text(json.dumps(analysis, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (ART / "prediction.json").write_text(json.dumps(pred, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print("prediction", pred["probs_final"], pred["headline"], pred["confidence"])
