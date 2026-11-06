from datetime import datetime

import pytest
from pydantic import ValidationError

from match_collector.matching import choose, rank_candidates, team_score
from match_collector.models import Candidate, MatchQuery


def candidate(**changes):
    return Candidate(
        **(
            {
                "source_id": "1",
                "url": "https://www.sofascore.com/match/1",
                "home": "Arsenal",
                "away": "Chelsea",
                "kickoff": datetime.fromisoformat("2026-11-06T23:30:00+00:00"),
            }
            | changes
        )
    )


def query(**changes):
    return MatchQuery(**({"opponent_a": "Arsenal", "opponent_b": "Chelsea", "date": "2026-11-06"} | changes))


def test_opponent_order_is_not_assumed():
    selected, status = choose(rank_candidates([candidate(home="Chelsea", away="Arsenal")], query()))
    assert status == "partial"
    assert selected.confidence == 1


def test_utc_day_is_not_local_day():
    assert rank_candidates([candidate()], query(timezone="Asia/Tehran")) == []
    assert choose(rank_candidates([candidate()], query(date="2026-11-07", timezone="Asia/Tehran")))[0]


def test_two_same_day_events_are_ambiguous():
    assert choose(rank_candidates([candidate(), candidate(source_id="2")], query())) == (None, "ambiguous")


def test_youth_women_and_reserve_sides_are_distinct():
    for name in ("Arsenal Women", "Arsenal U21", "Arsenal B", "Arsenal II"):
        assert team_score("Arsenal", name) == 0


def test_explicit_alias_resolves_abbreviation():
    q = query(opponent_a="Manchester United", aliases_a=["Man Utd"])
    assert choose(rank_candidates([candidate(home="Man Utd")], q))[0]


def test_club_designators_do_not_prevent_matching():
    assert team_score("Sydney FC", "Sydney") == 1
    assert team_score("Manchester Utd", "Manchester United") == 1
    assert team_score("FC", "AFC") == 0


def test_missing_timestamp_never_verifies_utc_date():
    c = candidate(kickoff=None, source_date="2026-11-06")
    assert choose(rank_candidates([c], query())) == (None, "unverified")


@pytest.mark.parametrize(
    "changes",
    [
        {"date": "11/06/26"},
        {"timezone": "Not/AZone"},
        {"max_pages_per_source": 100000},
        {"opponent_b": "Arsenal"},
    ],
)
def test_request_validation(changes):
    with pytest.raises(ValidationError):
        query(**changes)
