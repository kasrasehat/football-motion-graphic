import json

import httpx

from match_collector.models import MatchQuery
from match_collector.service import collect

MATCH_PATH = "/game/arsenal-12345678/chelsea-87654321/"
EVENT = {
    "id": 123,
    "homeTeam": {"name": "Arsenal"},
    "awayTeam": {"name": "Chelsea"},
    "startTimestamp": 1793966400,
    "newProviderField": {"keep": True},
}
ENV = {
    "event_id_c": "match001",
    "common_feed": [{"DC": 1793966400}],
    "participantsData": {"home": [{"name": "Arsenal"}], "away": [{"name": "Chelsea"}]},
    "basenameUrl": MATCH_PATH.rstrip("/"),
}
MATCH_HTML = f'<main><script>window.environment={json.dumps(ENV)};</script><a href="/news/arsenal-chelsea">Arsenal Chelsea preview</a></main>'
BALL = """<table><tr><td>11.6.2026</td><td>12:0</td><td>Arsenal (1) - Chelsea (2)</td></tr>
<tr><td colspan="3">1.11.2025 Arsenal - Chelsea 2 : 0</td></tr></table>"""
NEWS = '<h1>Arsenal Chelsea preview</h1><meta property="article:published_time" content="2026-11-05T12:00:00Z"><article>Synthetic test fixture preview.</article>'


def handler(request):
    path, host = request.url.path, request.url.host
    if path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nAllow: /")
    if "soccerway" in host:
        if path == "/":
            return httpx.Response(
                200, text=f'<a href="{MATCH_PATH}">Arsenal Chelsea</a>', headers={"content-type": "text/html"}
            )
        if path == "/sitemap.xml":
            return httpx.Response(
                200, text='<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>'
            )
        if path == MATCH_PATH:
            return httpx.Response(200, text=MATCH_HTML, headers={"content-type": "text/html"})
        if path == "/news/arsenal-chelsea":
            return httpx.Response(200, text=NEWS, headers={"content-type": "text/html"})
    if "ballhelper" in host:
        return httpx.Response(200, text=BALL, headers={"content-type": "text/html"})
    if "sofascore" in host:
        if "scheduled-events" in path:
            return httpx.Response(200, json={"events": [EVENT]})
        if path == "/api/v1/event/123":
            return httpx.Response(200, json={"event": EVENT})
        if path.endswith("statistics"):
            return httpx.Response(200, json={"statistics": [{"name": "xG", "home": 1.2, "away": 0.4}]})
        if path.endswith("lineups"):
            return httpx.Response(200, json={"home": {"players": []}, "confirmed": False})
    return httpx.Response(404, text="Not published")


async def test_all_three_sources_save_data_with_independent_failures(tmp_path):
    q = MatchQuery(
        opponent_a="Arsenal",
        opponent_b="Chelsea",
        date="2026-11-06",
        browser=False,
        ballhelper_timezone="UTC",
    )
    report = await collect(q, tmp_path, transport=httpx.MockTransport(handler), interval=0)
    assert report.status == "partial"
    assert len(report.sources) == 3
    assert all(s.match for s in report.sources)
    soccerway, ball, sofa = report.sources
    assert soccerway.data["news"][0]["value"]["body"] == "Synthetic test fixture preview."
    assert ball.data["h2h"]
    assert sofa.data["summary"][0]["value"]["newProviderField"] == {"keep": True}
    assert sofa.data["statistics"]
    assert sofa.coverage["incidents"].status == "unavailable"
    assert any(e.status_code == 404 for e in sofa.evidence)
    path = tmp_path / "runs" / report.run_id / "report.json"
    assert json.loads(path.read_text())["query"]["timezone"] == "UTC"


async def test_blocked_source_cannot_make_other_sources_fail(tmp_path):
    def blocked(request):
        return httpx.Response(403) if "sofascore" in request.url.host else handler(request)

    q = MatchQuery(opponent_a="Arsenal", opponent_b="Chelsea", date="2026-11-06", browser=False)
    report = await collect(q, tmp_path, transport=httpx.MockTransport(blocked), interval=0)
    assert report.sources[0].match
    assert report.sources[1].status == "unverified"
    assert report.sources[2].status == "blocked"
    assert report.sources[2].match is None


async def test_wrong_date_never_collects_match_data(tmp_path):
    q = MatchQuery(
        opponent_a="Arsenal", opponent_b="Chelsea", date="2026-11-07", browser=False, include_news=False
    )
    report = await collect(q, tmp_path, transport=httpx.MockTransport(handler), interval=0)
    assert report.status == "no_verified_match"
    assert all(not s.data["summary"] for s in report.sources)
