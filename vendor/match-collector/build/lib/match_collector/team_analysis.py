"""Stage-specific Soccerway history and separately timestamped published tables."""

import re
from datetime import UTC, datetime
from html import unescape
from urllib.parse import urljoin, urlsplit

from .transport import HOSTS, FetchError

GOAL_LINES = (0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5)
RESULTS_FEED = re.compile(r"""initialFeeds\[['"]results['"]\]\s*=\s*\{\s*data:\s*`([^`]+)`""")


def preview_markets(preview, event_id):
    """Keep the publisher's forecast separate from observed match outcomes."""
    if not isinstance(preview, dict) or preview.get("eventId") != event_id:
        return {}
    result = {}
    for paragraph in re.findall(r"\[p\](.*?)\[/p\]", preview.get("contentParsed") or "", re.DOTALL):
        line = unescape(re.sub(r"\[[^\]]+\]", "", paragraph)).strip(" -")
        prefix = "Win probability based on the average odds:"
        if line.startswith(prefix):
            percentages = re.findall(r"(?:^|,)\s*([^,:]+?):\s*(\d+(?:\.\d+)?)%", line[len(prefix) :])
            if percentages:
                result["result_percentages"] = {label.strip(): float(pct) for label, pct in percentages}
        if line.startswith("Score prediction:"):
            result["score_prediction"] = line.removeprefix("Score prediction:").strip()
    return result


def records(feed):
    for group in feed.split("~"):
        yield dict(field.split("÷", 1) for field in group.split("¬") if "÷" in field)


def score(row, home_key, away_key):
    values = [row.get(home_key, ""), row.get(away_key, "")]
    return [int(v) for v in values] if all(v.isdecimal() for v in values) else None


def truncated_results(html):
    match = RESULTS_FEED.search(html)
    if not match:
        return True
    count = re.match(r"\s*,\s*allEventsCount:\s*(\d+)", html[match.end() :])
    loaded = sum("AA" in row for row in records(match[1]))
    return loaded < int(count[1]) if count else loaded >= 100


def prior_results(html, stage, cutoff, target_id, team_ids):
    feeds = RESULTS_FEED.findall(html)
    games = {}
    for feed in feeds:
        active = None
        for row in records(feed):
            if "ZA" in row or "ZC" in row:
                active = row.get("ZC")
            event = row.get("AA")
            if active != stage or not event or event == target_id:
                continue
            if not team_ids.intersection((row.get("PX"), row.get("PY"))):
                continue
            # AC=3 is a regular full-time result. Exclude abandoned games,
            # shootouts and extra-time scores from regulation-time markets.
            ft = score(row, "AG", "AH")
            if row.get("AC") != "3" or ft is None or not row.get("AD", "").isdigit():
                continue
            start = int(row["AD"])
            end = row.get("AO", "")
            if start >= cutoff or (end.isdecimal() and int(end) >= cutoff):
                continue
            # BC/BD are second-half goals in this results feed.
            second_half = score(row, "BC", "BD")
            half_time = None
            if second_half and all(part <= total for part, total in zip(second_half, ft)):
                half_time = [total - part for total, part in zip(ft, second_half)]
            games[event] = {
                "event_id": event,
                "kickoff": datetime.fromtimestamp(start, UTC).isoformat(),
                "home": row.get("AE"),
                "away": row.get("AF"),
                "home_id": row.get("PX"),
                "away_id": row.get("PY"),
                "ft": ft,
                "ht": half_time,
            }
    return sorted(games.values(), key=lambda g: g["kickoff"], reverse=True)


def outcome(a, b):
    return "W" if a > b else "L" if a < b else "D"


def summarize(games, team_id, venue):
    sample = []
    for g in games:
        if team_id not in (g["home_id"], g["away_id"]):
            continue
        home = g["home_id"] == team_id
        if venue in ("overall", "home" if home else "away"):
            sample.append((g, 0 if home else 1))
    wdl = dict.fromkeys("WDL", 0)
    ht_ft = {f"{h}/{f}": 0 for h in "WDL" for f in "WDL"}
    form, totals = [], []
    gf = ga = btts = 0
    for game, side in sample:
        a, b = game["ft"][side], game["ft"][1 - side]
        result = outcome(a, b)
        wdl[result] += 1
        gf += a
        ga += b
        btts += int(min(a, b) > 0)
        form.append(result)
        totals.append(a + b)
        if game["ht"] is not None:
            half = game["ht"]
            ht_ft[f"{outcome(half[side], half[1 - side])}/{result}"] += 1
    n = len(sample)
    return {
        "played": n,
        "wdl": wdl,
        "points": 3 * wdl["W"] + wdl["D"],
        "goals_for": gf,
        "goals_against": ga,
        "average_total_goals": round((gf + ga) / n, 3) if n else None,
        "form_newest_first": form,
        "btts": {"yes": btts, "no": n - btts},
        "double_chance": {
            "win_or_draw": n - wdl["L"],
            "win_or_loss": n - wdl["D"],
            "draw_or_loss": n - wdl["W"],
        },
        "goal_lines": {
            str(line): {"over": sum(t > line for t in totals), "under": sum(t < line for t in totals)}
            for line in GOAL_LINES
        },
        "ht_ft_sample": sum(ht_ft.values()),
        "ht_ft": ht_ft,
        "event_ids": [g["event_id"] for g, _ in sample],
    }


