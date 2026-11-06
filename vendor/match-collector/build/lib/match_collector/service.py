from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from uuid import uuid4

from .collectors import Ballhelper, Soccerway, Sofascore
from .models import CollectionReport, MatchQuery, SourceReport, now
from .transport import Fetcher

log = logging.getLogger(__name__)
COLLECTORS = {c.name: c for c in (Soccerway, Ballhelper, Sofascore)}


async def collect(
    query: MatchQuery, output: Path = Path("data"), *, run_id: str | None = None, transport=None, interval=1.0
) -> CollectionReport:
    run_id = run_id or uuid4().hex
    report = CollectionReport(run_id=run_id, query=query)
    directory = output / "runs" / run_id
    directory.mkdir(parents=True, exist_ok=True)

    async def one(name):
        fetcher = Fetcher(name, directory / name / "raw", transport=transport, interval=interval)
        try:
            return await COLLECTORS[name](fetcher, query).run()
        except Exception as exc:
            log.exception("Collector failed for %s", name)
            return SourceReport(
                source=name,
                status="error",
                evidence=fetcher.evidence,
                warnings=[f"Collector failed: {type(exc).__name__}: {exc}"],
            )
        finally:
            await fetcher.close()

    report.sources = list(await asyncio.gather(*(one(name) for name in query.sources)))
    matches = [r for r in report.sources if r.match]
    if matches:
        report.status = "partial"
        times = {r.source: r.match.kickoff.isoformat() for r in matches if r.match.kickoff}
        if len(set(times.values())) > 1:
            report.conflicts.append({"field": "kickoff", "source_values": times})
    elif any(any(values for values in r.data.values()) for r in report.sources):
        report.status = "unverified"
    else:
        report.status = "no_verified_match"
    report.finished_at = now()
    temp = directory / "report.tmp"
    temp.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    temp.replace(directory / "report.json")
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "report": "report.json",
                "status": report.status,
                "raw_artifact_count": sum(bool(e.artifact) for r in report.sources for e in r.evidence),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return report
