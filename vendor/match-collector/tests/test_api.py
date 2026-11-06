import time

import httpx
from fastapi.testclient import TestClient
from test_integration import handler

from match_collector import api
from match_collector.service import collect


def test_job_api_persists_result_and_rejects_invalid_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "DATA", tmp_path)

    async def fixture_collect(query, output, *, run_id):
        return await collect(query, output, run_id=run_id, interval=0, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(api, "collect", fixture_collect)
    with TestClient(api.app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/jobs/does-not-exist").status_code == 404
        request = {"opponent_a": "Arsenal", "opponent_b": "Chelsea", "date": "2026-11-06", "browser": False}
        assert client.post("/jobs", json=request | {"date": "invalid"}).status_code == 422
        assert (
            client.post(
                "/jobs", json=request | {"seed_urls": {"soccerway": ["http://localhost/"]}}
            ).status_code
            == 422
        )
        response = client.post("/jobs", json=request)
        assert response.status_code == 202
        job = response.json()
        for _ in range(100):
            status = client.get(job["status_url"]).json()["status"]
            if status not in {"queued", "running"}:
                break
            time.sleep(0.01)
        assert status == "partial"
        result = client.get(job["result_url"])
        assert result.status_code == 200
        assert result.json()["query"]["timezone"] == "UTC"
        download = client.get(job["result_url"], headers={"Accept": "application/octet-stream"})
        assert download.headers["content-type"] == "application/octet-stream"
        assert f"match-{job['id']}.json" in download.headers["content-disposition"]
        assert download.content == result.content
        assert (tmp_path / "jobs.sqlite3").exists()
