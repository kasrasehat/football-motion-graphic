from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup


def soup_of(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def embedded_json(html: str) -> dict:
    soup = soup_of(html)
    result = {}
    for i, tag in enumerate(soup.find_all("script")):
        text = tag.get_text()
        if tag.get("type", "") in {"application/json", "application/ld+json"}:
            try:
                result[tag.get("id") or f"{tag.get('type')}:{i}"] = json.loads(text)
            except ValueError:
                pass
        for name in ("environment", "__INITIAL_STATE__", "__PRELOADED_STATE__"):
            m = re.search(r"(?:window\.)?" + re.escape(name) + r"\s*=\s*", text)
            if m:
                try:
                    result[name] = json.JSONDecoder().raw_decode(text[m.end() :])[0]
                except ValueError:
                    pass
    return result


def extract_page(html: str, url: str) -> dict:
    soup = soup_of(html)
    structured = embedded_json(html)
    # Do not mix site configuration and advertising identifiers into match fields.
    if isinstance(structured.get("environment"), dict):
        structured["environment"] = {
            k: v
            for k, v in structured["environment"].items()
            if k not in {"config", "pushParameters", "ratingScale", "brandMonochromeLogoPaths"}
        }
    metadata = {}
    for tag in soup.select("meta[content]"):
        key = tag.get("property") or tag.get("name") or tag.get("itemprop")
        if key:
            metadata.setdefault(key, []).append(tag["content"])
    links = list(
        {
            urljoin(url, a["href"]): a.get_text(" ", strip=True)
            for a in soup.select("a[href]")
            if a["href"] and not a["href"].startswith(("javascript:", "mailto:"))
        }.items()
    )
    tables = []
    for table in soup.find_all("table"):
        rows = [
            [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"], recursive=False)]
            for row in table.find_all("tr")
            if row.find_parent("table") is table
        ]
        if rows:
            tables.append(
                {"caption": table.caption.get_text(" ", strip=True) if table.caption else None, "rows": rows}
            )
    for tag in soup.select("script, style, noscript, svg"):
        tag.decompose()
    main = soup.select_one("main, #detail, #mc, article") or soup.body or soup
    headings = [{"level": h.name, "text": h.get_text(" ", strip=True)} for h in main.select("h1,h2,h3,h4")]
    media = [
        {"type": t.name, "url": urljoin(url, t.get("src") or t.get("data-src") or ""), "alt": t.get("alt")}
        for t in main.select("img[src],video[src],audio[src],iframe[src]")
    ]
    return {
        "title": soup.title.get_text(" ", strip=True) if soup.title else "",
        "metadata": metadata,
        "text": main.get_text("\n", strip=True),
        "headings": headings,
        "tables": tables,
        "embedded": structured,
        "links": [{"url": u, "text": t} for u, t in links],
        "media": media,
    }


def walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def category_for(url: str) -> str:
    value = url.lower()
    for words, category in [
        (("player-stat", "heatmap", "shotmap", "average-position"), "players"),
        (("lineup", "formation", "missing-player"), "lineups"),
        (("statistic", "/stats"), "statistics"),
        (("incident", "commentary", "timeline"), "incidents"),
        (("head-to-head", "/h2h"), "h2h"),
        (("standing", "/table"), "standings"),
        (("odds", "probability"), "odds"),
        (("news", "article", "preview"), "news"),
    ]:
        if any(w in value for w in words):
            return category
    return "extra"


def tab_data(html: str, category: str) -> dict | None:
    """Require category-specific rows, not merely changed navigation or a preview."""
    selectors = {
        "statistics": '.stat__row, [data-testid="wcl-statistics"], [class*="statisticsRow"]',
        "lineups": '.lf__lineUp, .lf__formation, [class*="lineups__player"], [data-testid="lineup-player"]',
        "players": '.playerStats__row, [class*="playerStats"] tr, [data-testid="player-statistics-row"]',
        "h2h": ".h2h__row",
        "standings": '.ui-table__row, [data-testid="standings-row"]',
        "odds": '.oddsCell__odd, [data-testid="odds-cell"]',
        "incidents": '.smv__incident, [data-testid="wcl-commentary"]',
    }
    soup = soup_of(html)
    if category == "lineups":
        players = []
        for node in soup.select('[data-testid="wcl-participantPitch"]'):
            person = node.select_one('a[href*="/player/"]')
            if person is None:
                person = node.select_one('[data-testid="wcl-lineupsParticipantName"] button')
            if not person:
                continue
            formation = node.find_parent(class_=lambda c: c and c.startswith("fp-formation_"))
            classes = formation.get("class", []) if formation else []
            side = next((s for s in ("home", "away") if any(c.startswith(f"fp-{s}_") for c in classes)), None)
            players.append(
                {
                    "name": person.get_text(" ", strip=True),
                    "profile_path": person.get("href"),
                    "player_id": node.get("data-analytics-player-id"),
                    "side": side,
                    "source_text": node.get_text(" ", strip=True),
                }
            )
        if players:
            label = (
                "predicted"
                if soup.find(string=lambda t: t and "predicted lineups" in t.lower() and len(t) < 100)
                else "listed"
            )
            return {"lineup_type": label, "on_pitch": players}
    nodes = soup.select(selectors.get(category, ".no-such-collector-category"))
    rows = [
        {"text": n.get_text(" ", strip=True), "html": str(n)} for n in nodes if n.get_text(" ", strip=True)
    ]
    return {"rows": rows} if rows else None