def published_totals(feed, team_ids, venue):
    rows = []
    scope = line = None
    current = None
    for r in records(feed):
        if "TZS" in r:
            scope = r["TZS"].lower()
        if "ETI" in r:
            line = r["ETI"]
            current = None
        if "TR" in r:
            current = None
            if scope == venue and line in {str(x) for x in GOAL_LINES} and r.get("TI") in team_ids:
                if not all(r.get(k, "").isdigit() for k in ("TM", "OUO", "OUU")):
                    continue
                current = {
                    "team_id": r["TI"],
                    "team": r.get("TN"),
                    "venue": venue,
                    "line": line,
                    "rank": r["TR"],
                    "played": int(r["TM"]),
                    "over": int(r["OUO"]),
                    "under": int(r["OUU"]),
                    "goals": r.get("TG"),
                    "goals_per_game": r.get("TGM"),
                    "last_five": [],
                }
                rows.append(current)
        if current is not None and r.get("LMS") in ("+", "-"):
            current["last_five"].append({"event_id": r.get("LME"), "result": r["LMS"]})
    return rows


async def collect_team_analysis(collector, match):
    raw = match.raw
    forecast = preview_markets(raw.get("eventPreview"), match.source_id)
    if forecast:
        collector.report.add("team_analysis", forecast, match.url, relation="publisher_match_forecast")
    stage = (raw.get("stats2_config") or {}).get("tournamentStage")
    league_path = ((raw.get("header") or {}).get("tournament") or {}).get("link")
    sides = raw.get("participantsData") or {}
    if not stage or not league_path or not match.kickoff or not all(sides.get(k) for k in ("home", "away")):
        return
    teams = [sides[k][0] for k in ("home", "away")]
    ids = {t.get("id") for t in teams}
    if None in ids or len(ids) != 2:
        return
    url = urljoin(match.url, league_path.rstrip("/") + "/results/")
    if urlsplit(url).hostname not in HOSTS["soccerway"]:
        return
    doc = await collector.maybe_get(url)
    games = prior_results(doc.text, stage, match.kickoff.timestamp(), match.source_id, ids) if doc else []
    history_urls = [doc.url] if doc else []
    if not doc or truncated_results(doc.text) or not games:
        merged = {game["event_id"]: game for game in games}
        for team in teams:
            path = team.get("detail_link")
            if not path:
                continue
            team_url = urljoin(match.url, path.rstrip("/") + "/results/")
            if urlsplit(team_url).hostname not in HOSTS["soccerway"]:
                continue
            team_doc = await collector.maybe_get(team_url)
            if team_doc:
                history_urls.append(team_doc.url)
                for game in prior_results(
                    team_doc.text, stage, match.kickoff.timestamp(), match.source_id, {team["id"]}
                ):
                    merged.setdefault(game["event_id"], game)
        games = sorted(merged.values(), key=lambda game: game["kickoff"], reverse=True)
    if games:
        collector.report.add(
            "team_analysis",
            {
                "stage_id": stage,
                "before_kickoff": match.kickoff.isoformat(),
                "games": games,
                "results_urls": history_urls,
                "scope": "Completed regulation-time games in the loaded competition results for this stage before kickoff. Counts describe this sample; older rounds can be absent.",
                "perspective": "W/D/L and HT/FT are relative to the named team. Double-chance counts overlap. Historical counts are not bookmaker prices.",
                "teams": [
                    {
                        "team": t.get("name"),
                        "team_id": t["id"],
                        "splits": {v: summarize(games, t["id"], v) for v in ("overall", "home", "away")},
                    }
                    for t in teams
                ],
            },
            url,
            relation="prior_competition_results",
        )
    else:
        collector.report.warnings.append("No eligible competition results found for pre-match team analysis.")
    # The competition table on either team's page contains both teams.
    path = teams[1].get("detail_link")
    if not collector.query.browser or not path:
        return
    for venue in ("overall", "home", "away"):
        if collector.pages >= collector.query.max_pages_per_source:
            break
        url = urljoin(match.url, f"{path.rstrip('/')}/standings/{stage}/over_under/{venue}/2.5/")
        if urlsplit(url).hostname not in HOSTS["soccerway"]:
            continue
        collector.pages += 1
        try:
            doc, payloads = await collector.renderer.render(url)
        except FetchError as exc:
            collector.report.warnings.append(str(exc))
            continue
        found = False
        for payload in payloads:
            if f"_{stage}_" not in urlsplit(payload["url"]).path or not isinstance(payload["value"], dict):
                continue
            rows = published_totals(payload["value"].get("text", ""), ids, venue)
            if rows:
                found = True
                collector.report.add(
                    "team_analysis",
                    {
                        "rows": rows,
                        "stage_id": stage,
                        "view_url": url,
                        "as_of": doc.evidence.fetched_at.isoformat(),
                    },
                    payload["url"],
                    relation="published_totals_at_collection_time",
                )
        if not found:
            collector.report.warnings.append(f"No published {venue} totals rows were captured at {url}")
