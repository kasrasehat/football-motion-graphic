# Match Collector

To use the collector inside another project, follow the [embedded integration guide](docs/EMBEDDING.md). The [developer prompt](docs/IMPLEMENT-IN-MY-PROJECT.txt) is ready to paste into the receiving project's coding chat.

Collect football data from Soccerway, Ballhelper and Sofascore using **two opponents and a date**. Dates default to **UTC**. The project includes a Python library, CLI and local REST API with an interactive request form at `/docs`.

The output retains source-specific fields and raw responses instead of flattening away unfamiliar data. Categories cover match summary, statistics, lineups, incidents, players, head-to-head, standings, odds, related news and extra data. News includes article text, title, author, publication date and source URL when available. Soccerway's automatically generated previews are identified as such.

## Run on Windows

Python 3.11+ is required. Python 3.12 and the dependencies have already been installed in this workspace's `.venv`.

```powershell
# Only needed on a fresh checkout:
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m playwright install chromium

# Collect a match (edit the request file to choose opponents/date):
.\.venv\Scripts\python.exe -m match_collector collect --query examples/match.json

# Or use individual flags:
.\.venv\Scripts\python.exe -m match_collector collect --opponent-a Arsenal --opponent-b "Hull City" --alias-b Hull --date 2026-11-07

# Start the local API:
.\.venv\Scripts\python.exe -m match_collector serve
```

`requirements.lock.txt` records the versions used for verification. For a matching Python 3.12 environment, install it with `pip install -r requirements.lock.txt` before `pip install -e .`.

Open **http://127.0.0.1:8000/docs** after starting the server. `start.ps1` is an alternative launcher. The server binds to localhost. Use one server process; its background workers run two collections concurrently and queue up to 24 jobs. Authentication, shared distributed workers and public hosting are outside this local implementation.

On Linux/macOS, use `python3 -m venv .venv` and `.venv/bin/python` instead of the Windows executable path. Install Chromium with Playwright in that environment.

## API

```powershell
$body = Get-Content -Raw examples/match.json
$job = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/jobs -ContentType 'application/json' -Body $body
Invoke-RestMethod "http://127.0.0.1:8000/jobs/$($job.id)"
# After the job leaves queued/running:
Invoke-RestMethod "http://127.0.0.1:8000/jobs/$($job.id)/result"
```

`POST /jobs` returns HTTP 202 and a job ID. `GET /jobs/{id}` reports progress/status. `GET /jobs/{id}/result` returns the complete report (HTTP 409 while running). Requests are validated; dates must be ISO `YYYY-MM-DD`. SQLite stores job metadata. A restart marks unfinished jobs `interrupted`; submit a new job to retry. Set `MATCH_COLLECTOR_DATA` to relocate API storage.

## Output and meaning of statuses

Soccerway's `data.players` records with `acquisition: "player_statistics"` contain named players, teams, positions, starting status, ratings and all metric entries returned for that fixture. Look up metric IDs in `metric_definitions` and `metric_groups`. Roster members can have missing metrics or source-reported zeros. For fixtures without current player figures, the browser collector also checks each side's most recent listed completed fixture within the page budget. These figures appear separately under `data.recent_player_form`, with the earlier match, kickoff and source links.

Each run is saved under `data/runs/<run_id>/`:

```text
report.json          Query, candidates, match data, news, coverage and failures
manifest.json        Run summary
soccerway/raw/       Original responses, named by SHA-256
ballhelper/raw/
sofascore/raw/
```

Each record has its source URL; the evidence list records retrieval timestamps, HTTP status, content type, hash and raw-file path. Reports do not silently merge differing source values. Kickoff disagreements are listed under `conflicts`. All original source payloads, including fields the parser does not understand, remain in raw artifacts. Media URLs are retained; audio, image and video binaries are not downloaded.

`partial` means a verified match was found and some data was collected. It **does not mean that every possible field is available**. `unverified` retains a plausible source record without asserting its UTC date; `ambiguous` lists competing matches without selecting one. `blocked`, `error` and `not_found` are distinct per-source outcomes. `not_found` means not found within the discovery scope, not proof that a site has no such match. A CLI run with no collected/verified result exits with code 2; other completed reports exit with code 0. Check the JSON status and coverage in either case.

`coverage` distinguishes collected data, unavailable sections, blocked requests, undiscovered sections and disabled news. HTML tab snapshots are retained in `extra`; a tab title or an error message alone does not count as lineup/statistics data.

## Source behavior and current limits

Live checks were performed on 2026-11-06:

