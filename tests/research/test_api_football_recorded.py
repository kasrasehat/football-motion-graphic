"""resolve() and pull() against real API-Football responses, recorded on the Free plan on 2026-11-05 (no network)."""
from __future__ import annotations

import json

import pytest

from tms.research import api_football as AF
from tests.fixtures.match.make_match_fixtures import CassetteClient
from tests.helpers import FIX

pytestmark = pytest.mark.fast
NOW = "2026-11-05T12:00:00Z"
RECORDING = json.loads((FIX / "match" / "api_recorded_free_plan.json").read_text(encoding="utf-8"))


class Replay(CassetteClient):
    """Answers as the recording did, refusals included."""

    def __init__(self):
        super().__init__(RECORDING["responses"])

    def get(self, path, **params):
        key = path + ("?" + "&".join(f"{k}={params[k]}" for k in sorted(params)) if params else "")
        if key in RECORDING["refusals"]:
            raise AF.PlanRestricted(RECORDING["refusals"][key])
        return super().get(path, **params)


def _pull(fixture_id):
    claims, raw = AF.pull(Replay(), fixture_id, NOW)
    return {c["fact_key"]: c["value"] for c in claims}, raw


def test_resolve_finds_the_real_current_season_fixture():
    cands = AF.resolve(Replay(), "Arsenal", "Real Madrid", "2026-12-09", "2026-12-09")
    assert [(c["fixture_id"], c["home"], c["away"], c["venue"]) for c in cands] == [(1635610, "Arsenal", "Real Madrid", "Emirates Stadium")]


def test_resolve_on_a_date_without_the_match_is_no_match_not_a_plan_limit():
    assert AF.resolve(Replay(), "Arsenal", "Real Madrid", "2026-12-10", "2026-12-10") == []


def test_past_season_bundle_parses_every_part_the_plan_allows():
    v, raw = _pull(1360764)
    assert v["fixture.kickoff_utc"] == "2025-04-08T19:00:00Z" and v["fixture.venue"] == "Emirates Stadium"
    assert v["fixture.referee"] == "I. Peljto" and v["fixture.round"] == "Quarter-finals"
    assert (v["H.goals_for_avg"], v["H.goals_against_avg"], v["H.home_goals_for_avg"]) == (2.2, 0.7, 2.0)
    assert (v["H.clean_sheets"], v["H.formation"]) == (6, "4-3-3")
    assert (v["H.standing.position"], v["H.standing.points"], v["H.standing.played"]) == (3, 19, 8)
    assert (v["A.standing.position"], v["A.standing.points"]) == (11, 15)
    assert len(v["H.predicted_xi"]) == 11 and v["H.predicted_xi"][0] == {"name": "David Raya", "number": 22, "position": "G"}
    assert {"player": "R. Calafiori", "reason": "Knee Injury", "status": "out"} in v["H.injuries"]
    assert set(raw["_plan_refused"]) == {"last5_H", "last5_A"}


def test_h2h_lists_only_played_meetings_newest_first():
    v, _ = _pull(1360764)  # the recording also holds the unplayed 2026-12-09 meeting
    assert [(m["date"], m["score"]) for m in v["h2h.last5"]] == [("2025-04-16", "1-2"), ("2025-04-08", "3-0"), ("2019-07-24", "2-2")]


def test_managers_are_the_current_ones_not_the_first_listed():
    v, _ = _pull(1635610)  # /coachs lists Ljungberg and Wenger before Arteta
    assert v["H.manager"] == "Mikel Arteta"
    assert v["A.manager"] == "José Mourinho"


def test_current_season_bundle_on_free_keeps_what_it_can_and_names_what_it_cannot():
    v, raw = _pull(1635610)
    assert v["fixture.kickoff_utc"] == "2026-12-09T20:00:00Z" and "h2h.last5" in v
    assert set(raw["_plan_refused"]) == {"last5_H", "last5_A", "stats_H", "stats_A", "standings"}
    assert "H.goals_for_avg" not in v and "H.standing.points" not in v and "H.form.last5" not in v


def test_no_injury_rows_is_not_reported_as_no_absences():
    v, _ = _pull(1635610)  # five weeks before kick-off the API has nothing filed
    assert "H.injuries" not in v and "A.injuries" not in v


def test_odds_and_lineups_parse_on_a_just_played_current_season_fixture():
    v, _ = _pull(1635606)
    assert (v["fixture.odds_home"], v["fixture.odds_draw"], v["fixture.odds_away"]) == (12.0, 7.5, 1.2)
    assert len(v["H.predicted_xi"]) == 11 and len(v["A.predicted_xi"]) == 11
