"""Soccerway's match page loads a roster and a separate set of metric values."""

from __future__ import annotations

import json
from urllib.parse import urlencode


def player_snapshot(roster: dict, details: dict) -> dict:
    teams = {team["id"]: team for team in roster.get("teams") or []}
    players = {}

    def player(pid):
        return players.setdefault(pid, {"player_id": pid, "metrics": {}})

    for member in roster.get("players") or []:
        person = member.get("participant") or {}
        if person.get("id"):
            team = teams.get(member.get("teamId"), {})
            player(person["id"]).update(
                name=person.get("name"),
                team=team.get("name"),
                side=team.get("side"),
                position=(member.get("position") or {}).get("name"),
                starting_lineup=member.get("inBaseLineup"),
            )

    stats = details.get("stats") or {}
    for entry in stats.get("entries") or []:
        pid, metric = entry.get("playerId"), entry.get("typeId")
        if pid and metric:
            player(pid)["metrics"].setdefault(metric, []).append(
                {k: entry[k] for k in ("value", "rawValue", "rank") if k in entry}
            )
    for item in details.get("ratings") or []:
        if item.get("participantId"):
            player(item["participantId"])["rating"] = item.get("value")
    for field, label in (("playerRoles", "role_breakdown"), ("bonuses", "bonuses")):
        for item in stats.get(field) or []:
            if item.get("playerId"):
                player(item["playerId"])[label] = item
    catalog = roster.get("stats") or {}
    return {
        "players": list(players.values()),
        "metric_definitions": catalog.get("types") or [],
        "metric_groups": catalog.get("typeGroups") or [],
        "teams": list(teams.values()),
    }


async def fetch_players(collector, match):
    endpoint = "https://2035.ds.lsapp.eu/pq_graphql?"

    async def read(parameters):
        url = endpoint + urlencode(parameters)
        doc = await collector.maybe_get(url)
        if doc:
            try:
                body = json.loads(doc.text)
                event = (body.get("data") or {}).get("findEventPMSById")
                if isinstance(event, dict):
                    return event, url
                if body.get("errors"):
                    collector.report.warnings.append(f"Player statistics service reported an error for {url}")
            except (ValueError, AttributeError):
                collector.report.warnings.append(f"Unexpected player statistics response for {url}")
        return {}, url

    roster, roster_url = await read({"_hash": "epmsse", "eventId": match.source_id, "projectId": 2035})
    provider = (roster.get("updateFeedProviderId") or {}).get("id")
    details = {}
    urls = [roster_url]
    if provider is not None:
        details, values_url = await read(
            {"_hash": "epmsd", "eventId": match.source_id, "providerId": provider}
        )
        urls.append(values_url)
    result = player_snapshot(roster, details)
    result.update(
        event_id=match.source_id,
        home=match.home,
        away=match.away,
        kickoff=match.kickoff.isoformat(),
        evidence_urls=urls,
    )
    return result