| Source | Implementation | Observed limitation |
|---|---|---|
| Soccerway | Homepage and published match sitemaps, embedded match state, preview, discovered match tabs, normal Chromium rendering and observed data responses | Sitemaps are not a full historical index. Some tabs are empty, fail, or require additional interaction. Match URLs are pinned with the event's `mid` to avoid silently switching fixtures. |
| Ballhelper | Current homepage/weekly fixtures, match-associated form/H2H rows, linked league tables/results/statistics, supplied historical result pages | Works over HTTP. HTTPS has a certificate hostname mismatch. Main fixture and result rows use month/day/year; inline H2H text uses day/month/year. The site does not declare its time zone in the inspected pages. |
| Sofascore | UTC schedule buckets, stable event IDs, summary, stats, lineups, incidents, shotmap, positions, H2H, odds, managers, highlights and season standings; linked news | Direct requests received HTTP 403 in this environment, including robots.txt. The adapter is fixture-tested; live match retrieval is unverified here. Its website endpoints are undocumented and may change. |

Ballhelper's dates are preserved as source wall-clock dates. Set `ballhelper_timezone` in the JSON request (for example, `Europe/Belgrade`) **only after establishing the site's actual time convention**. The system does not guess it. Even with this setting, historical rows without kickoff times cannot verify an exact UTC day and remain unverified.

An unrestricted promise to extract “all data” is not technically achievable: coverage varies by match, source availability and access, and news discovery is finite. This system collects discovered accessible content and explicitly reports the gaps. It does not solve access challenges, disable TLS validation, or bypass age/access gates. Sofascore also restricts automated reuse in its [terms](https://www.sofascore.com/terms-and-conditions); arrange appropriate access before production use. Review source rights before republishing full news articles.

## Improve discovery for a particular match

Use exact source URLs when a match is older than the current discovery window. URL hints never bypass opponent/date verification:

```json
{
  "opponent_a": "Arsenal",
  "opponent_b": "Hull City",
  "aliases_b": ["Hull"],
  "date": "2026-11-07",
  "timezone": "UTC",
  "seed_urls": {
    "soccerway": ["https://us.soccerway.com/game/arsenal-hA1Zm19f/hull-city-S66R0t75/?mid=Eyc1EfPH"]
  }
}
```

For Sofascore, a match URL containing `#id:<event_id>` is supported, as is the site's `/api/v1/event/<event_id>` URL. For Ballhelper, provide a league fixtures/results page. Cross-domain redirects and source URLs outside the supported source hosts are rejected.

Team aliases can be supplied as `aliases_a` / `aliases_b` (CLI `--alias-a` / `--alias-b`). Home/away order is discovered from the source. Women, reserve and youth qualifiers are preserved. Multiple close matches require a more specific request or exact URL; they are never chosen arbitrarily.

Defaults: 30 page attempts per source, 15 news items, a ±7-day news window, browser enabled. Increase `max_pages_per_source` (up to 300) for deeper tab/news collection. This counts top-level page/API attempts; a rendered page can make multiple additional data requests. Fetches are rate-limited per worker/host, successful requests are cached within a run, and retryable errors use bounded retries. Robots exclusions and reported crawl delays are observed; an unavailable policy is surfaced as an error.

News discovery follows relevant links and up to three linked news indexes. Linked Flashscore and Vrh News pages are supported where accessible. Both-team articles and one-team context are labelled separately; both-team mentions alone do not prove the article describes the exact fixture. Publication dates are filtered around the requested date; missing/unparseable dates are flagged, not invented. Unlinked publishers and exhaustive historical news search are not included.

## Team analysis in the download

In the Soccerway source, open `data.team_analysis`. The `prior_competition_results` entry contains the underlying games and each team's overall, home and away records before kickoff. Each split includes games played, W/D/L, recent form (newest first), goals for and against, both teams to score, double chance, all seven over/under lines from 0.5 to 6.5, and the nine half-time/full-time combinations. W/D/L is from that team's perspective. The HT/FT sample counts only games with known half-time scores. When the competition results page is truncated, the collector also checks both teams’ results pages and merges matches by event ID within the same competition stage. The export lists these source URLs. Older rounds can still be absent from all three pages.

With browser rendering enabled, `published_totals_at_collection_time` entries also carry Soccerway's ranks, over/under counts and recent results for each goal line. The collection timestamp matters when looking up an old fixture. When the match preview gives a forecast, `publisher_match_forecast` carries the published percentages and score prediction separately. Bookmaker quotes, when available, belong to the `odds` section.

## Development

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check match_collector tests
```

Tests use synthetic fixtures and mocked HTTP responses, so they do not depend on the live sites. Browser/live checks are separate. `collectors.py` owns source discovery and parsing, `transport.py` handles fetching and evidence, `browser.py` renders dynamic pages, `news.py` handles articles, and `service.py` combines independent source reports. Extend a source parser when its markup changes; raw snapshots make regressions reproducible.
