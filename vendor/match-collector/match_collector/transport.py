from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from bs4 import UnicodeDammit

from .models import Evidence

HOSTS = {
    "soccerway": {"soccerway.com", "www.soccerway.com", "us.soccerway.com"},
    "sofascore": {"www.sofascore.com", "sofascore.com", "api.sofascore.com"},
    "ballhelper": {"ballhelper.com", "www.ballhelper.com"},
}
NEWS_HOSTS = {"www.flashscore.com", "flashscore.com", "vrhnews.com", "www.vrhnews.com"}
# Observed in Soccerway's ordinary browser requests during live verification.
DATA_HOSTS = {
    "soccerway": {"global.flashscore.ninja", "content.livesportmedia.eu", "2035.ds.lsapp.eu"},
    "ballhelper": set(),
    "sofascore": set(),
}
USER_AGENT = "MatchCollector/0.1 (match research; low-rate requests)"


class FetchError(Exception):
    def __init__(self, url: str, reason: str, status: int | None = None):
        self.url, self.reason, self.status = url, reason, status
        super().__init__(f"{reason}: {url}")


def validate_url(url: str, hosts: set[str]) -> str:
    p = urlsplit(url)
    if p.scheme not in {"http", "https"} or p.hostname not in hosts:
        raise FetchError(url, "URL is outside the configured source hosts")
    if p.username or p.password or p.port not in (None, 80, 443):
        raise FetchError(url, "Credentials and nonstandard ports are not allowed")
    return urlunsplit((p.scheme, p.netloc, p.path or "/", p.query, ""))


