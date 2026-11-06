"""ballhelper.com league pages: table with home and away splits, and which half each team outscored in recent matches.

Plain server-rendered HTML. It covers domestic leagues, not cups or European competitions, so it needs each team's league.
A row is only reported if its numbers add up, because a silently shifted column would otherwise publish wrong statistics.
"""
from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import urljoin

from match_data_collector.contract import Fact, Gap, MatchQuery, Source
from match_data_collector.fetch import FetchRefused, PoliteFetcher
from match_data_collector.policy import POLICIES

HOME_URL = "http://www.ballhelper.com/"
LEAGUE_ALIASES = {"premier league": "england prem.", "english premier league": "england prem.", "la liga": "spain 1",
                  "serie a": "italy a", "bundesliga": "germany 1", "ligue 1": "france 1", "eredivisie": "holland 1",
                  "primeira liga": "portugal 1", "super league greece": "greece 1", "greek super league": "greece 1"}
HALF_CODES = {"I>": "first", "II>": "second", "I=II": "level"}


class _Page(HTMLParser):
    """Collects links, innermost tables with the heading before each, and the page's update note."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.tables: list[dict] = []
        self.stack: list[dict] = []
        self.heading, self.text_log = "", []
        self._a, self._a_text, self._cell = None, [], None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._a, self._a_text = dict(attrs).get("href"), []
        elif tag == "table":
            self.stack.append({"heading": self.heading, "rows": [], "nested": False})
            if len(self.stack) > 1:
                self.stack[-2]["nested"] = True
        elif tag == "tr" and self.stack:
            self.stack[-1]["rows"].append([])
        elif tag in ("td", "th") and self.stack and self.stack[-1]["rows"]:
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "a" and self._a is not None:
            self.links.append(("".join(self._a_text).strip(), self._a))
            self._a = None
        elif tag in ("td", "th") and self._cell is not None:
            if self.stack and self.stack[-1]["rows"]:
                self.stack[-1]["rows"][-1].append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "table" and self.stack:
            t = self.stack.pop()
            if not t["nested"]:
                self.tables.append(t)

    def handle_data(self, data):
        if self._a is not None:
            self._a_text.append(data)
        if self._cell is not None:
            self._cell.append(data)
        s = " ".join(data.split())
        if s:
            self.text_log.append(s)
            if len(s) >= 3 and not s.isdigit():
                self.heading = s


def parse(html: str) -> _Page:
    p = _Page()
    p.feed(html)
    return p


def _norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(fc|cf|afc|sc|ac|club|de|the)\b", " ", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def find_team(names: list[str], wanted: str) -> tuple[str | None, str]:
    """Returns (matched name, "") or (None, "not_found" | "ambiguous")."""
    w = _norm(wanted)
    exact = [n for n in names if _norm(n) == w]
    if len(exact) == 1:
        return exact[0], ""
    near = [n for n in names if w and (w in _norm(n) or _norm(n) in w)]
    if len(near) == 1:
        return near[0], ""
    return None, "ambiguous" if near else "not_found"


def league_rows(page: _Page) -> list[dict]:
    """The main table: position, team, played, W D L GF GA, home W D L GF GA, away W D L GF GA, points (19 cells)."""
    out = []
    for t in page.tables:
        # The site's HTML sometimes omits a </tr>, which joins two teams into one row.
        split = [r[i:i + 19] for r in t["rows"] if len(r) % 19 == 0 for i in range(0, len(r), 19)]
        rows = [r for r in split if r[0].isdigit() and all(c.isdigit() for c in r[2:])]
        if len(rows) >= 4:
            for r in rows:
                n = [int(c) for c in r[2:]]
                out.append({"position": int(r[0]), "team": r[1], "played": n[0], "won": n[1], "drawn": n[2], "lost": n[3],
                            "goals_for": n[4], "goals_against": n[5],
                            "home": dict(zip(("won", "drawn", "lost", "goals_for", "goals_against"), n[6:11])),
                            "away": dict(zip(("won", "drawn", "lost", "goals_for", "goals_against"), n[11:16])),
                            "points": n[16], "raw": " ".join(r)})
            return out
    return out


def row_adds_up(r: dict) -> bool:
    h, a = r["home"], r["away"]
    return (r["won"] + r["drawn"] + r["lost"] == r["played"]
            and all(h[k] + a[k] == r[k] for k in ("won", "drawn", "lost", "goals_for", "goals_against"))
            and r["points"] == 3 * r["won"] + r["drawn"])


def half_tables(page: _Page) -> dict[str, dict[str, dict]]:
    """Per venue, per team: how many recent matches had more goals in the first half, the second, or level."""
    out: dict[str, dict[str, dict]] = {}
    for t in page.tables:
        m = re.search(r"Score more goals table as (Home|Away)", t["heading"], re.I)
        if not m:
            continue
        venue = m.group(1).lower()
        for r in t["rows"]:
            codes = [c for c in r[1:] if c]
            if len(r) >= 2 and r[0] and codes and all(c in HALF_CODES for c in codes):
                counts = {"first": 0, "second": 0, "level": 0}
                for c in codes:
                    counts[HALF_CODES[c]] += 1
                out.setdefault(venue, {})[r[0]] = {**counts, "matches": len(codes), "raw": " ".join(r)}
    return out


class BallhelperAdapter:
    name = "ballhelper"

    def __init__(self, fetcher: PoliteFetcher):
        self.fetcher = fetcher
        self._menu: dict[str, str] | None = None

    def _league_url(self, league: str) -> str | None:
        if self._menu is None:
            page = parse(self.fetcher.get_text(HOME_URL))
            self._menu = {t.lower(): urljoin(HOME_URL, h) for t, h in page.links if t and "/soccer-football/" in (h or "")}
        key = league.strip().lower()
        return self._menu.get(LEAGUE_ALIASES.get(key, key))

    def _src(self, url: str, title: str, quote: str, now: str) -> Source:
        return Source(adapter=self.name, kind="web", retrieved_at=now, url=url, publisher="ballhelper", title=title[:200],
                      tier=POLICIES[self.name].tier, quote=quote[:400])

    def _side(self, side: str, team: str, league: str | None, now: str) -> tuple[list[Fact], list[Gap]]:
        need = f"{side}.league"
        if not league:
            return [], [Gap(self.name, need, "not_covered", f"no domestic league given for {team}; this source is organised by league")]
        try:
            url = self._league_url(league)
            if not url:
                return [], [Gap(self.name, need, "not_covered", f"league {league!r} is not in the site's menu")]
            page = parse(self.fetcher.get_text(url))
        except FetchRefused as e:
            return [], [Gap(self.name, need, e.reason, str(e))]
        rows = league_rows(page)
        if not rows:
            return [], [Gap(self.name, need, "parse_mismatch", f"no league table recognised at {url}")]
        name, why = find_team([r["team"] for r in rows], team)
        if not name:
            return [], [Gap(self.name, need, why, f"{team!r} in {url}")]
        row = next(r for r in rows if r["team"] == name)
        if not row_adds_up(row):
            return [], [Gap(self.name, need, "parse_mismatch", f"the row for {name} does not add up: {row['raw']}")]
        title = next((s for s in page.text_log if "league table" in s.lower() or "season" in s.lower()), league)
        # Kept as printed: "11.5.2026" could be 5 November or 11 May, so it is not converted into an as_of date.
        updated = next((s for s in page.text_log if s.lower().startswith("last updated")), None)
        facts = []

        def add(key, value, label, unit=None):
            facts.append(Fact(key=f"{side}.{key}", value=value, statement=f"{name} in {league}: {label} {value}.",
                              source=self._src(url, title, row["raw"], now), unit=unit, as_of=None, confidence="low"))
        for k in ("position", "played", "won", "drawn", "lost", "goals_for", "goals_against", "points"):
            add(f"league.{k}", row[k], k.replace("_", " "))
        for venue in ("home", "away"):
            for k, v in row[venue].items():
                add(f"league.{venue}.{k}", v, f"{venue} {k.replace('_', ' ')}")
        halves = half_tables(page)
        gaps = []
        for venue in ("home", "away"):
            hn, _ = find_team(list(halves.get(venue, {})), team)
            if not hn:
                gaps.append(Gap(self.name, f"{side}.half_pattern.{venue}", "parse_mismatch", f"no half table row for {team} ({venue})"))
                continue
            h = halves[venue][hn]
            value = {k: h[k] for k in ("first", "second", "level", "matches")}
            facts.append(Fact(key=f"{side}.half_pattern.{venue}", value=value,
                              statement=f"{name}'s last {h['matches']} {venue} matches in {league}: more goals in the first half {h['first']}, "
                                        f"second half {h['second']}, level {h['level']}.",
                              source=self._src(url, title, h["raw"], now), confidence="low"))
        if updated:
            facts.append(Fact(key=f"{side}.league.page_note", value=updated, statement=f"The {league} page says: {updated}.",
                              source=self._src(url, title, updated, now), confidence="low"))
        return facts, gaps

    def collect(self, query: MatchQuery, now_iso: str) -> tuple[list[Fact], list[Gap]]:
        hf, hg = self._side("home", query.home, query.home_league, now_iso)
        af, ag = self._side("away", query.away, query.away_league, now_iso)
        return hf + af, hg + ag
