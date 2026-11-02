---
name: api-football
description: How this project uses the API-Football v3 service (fixtures, standings, team statistics, form, head-to-head, injuries, line-ups, odds) through tms commands with caching and a per-project call budget, and how to fall back to web-only research. Use when resolving fixtures or pulling structured match data.
---

# API-Football (api-sports.io v3)

Key: `API_FOOTBALL_KEY` in `.env` (empty → research is web-only; everything still works). Never call the API with
curl — use the commands below (cached, budgeted, logged). Optional proxy: `TMS_HTTPS_PROXY`.

| command | calls | gives |
|---|---|---|
| `.venv/Scripts/tms fixture resolve "<home> vs <away> <when>"` | ~3 | candidate fixtures (id, kickoff, venue, competition) |
| `.venv/Scripts/tms research api` | ~12 | fixture, last-5 form ×2, season stats ×2, managers ×2, standings, H2H, injuries, line-ups (≈1 h before KO), odds |

Every claim it produces carries `{"kind":"api","endpoint":"/teams/statistics","field_path":"response.goals.for.average.total"}`
as its source and is trusted as authoritative for numbers (it wins conflicts with web claims).

## Budget and caching
- Free plan: 100 requests/day. The project cap is `brief.budget.api_calls_max` (and `TMS_MAX_API_FOOTBALL_CALLS_PER_PROJECT`);
  usage is tracked in `projects/<slug>/media/research/api_usage.json`.
- Responses are cached (fixtures/injuries 30 min, line-ups 10 min, stats 12 h, teams 30 days): re-running is free.
- Exit 2 = budget or daily quota reached → continue web-only for the rest, and tell the user.

## Not covered by the API (always web research)
xG for/against, tactical tendencies (`T.tactics.*`), predicted XIs before line-ups are published, stakes/news context.
