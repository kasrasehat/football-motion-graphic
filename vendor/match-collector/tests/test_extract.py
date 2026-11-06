import json

from match_collector.collectors import ballhelper_candidates, soccerway_candidate
from match_collector.extract import extract_page, tab_data
from match_collector.models import Evidence, MatchQuery
from match_collector.news import article_from_html, news_relation
from match_collector.transport import Document


def doc(html, url="http://www.ballhelper.com/"):
    return Document(url, html, Evidence(url=url))


def test_ballhelper_date_formats_and_match_boundaries():
    html = """<table><tr><td>11.6.2026</td><td>9:40</td><td>Sydney (5) - Central Coast Mariners (10)</td></tr>
    <tr><td colspan="3">6.12.2025 Central Coast Mariners - Sydney 1 : 2</td></tr>
    <tr><td>(1-1-1) - (0-2-1)</td><td>W D L</td></tr>
    <tr><td>11.7.2026</td><td>5:0</td><td>Auckland - Wellington Phoenix</td></tr></table>"""
    found = ballhelper_candidates(doc(html), None)
    assert len(found) == 2
    assert found[0].source_date.isoformat() == "2026-11-06"
    assert found[0].home == "Sydney"
    assert found[0].kickoff is None
    assert len(found[0].raw["following_rows"]) == 2
    assert "6.12.2025" in found[0].raw["following_rows"][0][0]
    configured = ballhelper_candidates(doc(html), "UTC")
    assert configured[0].kickoff.isoformat() == "2026-11-06T09:40:00+00:00"


def test_ballhelper_league_results_are_month_first_too():
    html = "<table><tr><td>10.16.2026</td><td>Sydney - Western Sydney</td><td>0 : 0</td><td>1 : 0</td></tr></table>"
    found = ballhelper_candidates(doc(html), None)
    assert found[0].source_date.isoformat() == "2026-10-16"
    assert found[0].kickoff is None


def test_soccerway_uses_scheduled_time_not_current_period_time():
    env = {
        "event_id_c": "abc12345",
        "common_feed": [{"DC": 1794063600}],
        "eventStageStartTime": 1794067200,
        "participantsData": {"home": [{"name": "Arsenal"}], "away": [{"name": "Hull"}]},
        "basenameUrl": "/game/arsenal-12345678/hull-87654321",
        "futureField": {"value": 42},
        "config": {"ignore": 1},
    }
    html = f"<script>window.environment = {json.dumps(env)};</script>"
    c = soccerway_candidate(doc(html, "https://us.soccerway.com/game/arsenal-12345678/hull-87654321/"))
    assert c.kickoff.isoformat() == "2026-11-07T15:00:00+00:00"
    assert "mid=abc12345" in c.url
    assert c.raw["futureField"] == {"value": 42}
    assert "config" not in c.raw


def test_page_preserves_unknown_json_and_all_table_cells():
    page = extract_page(
        '<title>Match</title><script type="application/json">{"newMetric":7}</script><main><table><tr><th>xG</th><td>2.1</td><td>0.4</td></tr></table></main>',
        "https://us.soccerway.com/",
    )
    assert page["tables"][0]["rows"] == [["xG", "2.1", "0.4"]]
    assert list(page["embedded"].values()) == [{"newMetric": 7}]


def test_news_relation_date_filter_and_missing_date():
    html = '<h1>Arsenal meet Chelsea</h1><meta property="article:published_time" content="2026-11-05T12:00:00Z"><article>A fixture preview with team news.</article>'
    article = article_from_html(html, "https://www.sofascore.com/news/test")
    q = MatchQuery(opponent_a="Arsenal", opponent_b="Chelsea", date="2026-11-06")
    assert news_relation(article, q) == "both_teams_mentioned"
    article["published_at"] = "2025-11-05"
    assert news_relation(article, q) is None
    article["published_at"] = None
    article["title"] = "Arsenal injury update"
    assert news_relation(article, q) == "team_context"
    assert article["publication_time_unverified"]


def test_category_coverage_requires_data_not_a_tab_name_or_error():
    shell = "<main>Lineups Statistics H2H Standings Odds We're sorry, but we can't load this section.</main>"
    for category in ("statistics", "lineups", "h2h", "standings", "odds"):
        assert tab_data(shell, category) is None
    actual = '<div class="stat__row"><span>Possession</span><span>60%</span><span>40%</span></div>'
    assert tab_data(actual, "statistics")["rows"][0]["text"] == "Possession 60% 40%"


def test_completed_lineup_player_dialog_without_profile_link():
    html = """<div class="fp-formation_1 fp-away_1"><div data-testid="wcl-participantPitch"
        data-analytics-player-id="player1"><div data-testid="wcl-lineupsParticipantName">
        <span>21</span><button>Keeper</button></div></div></div>"""
    lineup = tab_data(html, "lineups")
    assert lineup["on_pitch"] == [
        {
            "name": "Keeper",
            "player_id": "player1",
            "profile_path": None,
            "side": "away",
            "source_text": "21 Keeper",
        }
    ]
