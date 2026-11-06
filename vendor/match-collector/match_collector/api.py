from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi import Path as PathParameter
from fastapi.responses import FileResponse

from .models import MatchQuery, now
from .service import collect

DATA = Path(os.environ.get("MATCH_COLLECTOR_DATA", "data")).resolve()


def database():
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA / "jobs.sqlite3", timeout=10)
    db.row_factory = sqlite3.Row
    db.execute(
        "CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, status TEXT, created_at TEXT, query TEXT, error TEXT)"
    )
    return db


@asynccontextmanager
async def lifespan(app):
    app.state.tasks = set()
    app.state.semaphore = asyncio.Semaphore(2)
    with database() as db:
        db.execute(
            "UPDATE jobs SET status='interrupted', error='Server restarted before collection completed' WHERE status IN ('queued','running')"
        )
    yield
    for task in app.state.tasks:
        task.cancel()
    await asyncio.gather(*app.state.tasks, return_exceptions=True)


app = FastAPI(
    title="Match Collector",
    version="0.1.0",
    lifespan=lifespan,
    description=(
        "**Start with ‘1. Start collecting a match’ below.** Open it, click **Try it out**, "
        "edit the example opponents and date, then click **Execute**. Dates use **UTC** by default.\n\n"
        "The response gives you an **id** for your collection. Copy it into step 2 to check progress, "
        "then step 3 to download the collected match data and news."
    ),
    openapi_tags=[
        {"name": "Collect a match", "description": "Follow these three steps in order."},
        {"name": "Service status", "description": "Optional service check; this does not collect a match."},
    ],
    swagger_ui_parameters={"defaultModelsExpandDepth": -1, "syntaxHighlight": False},
)


@app.get(
    "/health",
    tags=["Service status"],
    summary="Check whether the service is running",
    description="Returns status: ok when the service is reachable. You can skip this when collecting a match.",
)
def health():
    return {"status": "ok"}


async def work(job_id: str, query: MatchQuery):
    try:
        async with app.state.semaphore:
            with database() as db:
                db.execute("UPDATE jobs SET status='running' WHERE id=?", (job_id,))
            report = await collect(query, DATA, run_id=job_id)
            with database() as db:
                db.execute("UPDATE jobs SET status=? WHERE id=?", (report.status, job_id))
    except asyncio.CancelledError:
        with database() as db:
            db.execute("UPDATE jobs SET status='interrupted', error='Server stopped' WHERE id=?", (job_id,))
        raise
    except Exception as exc:
        logging.getLogger(__name__).exception("Job failed: %s", job_id)
        with database() as db:
            db.execute(
                "UPDATE jobs SET status='failed', error=? WHERE id=?",
                (f"{type(exc).__name__}: {exc}", job_id),
            )


@app.post(
    "/jobs",
    status_code=202,
    tags=["Collect a match"],
    summary="1. Start collecting a match",
    description=(
        "Click **Try it out**, change the opponents and date in the example, then click **Execute**. "
        "The example includes all three websites and news. Home/away order does not matter. "
        "The **id** in the response identifies this collection; save it for steps 2 and 3. "
        "A queued response means your request was accepted, not that collection has finished."
    ),
)
async def create_job(
    query: Annotated[
        MatchQuery,
        Body(
            openapi_examples={
                "match": {
                    "summary": "Example: Arsenal vs Hull City",
                    "value": {
                        "opponent_a": "Arsenal",
                        "opponent_b": "Hull City",
                        "aliases_b": ["Hull"],
                        "date": "2026-11-07",
                        "timezone": "UTC",
                        "sources": ["soccerway", "ballhelper", "sofascore"],
                        "include_news": True,
                    },
                }
            }
        ),
    ],
):
    from .transport import HOSTS, FetchError, validate_url

    try:
        for source, urls in query.seed_urls.items():
            for url in urls:
                validate_url(url, HOSTS[source])
    except (FetchError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    if len(app.state.tasks) >= 24:
        raise HTTPException(429, "Job queue is full; retry after an existing job finishes")
    job_id = uuid4().hex
    with database() as db:
        db.execute(
            "INSERT INTO jobs VALUES (?,?,?,?,?)",
            (job_id, "queued", now().isoformat(), query.model_dump_json(), None),
        )
    task = asyncio.create_task(work(job_id, query))
    app.state.tasks.add(task)
    task.add_done_callback(app.state.tasks.discard)
    return {
        "id": job_id,
        "status": "queued",
        "status_url": f"/jobs/{job_id}",
        "result_url": f"/jobs/{job_id}/result",
    }


def get_record(job_id):
    with database() as db:
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Job not found")
    return dict(row)


@app.get(
    "/jobs/{job_id}",
    tags=["Collect a match"],
    summary="2. Check collection progress",
    description=(
        "Click **Try it out**, paste the **id** returned by step 1 into **job_id**, then click **Execute**. "
        "If status is **queued** or **running**, check again later. When it changes, use step 3. "
        "A failed or interrupted collection may not have a result; this response includes any error."
    ),
)
def get_job(job_id: Annotated[str, PathParameter(description="Paste the collection id returned by step 1.")]):
    record = get_record(job_id)
    record["query"] = json.loads(record["query"])
    return record


@app.get(
    "/jobs/{job_id}/result",
    tags=["Collect a match"],
    summary="3. Download collected match data and news",
    response_class=FileResponse,
    responses={
        200: {
            "description": "Saved JSON report",
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
            },
        }
    },
    description=(
        "Click **Try it out**, paste the same collection **id** into **job_id**, then click **Execute**. "
        "Keep the default response type (application/octet-stream), then click **Download file** "
        "under the response body to save the full JSON report. "
        "HTTP 409 means the result is not ready or the collection ended without a report. "
        "A **partial** report contains available data and does not guarantee full coverage."
    ),
)
def get_result(
    request: Request,
    job_id: Annotated[str, PathParameter(description="Paste the collection id returned by step 1.")],
):
    record = get_record(job_id)
    if record["status"] in {"queued", "running"}:
        raise HTTPException(409, "Collection is still running")
    path = DATA / "runs" / record["id"] / "report.json"
    if not path.exists():
        raise HTTPException(409, {"status": record["status"], "error": record["error"]})
    if request.headers.get("accept", "").split(",", 1)[0].strip() == "application/octet-stream":
        return FileResponse(path, media_type="application/octet-stream", filename=f"match-{job_id}.json")
    return FileResponse(path, media_type="application/json")
