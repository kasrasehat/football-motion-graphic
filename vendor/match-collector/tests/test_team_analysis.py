from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from match_collector.models import Candidate, SourceReport
from match_collector.team_analysis import (
    collect_team_analysis,
    preview_markets,
    prior_results,
    published_totals,
    summarize,
    truncated_results,
)


@pytest.mark.asyncio
async def test_truncated_league_page_uses_team_results_once_per_event():
    def page(ids, total):
        feed = "ZC÷stage~" + "~".join(f"AA÷{i}¬AD÷100¬AO÷190¬AC÷3¬PX÷h¬PY÷a¬AG÷1¬AH÷0¬BC÷1¬BD÷0" for i in ids)
        return "cjs.initialFeeds['results'] = {data:`" + feed + f"`, allEventsCount: {total}}}"

    short = page(["one"], 2)
    full = page(["one", "two"], 2)
    assert truncated_results(short)
    assert not truncated_results(full)
    match = Candidate(
        source_id="target",
        url="https://us.soccerway.com/game/test/",
        home="Home",
        away="Away",
        kickoff=datetime.fromtimestamp(200, UTC),
        raw={
            "stats2_config": {"tournamentStage": "stage"},
            "header": {"tournament": {"link": "/league/"}},
            "participantsData": {
                "home": [{"id": "h", "detail_link": "/team/home/"}],
                "away": [{"id": "a", "detail_link": "/team/away/"}],
            },
        },
    )

    async def get(url):
        return SimpleNamespace(url=url, text=short if "/league/" in url else full)

    collector = SimpleNamespace(
        maybe_get=AsyncMock(side_effect=get),
        query=SimpleNamespace(browser=False),
        report=SourceReport(source="soccerway"),
    )
    await collect_team_analysis(collector, match)
    result = collector.report.data["team_analysis"][0]["value"]
    assert len(result["results_urls"]) == 3
    assert {g["event_id"] for g in result["games"]} == {"one", "two"}
    assert result["teams"][0]["splits"]["overall"]["played"] == 2


def test_stage_history_and_away_team_markets():
    row = "AD÷100¬AO÷190¬AC÷3¬PX÷h¬PY÷a¬AG÷2¬AH÷3¬BC÷2¬BD÷1"
    feed = "~".join(
        [
            "ZC÷stage",
            f"AA÷game¬{row}",
            f"AA÷game¬{row}",
            f"AA÷target¬{row}",
            f"AA÷late¬{row}¬AO÷201",
            f"AA÷other¬{row}¬AC÷10",
            "ZC÷different",
            f"AA÷irrelevant¬{row}",
        ]
    )
    html = "cjs.initialFeeds['results'] = {data:`" + feed + "`}"
    games = prior_results(html, "stage", 200, "target", {"a"})
    assert [g["event_id"] for g in games] == ["game"]
    assert games[0]["ht"] == [0, 2]
    away = summarize(games, "a", "away")
    assert away["ht_ft"]["W/W"] == away["btts"]["yes"] == away["played"] == 1
    assert away["double_chance"] == {"win_or_draw": 1, "win_or_loss": 1, "draw_or_loss": 0}
    assert away["goal_lines"]["4.5"]["over"] == away["goal_lines"]["5.5"]["under"] == 1
    assert summarize(games, "a", "home")["played"] == 0
    games[0]["ht"] = None
    assert summarize(games, "a", "away")["ht_ft_sample"] == 0


def test_published_tables_and_forecasts():
    feed = "TZS÷Home~ETI÷2.5~TR÷1¬TI÷a¬TN÷Team¬TM÷3¬OUO÷1¬OUU÷2~LMS÷+¬LME÷match~TR÷2¬TI÷b~LMS÷-"
    rows = published_totals(feed, {"a"}, "home")
    assert len(rows) == 1
    assert rows[0]["last_five"] == [{"result": "+", "event_id": "match"}]
    assert published_totals(feed, {"a"}, "away") == []
    preview = {
        "eventId": "e",
        "contentParsed": "[p]Win probability based on the average odds: "
        "Team A wins: 54%, Team B wins: 30%, Draw: 16%.[/p]",
    }
    assert preview_markets(preview, "e")["result_percentages"]["Draw"] == 16
    assert preview_markets(preview, "other") == {}
