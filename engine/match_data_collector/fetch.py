"""The only way adapters reach the web: identifies itself, obeys robots.txt, paces itself, caches, and stops when refused.

It deliberately has no proxy, cookie, header-spoofing, retry-on-block or browser option. A block is an answer.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from match_data_collector import __version__
from match_data_collector.policy import host_of, policy_for_host

USER_AGENT = f"match-data-collector/{__version__}"
BLOCK_STATUS = {401, 403, 407, 429, 451, 503}
BLOCK_MARKERS = ("verifying you are human", "captcha", "cf-chl", "are you a robot", "unusual traffic")
PRODUCT = "match-data-collector"


class FetchRefused(Exception):
    """Base: this page must not be, or could not be, fetched. `reason` is a contract gap reason."""
    reason = "unavailable"


class NotPermitted(FetchRefused):
    reason = "not_permitted"


class RobotsDisallowed(FetchRefused):
    reason = "robots_disallowed"


class Blocked(FetchRefused):
    reason = "blocked"


class PoliteFetcher:
    def __init__(self, cache_dir: Path | None = None, ttl_s: float = 6 * 3600, transport: httpx.BaseTransport | None = None,
                 clock=time.monotonic, wall=time.time, sleep=time.sleep):
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.ttl_s = ttl_s
        self.clock, self.wall, self.sleep = clock, wall, sleep
        self.client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, transport=transport, follow_redirects=False)
        self.robots: dict[str, RobotFileParser | None] = {}
        self.last_hit: dict[str, float] = {}
        self.stopped: dict[str, str] = {}  # host -> why; nothing more is requested from it in this run

    def _pace(self, host: str, min_interval_s: float) -> None:
        last = self.last_hit.get(host)
        if last is not None:
            wait = min_interval_s - (self.clock() - last)
            if wait > 0:
                self.sleep(wait)
        self.last_hit[host] = self.clock()

    def _robots_allow(self, url: str, min_interval_s: float) -> bool:
        p = urlparse(url)
        root = f"{p.scheme}://{p.netloc}"
        if root not in self.robots:
            self._pace(p.hostname or "", min_interval_s)
            try:
                r = self.client.get(urljoin(root, "/robots.txt"))
            except httpx.HTTPError as e:
                raise FetchRefused(f"could not read robots.txt: {type(e).__name__}") from e
            if r.status_code in BLOCK_STATUS:
                self.stopped[p.hostname or ""] = f"robots.txt -> HTTP {r.status_code}"
                raise Blocked(self.stopped[p.hostname or ""])
            if r.status_code == 200:
                rp = RobotFileParser()
                rp.parse(r.text.splitlines())
                self.robots[root] = rp
            else:
                self.robots[root] = None  # no robots.txt: nothing is disallowed
        rp = self.robots[root]
        return rp is None or rp.can_fetch(PRODUCT, url)

    def _cache_file(self, url: str) -> Path | None:
        return self.cache_dir / (hashlib.sha256(url.encode()).hexdigest()[:32] + ".html") if self.cache_dir else None

    def get_text(self, url: str) -> str:
        host = host_of(url)
        policy = policy_for_host(host)
        if policy is None or policy.status != "allowed":
            raise NotPermitted(f"{host}: {policy.reason if policy else 'no recorded policy for this host'}")
        if host in self.stopped:
            raise Blocked(f"{host}: stopped earlier in this run ({self.stopped[host]})")
        cached = self._cache_file(url)
        if cached and cached.is_file() and self.wall() - cached.stat().st_mtime < self.ttl_s:
            return cached.read_text(encoding="utf-8")
        if not self._robots_allow(url, policy.min_interval_s):
            raise RobotsDisallowed(f"robots.txt disallows {url}")
        self._pace(host, policy.min_interval_s)
        try:
            r = self.client.get(url)
        except httpx.HTTPError as e:
            raise FetchRefused(f"network error: {type(e).__name__}") from e
        if r.is_redirect:
            target = urljoin(url, r.headers.get("location", ""))
            if policy_for_host(host_of(target)) is not policy:
                raise FetchRefused(f"redirect leaves the source: {target}")
            return self.get_text(target)
        if r.status_code in BLOCK_STATUS:
            self.stopped[host] = f"HTTP {r.status_code}"
            raise Blocked(f"{host}: HTTP {r.status_code}")
        if r.status_code != 200:
            raise FetchRefused(f"{url}: HTTP {r.status_code}")
        low = r.text[:20000].lower()
        if any(m in low for m in BLOCK_MARKERS):
            self.stopped[host] = "human-verification page"
            raise Blocked(f"{host}: human-verification page")
        if cached:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(r.text, encoding="utf-8")
        return r.text
