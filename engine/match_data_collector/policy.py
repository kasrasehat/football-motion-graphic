"""What the collector may touch, and why. Permission is a recorded decision per source, never a technical workaround."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class SourcePolicy:
    name: str
    hosts: tuple[str, ...]
    status: str  # "allowed" | "needs_permission"
    reason: str
    tier: int = 3
    min_interval_s: float = 3.0
    evidence: tuple[str, ...] = ()


# Checked 2026-11-05. Re-check terms before relying on these, and record any permission where the caller can audit it.
POLICIES: dict[str, SourcePolicy] = {
    "ballhelper": SourcePolicy(
        "ballhelper", ("ballhelper.com",), "allowed",
        "robots.txt returns 404 and the homepage links no terms; no API. Betting-tips site, so treat as low trust.",
        evidence=("http://www.ballhelper.com/robots.txt",)),
    "soccerway": SourcePolicy(
        "soccerway", ("soccerway.com",), "needs_permission",
        "Terms 2.9 and 2.10 bar extraction and scraping without express consent; robots.txt disallows /football/.",
        tier=2, evidence=("https://us.soccerway.com/terms-of-use/", "https://us.soccerway.com/robots.txt")),
    "sofascore": SourcePolicy(
        "sofascore", ("sofascore.com",), "needs_permission",
        "No public API, by the site's own statement. Pages returned a human-verification check; it is not to be bypassed.",
        tier=2, evidence=("https://sofascore.helpscoutdocs.com/article/129-sports-data-api-availability",)),
}


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def host_matches(host: str, allowed: str) -> bool:
    return host == allowed or host.endswith("." + allowed)


def policy_for_host(host: str) -> SourcePolicy | None:
    return next((p for p in POLICIES.values() if any(host_matches(host, h) for h in p.hosts)), None)
