"""The match collector inside the research stage: collection, replay, and how its reports become sourced facts. No network."""
from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from match_collector.models import CollectionReport, Coverage, MatchQuery, SourceReport

from tests.helpers import fixture, place
from tms.research import cli as RC
from tms.research import scrape
from tms.state import machine, project as P
from tms.state.project import GateViolation

pytestmark = pytest.mark.fast

KICKOFF = "2026-11-02T20:00:00Z"


def brief(project_id):
    b = fixture("brief.match")
    b["project_id"] = project_id
    b["match"].update(home="Newcastle", away="Everton", kickoff_utc=KICKOFF, competition="Premier League")
    b["match"]["resolution"]["resolved_at"] = "2026-11-02T12:00:00Z"
    return b


@pytest.fixture
def pr(tmp_projects):
    project = P.init("fx-scrape", "match_preview", "Newcastle v Everton", True)
    place(project.dir, "brief", brief(project.id))
    return project


def report(run_id="run1", status="partial", when=date(2026, 11, 2), a="Newcastle", b="Everton", sources=None):
    return CollectionReport(run_id=run_id, query=MatchQuery(opponent_a=a, opponent_b=b, date=when), status=status,
                            finished_at=datetime(2026, 11, 2, 12, tzinfo=UTC), sources=sources or [])


def test_the_query_comes_from_the_brief_and_uses_the_utc_day(pr):
    b = brief(pr.id)
    b["match"]["kickoff_utc"] = "2026-11-03T00:30:00Z"
    q = scrape.query_from_brief(b, ["ballhelper"], browser=False)
    assert (q.opponent_a, q.opponent_b, q.date, q.timezone) == ("Newcastle", "Everton", date(2026, 11, 3), "UTC")
    assert q.sources == ["ballhelper"] and q.browser is False


def test_a_live_collection_publishes_its_report_through_an_injected_collector(pr):
    seen = {}

    async def fake(query, output):
        seen.update(query=query, output=output)
        return report()
    latest = scrape.collect(pr, ["soccerway"], browser=False, collect_fn=fake)
    assert seen["query"].sources == ["soccerway"] and seen["output"].is_absolute()
    assert latest["run_id"] == "run1" and latest["status"] == "partial" and latest["schema_version"] == "1.0"
    got_latest, got = scrape.load_latest(pr)
    assert got_latest == latest and got.run_id == "run1"
    assert not (scrape.root(pr) / "collection.lock").exists()


def test_a_second_collection_cannot_start_while_one_runs(pr):
    async def fake(query, output):
        with pytest.raises(GateViolation):
            scrape.collect(pr, ["soccerway"], browser=False, collect_fn=fake)
        return report()
    scrape.collect(pr, ["soccerway"], browser=False, collect_fn=fake)


def test_a_failed_collection_keeps_the_previous_result_and_releases_the_lock(pr):
    async def good(query, output):
        return report("good")

    async def bad(query, output):
        raise OSError("disk full")
    scrape.collect(pr, ["soccerway"], browser=False, collect_fn=good)
    with pytest.raises(OSError):
        scrape.collect(pr, ["soccerway"], browser=False, collect_fn=bad)
    assert scrape.load_latest(pr)[0]["run_id"] == "good"
    assert not (scrape.root(pr) / "collection.lock").exists()


def test_replay_needs_no_network_and_must_be_for_this_fixture(pr, tmp_path):
    saved = tmp_path / "report.json"
    saved.write_text(report("old").model_dump_json(), encoding="utf-8")
    assert scrape.replay(pr, saved)["run_id"] == "old"
    for wrong in (report("x", when=date(2026, 11, 9)), report("x", a="Arsenal")):
        saved.write_text(wrong.model_dump_json(), encoding="utf-8")
        with pytest.raises(GateViolation):
            scrape.replay(pr, saved)
    assert scrape.load_latest(pr)[0]["run_id"] == "old"


def test_the_command_runs_only_in_the_research_stage_and_logs_the_run(pr, tmp_path, capsys):
    saved = tmp_path / "report.json"
    blocked = SourceReport(source="sofascore", status="blocked", warnings=["HTTP 403: https://www.sofascore.com/robots.txt"],
                           coverage={"summary": Coverage(status="blocked", detail="x")})
    saved.write_text(report(sources=[blocked]).model_dump_json(), encoding="utf-8")
    args = SimpleNamespace(project=pr.id, sources="sofascore", no_browser=True, replay=str(saved), json=False)
    assert RC.cmd_scrape(args) == 2  # research has not begun
    machine.begin(pr, "intake")
    place(pr.dir, "brief", brief(pr.id))
    machine.submit(pr, "intake")
    machine.begin(pr, "research")
    assert RC.cmd_scrape(args) == 0
    out = capsys.readouterr().out
    assert "sofascore: blocked, no verified fixture" in out and "HTTP 403" in out


def test_a_run_that_found_nothing_does_not_replace_one_that_found_something(pr):
    async def good(query, output):
        return report("good")

    async def empty(query, output):
        return report("empty", status="no_verified_match")
    scrape.collect(pr, ["soccerway"], browser=False, collect_fn=good)
    assert scrape.collect(pr, ["soccerway"], browser=False, collect_fn=empty)["run_id"] == "good"


def test_a_path_too_long_for_the_collector_stops_before_it_starts(pr, monkeypatch):
    monkeypatch.setattr(scrape.os, "name", "nt")
    monkeypatch.setattr(scrape, "WINDOWS_MAX_PATH", 10)

    async def never(query, output):
        raise AssertionError("must not run")
    with pytest.raises(P.ProjectError, match="too long"):
        scrape.collect(pr, ["soccerway"], browser=False, collect_fn=never)