class Robots:
    """Robots allow/disallow matching with wildcards and longest-rule precedence."""

    def __init__(self, text: str):
        groups, agents, rules = [], [], []
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (x.strip() for x in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if rules:
                    groups.append((agents, rules))
                    agents, rules = [], []
                agents.append(value.lower())
            elif key in {"allow", "disallow", "crawl-delay"}:
                rules.append((key, value))
        groups.append((agents, rules))
        specific = [r for a, r in groups if any(x != "*" and x in USER_AGENT.lower() for x in a)]
        selected = specific or [r for a, r in groups if "*" in a]
        self.rules = [rule for group in selected for rule in group]
        self.delay = max(
            [float(v) for k, v in self.rules if k == "crawl-delay" and v.replace(".", "", 1).isdigit()] or [0]
        )

    def allows(self, url: str) -> bool:
        p = urlsplit(url)
        path = p.path + ("?" + p.query if p.query else "")
        matches = []
        for key, rule in self.rules:
            if key == "crawl-delay" or not rule:
                continue
            pattern = re.escape(rule).replace(r"\*", ".*")
            pattern = pattern[:-2] + "$" if rule.endswith("$") else pattern
            if re.match(pattern, path):
                matches.append((len(rule.replace("*", "")), key == "allow"))
        return max(matches, default=(0, True))[1]


@dataclass
class Document:
    url: str
    text: str
    evidence: Evidence


class Fetcher:
    def __init__(
        self,
        source: str,
        storage: Path,
        *,
        interval: float = 1.0,
        transport=None,
        cache_seconds: int = 300,
        max_bytes: int = 12_000_000,
    ):
        self.source = source
        self.hosts = HOSTS[source] | DATA_HOSTS[source] | NEWS_HOSTS
        self.storage = storage
        self.storage.mkdir(parents=True, exist_ok=True)
        self.client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, timeout=25, follow_redirects=False, transport=transport
        )
        self.interval, self.cache_seconds, self.max_bytes = interval, cache_seconds, max_bytes
        self.policies: dict[str, Robots] = {}
        self.evidence: list[Evidence] = []
        self._locks: dict[str, asyncio.Lock] = {}
        self._last: dict[str, float] = {}
        self._cache: dict[str, Document] = {}
        self._blocked: dict[str, str] = {}

    async def close(self):
        await self.client.aclose()

    async def throttle(self, url: str):
        host = urlsplit(url).netloc
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            origin = f"{urlsplit(url).scheme}://{host}"
            delay = max(self.interval, self.policies.get(origin, Robots("")).delay)
            if delay > 30:
                raise FetchError(
                    url, "Source crawl-delay exceeds this worker's wait limit; schedule collection separately"
                )
            await asyncio.sleep(max(0, delay - (time.monotonic() - self._last.get(host, 0))))
            self._last[host] = time.monotonic()

    def save(self, url: str, body: bytes, status: int, content_type: str, *, encoding="utf-8") -> Document:
        digest = hashlib.sha256(body).hexdigest()
        artifact = self.storage / (digest + ".body")
        if not artifact.exists():
            artifact.write_bytes(body)
        ev = Evidence(
            url=url,
            status_code=status,
            content_type=content_type,
            sha256=digest,
            artifact=str(artifact.resolve()),
        )
        self.evidence.append(ev)
        return Document(url, body.decode(encoding, errors="replace"), ev)

    async def policy(self, url: str):
        url = validate_url(url, self.hosts)
        p = urlsplit(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin in self._blocked:
            raise FetchError(url, self._blocked[origin], 403)
        if origin not in self.policies:
            robots_url = origin + "/robots.txt"
            try:
                doc = await self._request(robots_url, robots=True)
                if doc.evidence.status_code in (404, 410):
                    self.policies[origin] = Robots("")
                elif doc.evidence.status_code == 200:
                    # A soft-404 HTML page is not a robots policy.
                    if "<html" in doc.text.lower()[:500]:
                        raise FetchError(robots_url, "robots.txt returned HTML; policy unavailable")
                    self.policies[origin] = Robots(doc.text)
                else:
                    raise FetchError(robots_url, "robots.txt unavailable", doc.evidence.status_code)
            except FetchError as exc:
                self._blocked[origin] = str(exc)
                raise
        if not self.policies[origin].allows(url):
            raise FetchError(url, "Disallowed by robots.txt", 403)

    async def _request(self, url: str, *, robots=False) -> Document:
        for redirect in range(6):
            validate_url(url, self.hosts)
            for attempt in range(3):
                await self.throttle(url)
                try:
                    async with self.client.stream("GET", url) as response:
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > self.max_bytes:
                                raise FetchError(url, "Response exceeded size limit")
                        content_type = response.headers.get("content-type", "")
                        encoding = response.encoding or "utf-8"
                        if "html" in content_type and "charset=" not in content_type:
                            encoding = UnicodeDammit(bytes(body), is_html=True).original_encoding or encoding
                        doc = self.save(
                            url, bytes(body), response.status_code, content_type, encoding=encoding
                        )
                except httpx.HTTPError as exc:
                    if attempt < 2:
                        await asyncio.sleep(2**attempt)
                        continue
                    raise FetchError(url, f"Network/TLS error: {type(exc).__name__}: {exc}") from exc
                if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                    retry = response.headers.get("retry-after", "")
                    wait = float(retry) if retry.isdigit() else 2 ** (attempt + 1)
                    if wait > 30:
                        raise FetchError(
                            url,
                            "Server requested a longer retry delay; retry this run later",
                            response.status_code,
                        )
                    await asyncio.sleep(wait)
                    continue
                break
            if response.is_redirect:
                url = validate_url(urljoin(url, response.headers.get("location", "")), self.hosts)
                if not robots:
                    await self.policy(url)
                continue
            if response.status_code >= 400 and not (robots and response.status_code in (404, 410)):
                raise FetchError(url, f"HTTP {response.status_code}", response.status_code)
            if any(
                x in doc.text[:5000].lower() for x in ("just a moment...", "verify you are human", "cf-chl-")
            ):
                raise FetchError(url, "Access challenge", response.status_code)
            return doc
        raise FetchError(url, "Too many redirects")

    async def get(self, url: str) -> Document:
        url = validate_url(url, self.hosts)
        try:
            await self.policy(url)
            cached = self._cache.get(url)
            if (
                cached
                and (datetime.now(UTC) - cached.evidence.fetched_at).total_seconds() < self.cache_seconds
            ):
                ev = cached.evidence.model_copy(update={"cached": True})
                self.evidence.append(ev)
                return Document(cached.url, cached.text, ev)
            doc = await self._request(url)
            self._cache[url] = doc
            return doc
        except FetchError as exc:
            self.evidence.append(Evidence(url=url, error=exc.reason, status_code=exc.status))
            raise

    async def json(self, url: str):
        doc = await self.get(url)
        try:
            return json.loads(doc.text)
        except ValueError as exc:
            raise FetchError(url, "Expected JSON but received another format") from exc
