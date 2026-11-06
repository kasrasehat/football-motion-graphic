"""Research stage: run the vendored match_collector for the brief's fixture, or replay a saved report, into the project.

Layout under media/research/collector/:
    runs/<run_id>/...   the collector's own report, manifest and raw evidence
    latest.json         which run this project uses: run id, status, schema version, report path
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from tms import jsonio
from tms.state.project import GateViolation, ProjectError

SOURCES = ("soccerway", "ballhelper", "sofascore")
LOCK_STALE_S = 2 * 3600
WINDOWS_MAX_PATH = 259
RAW_PATH_SUFFIX = 125  # runs/<32-char id>/<source>/raw/<64-char hash>.body, the longest path the collector writes


def _models():
    try:
        from match_collector.models import CollectionReport, MatchQuery
    except ImportError as e:
        raise ProjectError("match_collector is not installed: run `.venv/Scripts/python.exe -m pip install ./vendor/match-collector`") from e
    return CollectionReport, MatchQuery


def root(pr) -> Path:
    return pr.dir / "media" / "research" / "collector"


def query_from_brief(brief: dict, sources: list[str], browser: bool):
    """The brief's kick-off is UTC, so the UTC day is the match day whatever the viewer's timezone."""
    _, MatchQuery = _models()
    m = brief["match"]
    return MatchQuery(opponent_a=m["home"], opponent_b=m["away"], date=jsonio.parse_iso(m["kickoff_utc"]).date(), timezone="UTC",
                      sources=sources, browser=browser)


class _Lock:
    """One live collection per project: a retried command must not publish a competing result."""

    def __init__(self, path: Path):
        self.path = path

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_file() and time.time() - self.path.stat().st_mtime > LOCK_STALE_S:
            self.path.unlink()  # left behind by an interrupted run
        try:
            os.close(os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            raise GateViolation("another collection is running for this project; wait for it to finish") from None

    def __exit__(self, *_exc):
        self.path.unlink(missing_ok=True)


def _publish(pr, report, report_path: Path) -> dict:
    """Make this run the project's result, unless it found nothing and an earlier run found something."""
    previous = root(pr) / "latest.json"
    if report.status == "no_verified_match" and previous.is_file() and jsonio.read_json(previous)["status"] != "no_verified_match":
        return jsonio.read_json(previous)
    latest = {"run_id": report.run_id, "status": report.status, "schema_version": report.schema_version,
              "report": report_path.relative_to(pr.dir).as_posix(), "finished_at": report.finished_at.isoformat() if report.finished_at else None}
    jsonio.write_json(root(pr) / "latest.json", latest)
    return latest


def collect(pr, sources: list[str], browser: bool, collect_fn=None) -> dict:
    """Run a live collection. `collect_fn` is injected in tests, so they need no network."""
    query = query_from_brief(pr.load_artifact("brief"), sources, browser)
    out = root(pr).resolve()
    if os.name == "nt" and len(str(out)) + RAW_PATH_SUFFIX > WINDOWS_MAX_PATH:
        raise ProjectError(f"{out} is too long: the collector's evidence files would pass Windows' {WINDOWS_MAX_PATH}-character path limit. Use a shorter project slug or projects folder.")
    if collect_fn is None:
        from match_collector.service import collect as collect_fn
    with _Lock(root(pr) / "collection.lock"):
        report = asyncio.run(collect_fn(query, output=out))
    path = root(pr) / "runs" / report.run_id / "report.json"
    if not path.is_file():  # an injected collector may not write one; the real one always does
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report.model_dump_json(indent=1), encoding="utf-8")
    return _publish(pr, report, path)


def _same_fixture(report, brief: dict) -> bool:
    m = brief["match"]
    want, got = {m["home"].casefold(), m["away"].casefold()}, {report.query.opponent_a.casefold(), report.query.opponent_b.casefold()}
    return want == got and report.query.date == jsonio.parse_iso(m["kickoff_utc"]).date()


def replay(pr, saved: Path) -> dict:
    """Use a saved report with no network. It must be for this project's fixture, and it stays subject to freshness rules."""
    CollectionReport, _ = _models()
    if not saved.is_file():
        raise ProjectError(f"no saved report at {saved}")
    report = CollectionReport.model_validate_json(saved.read_text(encoding="utf-8"))
    if not _same_fixture(report, pr.load_artifact("brief")):
        q = report.query
        raise GateViolation(f"saved report is for {q.opponent_a} v {q.opponent_b} on {q.date}, not this project's fixture")
    path = root(pr) / "runs" / report.run_id / "report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(saved.read_text(encoding="utf-8"), encoding="utf-8")
    return _publish(pr, report, path)


def load_latest(pr):
    """(latest pointer, report), or (None, None) if this project has not collected."""
    CollectionReport, _ = _models()
    f = root(pr) / "latest.json"
    if not f.is_file():
        return None, None
    latest = jsonio.read_json(f)
    return latest, CollectionReport.model_validate_json((pr.dir / latest["report"]).read_text(encoding="utf-8"))


def coverage_lines(report) -> list[str]:
    out = [f"collector run {report.run_id}: {report.status} (report schema {report.schema_version})"]
    for s in report.sources:
        fixture = f"{s.match.home} v {s.match.away}" if s.match else "no verified fixture"
        got = sorted(k for k, c in s.coverage.items() if c.status == "collected")
        out.append(f"  {s.source}: {s.status}, {fixture}; collected: {', '.join(got) or 'nothing'}")
        out += [f"    warning: {w}" for w in s.warnings if "HTTP" in w or "block" in w.lower()]
    out += [f"  conflict: {c}" for c in report.conflicts]
    return out
