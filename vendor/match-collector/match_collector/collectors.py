from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from typing import ClassVar
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from .browser import Renderer
from .extract import category_for, embedded_json, extract_page, soup_of, tab_data, walk_json
from .matching import choose, rank_candidates, team_score
from .models import Candidate, Coverage, MatchQuery, SourceReport
from .player_stats import fetch_players
from .team_analysis import collect_team_analysis
from .transport import HOSTS, Document, Fetcher, FetchError, validate_url


class Collector:
    name = ""

    def __init__(self, fetcher: Fetcher, query: MatchQuery):
        self.fetcher, self.query = fetcher, query
        self.report = SourceReport(source=self.name)
        self.renderer = Renderer(fetcher, query.timezone)
        self.pages = 0
        self.documents: dict[str, Document] = {}

    async def get(self, url: str) -> Document:
        if url in self.documents:
            return self.documents[url]
        if self.pages >= self.query.max_pages_per_source:
            raise FetchError(url, "Page budget reached; increase max_pages_per_source for deeper coverage")
        self.pages += 1
        doc = await self.fetcher.get(url)
        self.documents[url] = doc
        return doc

    async def maybe_get(self, url: str) -> Document | None:
        try:
            return await self.get(url)
        except FetchError as exc:
            self.report.warnings.append(str(exc))
            return None

    def select(self, candidates):
        self.report.candidates = rank_candidates(candidates, self.query)
        self.report.match, self.report.status = choose(self.report.candidates)
        return self.report.match

    async def render(self, url: str):
        if not self.query.browser:
            return None
        if self.pages >= self.query.max_pages_per_source:
            self.report.warnings.append("Page budget reached before rendering.")
            return None
        self.pages += 1
        try:
            doc, payloads = await self.renderer.render(url)
            for item in payloads:
                payload = item["value"]
                if (
                    self.name == "soccerway"
                    and isinstance(payload, dict)
                    and isinstance(payload.get("data"), dict)
                ):
                    scorers = payload["data"].get("findEventTopScorersById")
                    if isinstance(scorers, dict) and any(
                        t.get("topScorers") for t in scorers.get("teams") or []
                    ):
                        if not any(
                            r.get("relation") == "team_scorers_context" and r["value"] == scorers
                            for r in self.report.data["players"]
                        ):
                            self.report.add("players", scorers, item["url"], relation="team_scorers_context")
                        continue
                self.report.add(
                    category_for(item["url"]),
                    {"response": item["value"]},
                    item["url"],
                    acquisition="browser_response",
                )
            return doc
        except FetchError as exc:
            self.report.warnings.append(str(exc))
            return None

    async def run(self) -> SourceReport:
        try:
            for url in self.query.seed_urls.get(self.name, []):
                validate_url(url, HOSTS[self.name])
            await self.collect()
            if self.query.include_news and self.query.max_news:
                from .news import collect_news

                await collect_news(self)
            else:
                self.report.coverage["news"] = Coverage(
                    status="disabled", detail="News collection disabled by request."
                )
        except FetchError as exc:
            self.report.warnings.append(str(exc))
            self.report.status = (
                "partial" if self.report.match else ("blocked" if exc.status in (401, 403, 429) else "error")
            )
            for category in self.report.coverage:
                if self.report.coverage[category].status == "not_discovered":
                    self.report.coverage[category] = Coverage(
                        status="blocked" if exc.status in (401, 403, 429) else "unavailable",
                        detail=exc.reason,
                    )
        finally:
            await self.renderer.close()
            self.report.evidence = self.fetcher.evidence
            self.report.limits = {
                "pages_attempted": self.pages,
                "page_budget": self.query.max_pages_per_source,
                "news_limit": self.query.max_news,
                "browser_enabled": self.query.browser,
            }
            if self.pages >= self.query.max_pages_per_source:
                self.report.warnings.append(
                    "Page budget exhausted; undiscovered pages may contain additional data."
                )
            self.report.warnings = list(dict.fromkeys(self.report.warnings))
        return self.report


