import hashlib

import httpx
import pytest

from match_collector.transport import Fetcher, FetchError, Robots, validate_url


def test_robots_wildcards_and_longest_allow():
    robots = Robots("User-agent: *\nDisallow: /private/*\nAllow: /private/public/\nDisallow: */day+2/$")
    assert not robots.allows("https://us.soccerway.com/private/a")
    assert robots.allows("https://us.soccerway.com/private/public/a")
    assert not robots.allows("https://us.soccerway.com/soccer/day+2/")
    assert robots.allows("https://us.soccerway.com/soccer/day+2/other")


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "file:///etc/passwd",
        "https://us.soccerway.com.evil.test/",
        "https://us.soccerway.com:9999/",
        "https://name:password@us.soccerway.com/",
    ],
)
def test_untrusted_seed_urls_rejected(url):
    with pytest.raises(FetchError):
        validate_url(url, {"us.soccerway.com"})


async def test_403_robots_stops_requests(tmp_path):
    requests = []

    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(403, text="Forbidden")

    f = Fetcher("sofascore", tmp_path, interval=0, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(FetchError):
            await f.get("https://www.sofascore.com/api/v1/event/1")
        assert requests == ["https://www.sofascore.com/robots.txt"]
        assert f.evidence[-1].error
    finally:
        await f.close()


async def test_redirect_to_another_host_is_not_followed(tmp_path):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})

    f = Fetcher("soccerway", tmp_path, interval=0, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(FetchError, match="outside"):
            await f.get("https://us.soccerway.com/")
    finally:
        await f.close()


async def test_raw_evidence_and_cache(tmp_path):
    requests = []

    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(
            200, text="User-agent: *\nAllow: /" if request.url.path == "/robots.txt" else "<h1>fixture</h1>"
        )

    f = Fetcher("soccerway", tmp_path, interval=0, transport=httpx.MockTransport(handler))
    try:
        doc = await f.get("https://us.soccerway.com/")
        cached = await f.get("https://us.soccerway.com/")
        assert cached.evidence.cached
        assert len(requests) == 2
        assert doc.evidence.sha256 == hashlib.sha256(b"<h1>fixture</h1>").hexdigest()
        assert (tmp_path / (doc.evidence.sha256 + ".body")).read_bytes() == b"<h1>fixture</h1>"
    finally:
        await f.close()
