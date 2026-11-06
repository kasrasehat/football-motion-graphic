---
name: stage-research
description: Match-preview research - resolve the fixture during intake, pull API-Football data when a key exists, run parallel web research for tactics, xG, team news and predicted line-ups as sourced claims, merge everything into the match dossier and get it fact-checked. Use for intake of match previews and when tms next names the research stage.
---

# Stage: research → `artifacts/web_claims.json` + engine `build/match_dossier.json`

Authors: **match-researcher** (×3 in parallel: scope H, A, fixture). Reviewer: **fact-checker** (blocking). No human gate.
Read `skills/match-data-sources/SKILL.md` (and `skills/api-football/SKILL.md` when a key exists).

## Intake for match previews (inside the intake stage)
1. `.venv/Scripts/tms fixture resolve "<the user's fixture text>"`
   - mode `api` with exactly one candidate → use it (`resolution.method = "api"`, `fixture_id`, kickoff, venue).
   - several or none → ask the user which match they mean; never guess.
   - mode `web` (no key, API unavailable, or `api_status: "plan_restricted"`) → find the fixture on the competition's or club's official site plus one more independent source;
     `resolution.method = "web"`, `fixture_id: null`, ≥ 2 sources (`BR-09`).
2. Fill `brief.match` (home = the team playing at home; kickoff in UTC; `local_timezone` = the user's, e.g. `Asia/Tehran`),
   `teams.H` = home colours, `teams.A` = away colours (distinct, `BR-02`), `focus_team: "both"`, `show_names: true`.

## Steps
1. `.venv/Scripts/tms stage begin research`
2. If an API key exists: `.venv/Scripts/tms research api` (≈ 12 cached calls; refuses beyond the project budget).
3. `.venv/Scripts/tms research scrape` runs the vendored match collector for the brief's fixture (see "Match collector" below).
   Read its coverage and gaps. It writes `media/research/collector_claims.json`, which `research build` merges into the dossier.
4. Launch three **match-researcher** subagents in parallel (scope `H`, `A`, `fixture`) with the brief, the collector's gaps and the list of
   facts the API and collector did not supply (see `config/facts.yaml`; required facts must be covered). Merge their claims into one
   `projects/<slug>/artifacts/web_claims.json` (renumber ids W-001…, keep one `runs` entry per researcher).
5. `.venv/Scripts/tms validate web_claims` then `.venv/Scripts/tms research build` → `build/match_dossier.json`.
   Fix every MD error: missing required facts (research more), single-source key facts (find a second source or
   flag `single_source: true` honestly), stale news (re-fetch), conflicts (verify and drop the wrong claim).
6. **fact-checker** reviews `web_claims` + dossier (re-opens sources, checks quotes against values; collector claims are checked through
   their `field_path` in the saved report and a sample of their pages) →
   `.venv/Scripts/tms qa record research --agent fact-checker --review <file>`; fix refuted/corrected claims, rebuild.
7. **gate-verifier**, then `.venv/Scripts/tms stage submit research` → `completed`.

## Match collector (`vendor/match-collector`, run by `tms research scrape`)
- **When:** after the API pull and before the web researchers, so they only chase what is still missing. Close to kick-off, run it again
  for line-ups: downstream stages then go stale, as with any research refresh.
- **Options:** `--sources soccerway,ballhelper,sofascore` (default all three), `--no-browser` (plain HTTP; needs no Chromium, may miss rendered tabs
  and published totals), `--replay <report.json>` (a saved report for this fixture, with no network). Browser runs need
  `.venv/Scripts/python.exe -m playwright install chromium` once.
- **Output:** `media/research/collector/runs/<run_id>/` (report, manifest, raw evidence), `latest.json`, and `collector_claims.json` (claims and gaps).
- **What becomes a fact** (`engine/tms/research/scrape_map.py`): kick-off, competition, round, form, goal rates, `T.split.overall|home|away` (W/D/L, goals,
  BTTS, double chance, goal lines, HT/FT, each with its own sample), standings and head-to-head, only from a source with a date-verified match oriented
  like the brief, and only from before kick-off. No games means unknown; a real zero stays zero. Venue rates need 5 games. A table collected after
  kick-off is dropped.
- **Read the report directly, as leads, not facts:** line-ups (no positions, so they can't fill `T.predicted_xi`), player metrics, recent player form, news,
  odds and `publisher_match_forecast`. Publisher forecasts and bookmaker odds are not our model's input unless researched as claims. Honour
  generated-preview and unverified-date flags on news. A researcher who uses one opens the page and writes a normal sourced claim.
- **A block is an answer:** report it and go on. The collector has no way around one, and none should be added.
- **Terms:** see the source notes in `vendor/match-collector/VENDORED.md`. Soccerway's terms bar scraping and commercial use without consent, so it is the user's call per project.
