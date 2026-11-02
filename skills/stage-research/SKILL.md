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
   - mode `web` → find the fixture on the competition's or club's official site plus one more independent source;
     `resolution.method = "web"`, `fixture_id: null`, ≥ 2 sources (`BR-09`).
2. Fill `brief.match` (home = the team playing at home; kickoff in UTC; `local_timezone` = the user's, e.g. `Asia/Tehran`),
   `teams.H` = home colours, `teams.A` = away colours (distinct, `BR-02`), `focus_team: "both"`, `show_names: true`.

## Steps
1. `.venv/Scripts/tms stage begin research`
2. If an API key exists: `.venv/Scripts/tms research api` (≈ 12 cached calls; refuses beyond the project budget).
3. Launch three **match-researcher** subagents in parallel (scope `H`, `A`, `fixture`) with the brief and the list of
   facts the API did not supply (see `config/facts.yaml`; required facts must be covered). Merge their claims into one
   `projects/<slug>/artifacts/web_claims.json` (renumber ids W-001…, keep one `runs` entry per researcher).
4. `.venv/Scripts/tms validate web_claims` then `.venv/Scripts/tms research build` → `build/match_dossier.json`.
   Fix every MD error: missing required facts (research more), single-source key facts (find a second source or
   flag `single_source: true` honestly), stale news (re-fetch), conflicts (verify and drop the wrong claim).
5. **fact-checker** reviews `web_claims` + dossier (re-opens sources, checks quotes against values) →
   `.venv/Scripts/tms qa record research --agent fact-checker --review <file>`; fix refuted/corrected claims, rebuild.
6. **gate-verifier**, then `.venv/Scripts/tms stage submit research` → `completed`.