def soccerway_candidate(doc: Document) -> Candidate | None:
    state = embedded_json(doc.text).get("environment", {})
    sides = state.get("participantsData", {})
    home, away = sides.get("home", []), sides.get("away", [])
    if not home or not away:
        return None
    feed = {k: v for entry in state.get("common_feed", []) for k, v in entry.items()}
    timestamp = feed.get("DC") or feed.get("DD")
    kickoff = datetime.fromtimestamp(timestamp, UTC) if isinstance(timestamp, (int, float)) else None
    event_id = state.get("event_id_c")
    if not event_id:
        return None
    parsed = urlsplit(doc.url)
    args = parse_qs(parsed.query)
    args["mid"] = [event_id]
    url = urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            state.get("basenameUrl", parsed.path) + "/",
            urlencode(args, doseq=True),
            "",
        )
    )
    return Candidate(
        source_id=event_id,
        url=url,
        home=home[0]["name"],
        away=away[0]["name"],
        kickoff=kickoff,
        competition=state.get("header", {}).get("tournament", {}).get("tournament"),
        raw={
            k: v
            for k, v in state.items()
            if k not in {"config", "pushParameters", "odds", "ratingScale", "brandMonochromeLogoPaths"}
        },
    )


class Soccerway(Collector):
    name = "soccerway"
    base = "https://us.soccerway.com"

    async def recent_players(self, html, selected):
        """Look up the most recent completed game listed for each side."""
        remaining = {selected.home, selected.away}
        seen = set()
        for row in soup_of(html).select("a.h2h__row[href]"):
            teams = [n.get_text(" ", strip=True) for n in row.select(".h2h__participant")]
            interested = {t for t in remaining if any(team_score(t, n) >= 0.88 for n in teams)}
            url = urljoin(selected.url, row["href"])
            expected_id = parse_qs(urlsplit(url).query).get("mid", [None])[0]
            if (
                not interested
                or not expected_id
                or expected_id in seen
                or urlsplit(url).hostname not in HOSTS[self.name]
            ):
                continue
            if self.pages + 3 > self.query.max_pages_per_source:
                break
            seen.add(expected_id)
            doc = await self.maybe_get(url)
            previous = soccerway_candidate(doc) if doc else None
            if (
                not previous
                or previous.source_id != expected_id
                or not previous.kickoff
                or previous.kickoff >= selected.kickoff
                or str(previous.raw.get("eventStageTypeId")) != "3"
            ):
                continue
            interested = {
                t
                for t in interested
                if max(team_score(t, previous.home), team_score(t, previous.away)) >= 0.88
            }
            if interested:
                snapshot = await fetch_players(self, previous)
                if any(p["metrics"] or p.get("rating") is not None for p in snapshot["players"]):
                    self.report.add(
                        "recent_player_form",
                        snapshot,
                        previous.url,
                        relation="previous_fixture",
                        requested_teams=sorted(interested),
                    )
                remaining -= interested
            if not remaining:
                break

    def url_relevance(self, url):
        path = urlsplit(url).path
        m = re.search(r"/game/([^/]+)/([^/]+)/", path)
        if not m:
            return 0
        names = [re.sub(r"-[A-Za-z0-9]{8}$", "", n).replace("-", " ") for n in m.groups()]
        a, b = [self.query.opponent_a, *self.query.aliases_a], [self.query.opponent_b, *self.query.aliases_b]
        sim = lambda group, n: max(team_score(x, n) for x in group)
        return max(min(sim(a, names[0]), sim(b, names[1])), min(sim(a, names[1]), sim(b, names[0])))

    async def collect(self):
        root = await self.get(self.base + "/")
        urls = list(self.query.seed_urls.get(self.name, []))
        sitemap_tabs = []
        page = extract_page(root.text, root.url)
        urls.extend(link["url"] for link in page["links"] if self.url_relevance(link["url"]) >= 0.55)
        sitemap = await self.maybe_get(self.base + "/sitemap.xml")
        if sitemap:
            try:
                maps = [
                    e.text
                    for e in ET.fromstring(sitemap.text).iter()
                    if e.tag.endswith("}loc") and e.text and "match" in e.text
                ]
                for map_url in maps[:5]:
                    doc = await self.maybe_get(map_url)
                    if not doc:
                        continue
                    for element in ET.fromstring(doc.text).iter():
                        if (
                            element.tag.endswith("}loc")
                            and element.text
                            and self.url_relevance(element.text) >= 0.55
                        ):
                            sitemap_tabs.append(element.text)
                            m = re.match(r"(https?://[^/]+/game/[^/]+/[^/]+/)", element.text)
                            if m:
                                urls.append(m[1])
            except ET.ParseError:
                self.report.warnings.append("Soccerway sitemap was not valid XML.")
        seeds = self.query.seed_urls.get(self.name, [])
        urls = sorted(dict.fromkeys(urls), key=lambda u: (u in seeds, self.url_relevance(u)), reverse=True)
        candidates, candidate_docs = [], {}
        for url in urls[: max(1, self.query.max_pages_per_source // 2)]:
            doc = await self.maybe_get(url)
            candidate = soccerway_candidate(doc) if doc else None
            if candidate:
                candidates.append(candidate)
                candidate_docs[candidate.source_id] = doc
        selected = self.select(candidates)
        if not selected:
            self.report.warnings.append(
                "Automatic Soccerway discovery covers published sitemap matches. Supply an exact match URL for older/unlisted fixtures; candidates must still pass opponent/date checks."
            )
            return
        doc = candidate_docs[selected.source_id]
        self.report.add("summary", selected.raw, selected.url)
        await collect_team_analysis(self, selected)
        snapshot = await fetch_players(self, selected)
        has_values = any(p["metrics"] or p.get("rating") is not None for p in snapshot["players"])
        if has_values:
            self.report.add("players", snapshot, selected.url, acquisition="player_statistics")
        elif snapshot["players"]:
            self.report.add("extra", snapshot, selected.url, acquisition="roster_without_match_statistics")
        parsed = extract_page(doc.text, doc.url)
        self.report.add("extra", parsed, doc.url, acquisition="html_snapshot")
        preview = selected.raw.get("eventPreview")
        if preview and self.query.include_news and self.query.max_news:
            self.report.add(
                "news",
                preview,
                selected.url,
                relation="match_preview",
                generated=preview.get("type") == "ODDS_PREVIEW",
            )
        rendered = await self.render(selected.url)
        if rendered:
            parsed = extract_page(rendered.text, rendered.url)
            self.report.add("extra", parsed, rendered.url, acquisition="rendered_snapshot")
        match_path = urlsplit(selected.url).path.rstrip("/")
        tabs = sitemap_tabs + [link["url"] for link in parsed["links"]]
        # Give the core match and player sections priority over odds market variants.
        priority = {"players": 0, "lineups": 1, "statistics": 2, "h2h": 3, "incidents": 4}
        tabs.sort(key=lambda u: priority.get(category_for(u), 5))
        seen = set()
        # Only follow tabs of the verified event, pinning its stable match ID.
        for url in tabs:
            parts = urlsplit(url)
            if not parts.path.startswith(match_path + "/") or parts.path.rstrip("/") == match_path:
                continue
            suffix = parts.path[len(match_path) :].strip("/")
            if suffix.split("/")[0] not in {
                "summary",
                "odds",
                "h2h",
                "standings",
                "news",
                "stats",
                "lineups",
            }:
                continue
            if parts.hostname not in HOSTS[self.name]:
                continue
            args = parse_qs(parts.query)
            args["mid"] = [selected.source_id]
            url = urlunsplit(
                (parts.scheme, parts.netloc, parts.path.rstrip("/") + "/", urlencode(args, doseq=True), "")
            )
            if url in seen:
                continue
            seen.add(url)
            doc = await self.maybe_get(url)
            if not doc:
                continue
            candidate = soccerway_candidate(doc)
            if candidate and candidate.source_id != selected.source_id:
                self.report.warnings.append(f"Skipped tab that resolved to a different event: {url}")
                continue
            rendered = await self.render(url)
            page = extract_page((rendered or doc).text, url)
            category = category_for(url)
            # An unrendered tab often contains exactly the same preview as the
            # summary. Preserve it as evidence without claiming lineup/stats data.
            self.report.add("extra", page, url, acquisition="tab_snapshot", requested_category=category)
            records = tab_data((rendered or doc).text, category)
            if (
                category == "h2h"
                and records
                and not has_values
                and not self.report.data["recent_player_form"]
            ):
                await self.recent_players((rendered or doc).text, selected)
            if records:
                self.report.add(category, records, url, acquisition="rendered_tab")
                self.report.coverage[
                    category
                ].detail = "Rendered tab content captured; see raw text/tables and response evidence."
            elif self.report.coverage[category].status != "collected":
                self.report.coverage[category] = Coverage(
                    status="unavailable", detail="Tab captured, but dynamic category data was not verified."
                )
            if self.pages >= self.query.max_pages_per_source:
                break


def ballhelper_candidates(doc: Document, site_timezone: str | None) -> list[Candidate]:
    soup = soup_of(doc.text)
    candidates = []
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) < 3:
            continue
        values = [c.get_text(" ", strip=True) for c in cells]
        if not re.fullmatch(r"\d{1,2}\.\d{1,2}\.\d{4}", values[0]):
            continue
        # Main fixture AND league-results rows use MM.DD.YYYY. Inline H2H
        # entries in following_rows use DD.MM.YYYY and are retained separately.
        fixture = bool(re.fullmatch(r"\d{1,2}:\d{1,2}", values[1]))
        fmt = "%m.%d.%Y"
        try:
            day = datetime.strptime(values[0], fmt).date()
        except ValueError:
            continue
        name_cell = values[2] if fixture else values[1]
        name_cell = re.sub(r"\s*\(\d+\)", "", name_cell)
        sides = re.split(r"\s+-\s+", name_cell, maxsplit=1)
        if len(sides) != 2:
            continue
        stamp = None
        if fixture and site_timezone:
            hour, minute = map(int, values[1].split(":"))
            try:
                stamp = datetime.combine(day, datetime.min.time()).replace(
                    hour=hour, minute=minute, tzinfo=ZoneInfo(site_timezone)
                )
            except ValueError:
                continue
        extras = []
        for sibling in row.find_next_siblings("tr"):
            vals = [c.get_text(" ", strip=True) for c in sibling.find_all(["td", "th"], recursive=False)]
            if vals and (re.fullmatch(r"\d{1,2}\.\d{1,2}\.\d{4}", vals[0]) or " - links" in " ".join(vals)):
                break
            extras.append(vals)
        table = row.find_parent("table")
        league_links = [
            {"url": urljoin(doc.url, a["href"]), "text": a.get_text(" ", strip=True)}
            for a in table.select("a[href]")
        ]
        # The league links are in a separate table immediately following the
        # fixture table in the live layout (not children of the fixture row).
        if not league_links:
            following = table.find_next("table")
            for _ in range(12):
                if following is None:
                    break
                if " - links" in following.get_text(" ", strip=True):
                    league_links = [
                        {"url": urljoin(doc.url, a["href"]), "text": a.get_text(" ", strip=True)}
                        for a in following.select("a[href]")
                    ]
                    break
                if following.find_parent("table") is not table and following.select("td font[color='blue']"):
                    break
                following = following.find_next("table")
        key = f"{day}|{sides[0]}|{sides[1]}"
        candidates.append(
            Candidate(
                source_id=hashlib.sha256(key.encode()).hexdigest()[:20],
                url=doc.url,
                home=sides[0],
                away=sides[1],
                kickoff=stamp,
                source_date=day,
                date_basis="configured_site_timezone" if stamp else "source_wall_date_timezone_unknown",
                raw={
                    "row": values,
                    "following_rows": extras,
                    "league_links": league_links,
                    "date_format": fmt,
                    "source_time": values[1] if fixture else None,
                },
            )
        )
    return candidates


class Ballhelper(Collector):
    name = "ballhelper"
    base = "http://www.ballhelper.com"

    async def collect(self):
        self.report.warnings.append(
            "Ballhelper is served over unencrypted HTTP; HTTPS currently has a hostname certificate mismatch."
        )
        urls = [
            *self.query.seed_urls.get(self.name, []),
            self.base + "/",
            self.base + "/meny-en/weekly-match-review.php",
        ]
        candidates = []
        for url in dict.fromkeys(urls):
            doc = await self.get(url)
            candidates.extend(ballhelper_candidates(doc, self.query.ballhelper_timezone))
        selected = self.select(candidates)
        # Retain relevant source rows even when the unadvertised source timezone
        # prevents verification of the requested UTC day.
        relevant = selected or (self.report.candidates[0] if len(self.report.candidates) == 1 else None)
        if relevant is None:
            self.report.warnings.append(
                "Ballhelper's automatic discovery covers its current weekly window and supplied league/result URLs. No full historical index is exposed here."
            )
            return
        verified = selected is not None
        self.report.add("summary", relevant.raw, relevant.url, match_date_verified=verified)
        if not verified:
            self.report.warnings.append(
                "Relevant fixture found, but Ballhelper does not advertise a timezone. Its date cannot be verified as UTC. Set ballhelper_timezone only after establishing the site's convention."
            )
        rows = relevant.raw.get("following_rows", [])
        if rows:
            self.report.add("statistics", {"source_rows": rows}, relevant.url, match_date_verified=verified)
            history = [r for r in rows if re.search(r"\d{1,2}\.\d{1,2}\.\d{4}", " ".join(r))]
            if history:
                self.report.add(
                    "h2h",
                    {"rows": history, "date_format": "DD.MM.YYYY"},
                    relevant.url,
                    match_date_verified=verified,
                )
        links = list(relevant.raw.get("league_links", []))
        seen = set()
        while links:
            link = links.pop(0)
            if link["url"] in seen:
                continue
            seen.add(link["url"])
            if urlsplit(link["url"]).hostname not in HOSTS[self.name]:
                continue
            doc = await self.maybe_get(link["url"])
            if not doc:
                continue
            label = link["text"].lower()
            path = urlsplit(doc.url).path
            details = (
                "fixtures-and-results",
                "statistics",
                "results-for-teams",
                "goals",
                "first-half-second-half",
            )
            category = (
                "standings" if "table" in label or not any(word in path for word in details) else "statistics"
            )
            parsed = extract_page(doc.text, doc.url)
            self.report.add(
                category,
                parsed,
                doc.url,
                relation="league_context",
                match_date_verified=verified,
            )
            # The weekly page sometimes only links the league landing page.
            # Follow that league's published result/stat pages within the budget.
            folder = path.rsplit("/", 1)[0] + "/"
            links.extend(
                item
                for item in parsed["links"]
                if urlsplit(item["url"]).path.startswith(folder)
                and any(word in urlsplit(item["url"]).path for word in details)
                and item["url"] not in seen
            )
            if self.pages >= self.query.max_pages_per_source:
                break


def sofascore_candidate(event: dict, base="https://www.sofascore.com") -> Candidate | None:
    if not all(k in event for k in ("id", "homeTeam", "awayTeam", "startTimestamp")):
        return None
    if not isinstance(event["homeTeam"], dict) or not isinstance(event["awayTeam"], dict):
        return None
    if not isinstance(event["startTimestamp"], (float, int)):
        return None
    return Candidate(
        source_id=str(event["id"]),
        url=f"{base}/api/v1/event/{event['id']}",
        home=event["homeTeam"].get("name", ""),
        away=event["awayTeam"].get("name", ""),
        kickoff=datetime.fromtimestamp(event["startTimestamp"], UTC),
        competition=event.get("tournament", {}).get("name"),
        raw=event,
    )


class Sofascore(Collector):
    name = "sofascore"
    base = "https://www.sofascore.com"
    sections: ClassVar[dict[str, str]] = {
        "statistics": "statistics",
        "lineups": "lineups",
        "incidents": "incidents",
        "shotmap": "players",
        "average-positions": "players",
        "graph": "extra",
        "h2h": "h2h",
        "pregame-form": "h2h",
        "odds/1/all": "odds",
        "managers": "lineups",
        "best-players": "players",
        "highlights": "extra",
    }

    async def collect(self):
        import json

        candidates = []
        for url in self.query.seed_urls.get(self.name, []):
            # Sofascore match pages often select a historical event in #id:...
            # Keep that event identity before the HTTP transport removes fragments.
            event_id = re.search(r"(?:#id:|[?&]id=)(\d+)", url)
            if event_id:
                url = f"{self.base}/api/v1/event/{event_id.group(1)}"
            doc = await self.get(url)
            try:
                values = json.loads(doc.text)
            except ValueError:
                values = embedded_json(doc.text)
            candidates.extend(c for x in walk_json(values) if (c := sofascore_candidate(x)))
        if not candidates:
            # UTC schedule buckets can straddle a user's local calendar day.
            local_start = datetime.combine(
                self.query.date, datetime.min.time(), ZoneInfo(self.query.timezone)
            )
            local_end = local_start + timedelta(days=1) - timedelta(microseconds=1)
            day, last = local_start.astimezone(UTC).date(), local_end.astimezone(UTC).date()
            while day <= last:
                url = f"{self.base}/api/v1/sport/football/scheduled-events/{day.isoformat()}"
                doc = await self.get(url)
                try:
                    schedule = json.loads(doc.text)
                except ValueError as exc:
                    raise FetchError(url, "Schedule endpoint did not return JSON") from exc
                candidates.extend(c for e in schedule.get("events", []) if (c := sofascore_candidate(e)))
                day += timedelta(days=1)
        selected = self.select(candidates)
        if not selected:
            return
        event_url = f"{self.base}/api/v1/event/{selected.source_id}"
        doc = await self.get(event_url)
        event = json.loads(doc.text).get("event", selected.raw)
        current = sofascore_candidate(event)
        if (
            current is None
            or current.source_id != selected.source_id
            or not rank_candidates([current], self.query)
        ):
            raise FetchError(event_url, "Event identity changed between discovery and collection")
        self.report.add("summary", event, event_url)
        for suffix, category in self.sections.items():
            url = event_url + "/" + suffix
            doc = await self.maybe_get(url)
            if doc:
                try:
                    value = json.loads(doc.text)
                    self.report.add(category, value, url)
                except ValueError:
                    self.report.warnings.append(f"Expected JSON for {url}")
            elif self.report.coverage[category].status != "collected":
                self.report.coverage[category] = Coverage(
                    status="unavailable", detail="Endpoint unavailable; see evidence."
                )
        tournament = event.get("tournament", {}).get("uniqueTournament", {}).get("id")
        season = event.get("season", {}).get("id")
        if tournament and season:
            for side in ("total", "home", "away"):
                url = f"{self.base}/api/v1/unique-tournament/{tournament}/season/{season}/standings/{side}"
                doc = await self.maybe_get(url)
                if doc:
                    try:
                        self.report.add("standings", json.loads(doc.text), url, relation="season_context")
                    except ValueError:
                        self.report.warnings.append(f"Expected JSON for {url}")
        self.report.warnings.append(
            "Sofascore website endpoints are undocumented and may change. Optional endpoint failures are recorded individually."
        )
