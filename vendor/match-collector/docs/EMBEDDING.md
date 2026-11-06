# Match Collector developer handoff

Use the existing Python package inside the receiving project's backend or worker. Your application creates a `MatchQuery`, awaits `collect()`, and receives a typed `CollectionReport`. Your application owns the user interface, scheduling and storage policy. Live collection makes outbound requests to the selected football websites. Reading a saved report works entirely offline.

Source on the development machine: `E:\codex_files\web scrapper`. Package: `match_collector`. Distribution: `match-collector` 0.1.0. Report schema: `1.0`. Python 3.11+ is required. The reference environment is Windows with Python 3.12. No running collector server, local port or Docker installation is needed.

## 1. Put the collector inside your project

From the **receiving repository**, extract the supplied handoff ZIP into `vendor/match-collector/`. At the end, `vendor/match-collector/pyproject.toml` and `vendor/match-collector/match_collector/service.py` should exist. Alternatively, copy `pyproject.toml` and the entire `match_collector/` package from the source path into that same folder. Include the tests, examples and guide for development. Leave behind the source machine's virtual environment, caches, job database, downloaded reports and raw evidence.

Activate the receiving project's Python environment. Install the local package and run the import check:

```sh
python -m pip install ./vendor/match-collector
python -c "from match_collector.service import collect; from match_collector.models import MatchQuery, CollectionReport; print('ready')"
```

Record the local dependency or install step in the host's package manager, CI and deployment build. Keep the vendor directory under version control. If editing the vendored package in development, use `python -m pip install -e ./vendor/match-collector`. The receiving project's normal dependency resolver must accept the ranges in the vendored `pyproject.toml`. The Windows reference lock includes test tools and documents the verified environment.

Browser rendering is enabled by default. To enable it on the worker, install Chromium once using that same environment's `python -m playwright install chromium`. On Linux, provision Playwright's Chromium OS dependencies as part of the build. For a smaller installation, set `browser=False` on your queries and omit the Chromium binary. Basic HTTP collection still runs. Rendered tabs and published team totals may then be absent. The Playwright Python package is a declared dependency in either mode.

## 2. Call from host code

```python
from datetime import date
from pathlib import Path

from match_collector.models import CollectionReport, MatchQuery
from match_collector.service import collect


async def collect_fixture(home: str, away: str, match_day: date, storage: Path) -> CollectionReport:
    query = MatchQuery(opponent_a=home, opponent_b=away, date=match_day, timezone="UTC")
    return await collect(query, output=storage.resolve())
```

Pass an absolute, writable, persistent storage directory from host configuration. An async worker can await this directly. A synchronous Python job can use `asyncio.run(collect_fixture(...))` once at its outer boundary. Schedule collection outside a time-sensitive UI request. The standalone API's queue limit and SQLite job tracking apply only to that API. When embedding, use your own job runner, concurrency limit, timeout, cancellation and error reporting. Start with one live match at a time on a memory-constrained host. The service already collects the selected sources concurrently within a match.

For a non-Python backend, keep the same vendored Python dependency and invoke its installed CLI as a local child process from a worker. Pass arguments as an array, for example `[python_executable, "-m", "match_collector", "collect", "--query", query_file, "--output", storage_dir]`. Give each invocation its own request file. Read the JSON summary from stdout and load the saved report at its `report` path. Exit code 2 can mean a saved `no_verified_match` report or invalid arguments without a report. Inspect stdout and stderr. This path also runs entirely within the host deployment.

### Try it offline first

```sh
python vendor/match-collector/examples/embed.py --report "/absolute/path/to/report.json"
```

On the source machine a verified completed-match report is available at `E:\codex_files\web scrapper\data\runs\d2fe53f7d6f44443a6b3a6a4f11269a2\report.json`. To collect live when ready, pass `--query vendor/match-collector/examples/match.json --output ./match-data` in place of `--report`. Change the example opponents and date as needed. The example prints coverage and the game count behind each team's record.

## 3. Input contract

| Field | Meaning and default |
|---|---|
| `opponent_a`, `opponent_b` | Required. Distinct names of 2–120 characters each. The source establishes home/away order. |
| `date`, `timezone` | Required match day as a Python date or ISO YYYY-MM-DD. Timezone defaults to UTC and accepts IANA names. |
| `aliases_a`, `aliases_b` | Optional alternatives for each team, up to 20 each. Preserve youth, reserve and women's team qualifiers. |
| `sources` | One or more of `soccerway`, `ballhelper`, `sofascore`. Defaults to all three. |
| `seed_urls` | Source name mapped to a list of URLs. Up to 30 hints in total. Useful for older games. Prefer a Soccerway match URL with its `mid`. Date and opponent verification still apply. |
| `browser` | Defaults to true. Enables the optional Chromium renderer. |
| `max_pages_per_source` | Default 30, range 2–300. Browser pages can issue multiple data requests. |
| `include_news`, `news_days`, `max_news` | Defaults to true, ±7 days, and 15 items. Allowed windows are 0–90 days and 0–100 items. Zero items disables news collection. |
| `ballhelper_timezone` | Defaults to unset. Set only if you have established the source's time convention. The user's UTC preference alone does not establish it. |

Unknown input fields fail Pydantic validation. Treat validation failures as input errors. Keep storage paths and run identifiers under host control. Let the collector generate a fresh run ID per attempt. Reusing an ID makes independent attempts write to the same directory.

## 4. Read the returned report

`report.sources` is a **list**. Select a source by `source.source`; each source has its own match, candidates, data, coverage, evidence and warnings. The report also carries the original query, run ID, start/finish times, scope and any kickoff conflicts. Serialize using `report.model_dump(mode="json")` or `report.model_dump_json()`. Restore with `CollectionReport.model_validate_json(...)`. Preserve unfamiliar provider fields. The bundled JSON Schema describes the report envelope; category payloads intentionally allow source-specific fields.

| Layer | Values and host behavior |
|---|---|
| Returned report | `partial` means at least one source selected a verified match. `unverified` means data exists without a verified match. `no_verified_match` means the run produced no verified match or retained category records. All three are completed outcomes. |
| Source | `partial`, `unverified`, `ambiguous`, `not_found`, `blocked`, `error`. Use the selected `match` for verified fixture data. Show candidate context separately if needed. A blocked source can coexist with usable data from another. |
| Category coverage | `collected`, `unavailable`, `not_discovered`, `blocked`, `disabled`. Check the records, coverage detail and warnings before displaying a metric. Empty arrays and missing values mean unknown or unavailable. Source-reported zeros are valid. |

Each `source.data[category]` is a list of records containing `source_url`, `value` and optional metadata such as `relation`, `acquisition` or `match_date_verified`. Retain those labels when projecting data into your database.

| Category | What a consumer can use |
|---|---|
| `summary` | Provider match header and raw fields. Prefer the selected match for source ID, home, away and verified kickoff. |
| `statistics`, `incidents`, `lineups` | Available source statistics, commentary/events and players on the pitch. Pre-match tabs may contain team averages or projected lineups. Preserve the source labels. |
| `players` | For Soccerway, select `acquisition == "player_statistics"` for the requested fixture's roster, ratings and metric entries. Use metric definitions for labels and retain team, side, player ID and raw values. Team-scorer context has a different relation. |
| `recent_player_form` | Earlier fixture snapshots carrying their own event ID, date and teams. Useful for pre-match context. |
| `team_analysis` | See the three distinct records below. |
| `h2h`, `standings`, `odds` | Meeting history, team/competition tables and available market information. Inspect the scope, source and collection time. |
| `news` | Article text, attribution, publication date and canonical link when available. Distinguish team context, both-team mentions and match previews. Honor generated-preview and unverified-date flags. |
| `extra` | HTML snapshots, raw structured responses and other unclassified context. Keep for evidence and future parsing. |

**Soccerway team analysis**

1. `prior_competition_results` contains the eligible regulation-time games before the selected kickoff and a `teams` list. Each team's `splits` contains `overall`, `home` and `away`. Read `played`, `wdl`, `form_newest_first`, goals for/against, points, average goals, `btts`, `double_chance`, `goal_lines` and `ht_ft`. W/D/L is relative to that team, including for the away side. Double-chance counts overlap. Use `ht_ft_sample` for HT/FT rates and `played` for full-time rates. An empty sample gives an unknown rate. Seven goal lines range from 0.5 to 6.5. Source event IDs and results URLs make the counts traceable.
2. `published_totals_at_collection_time` contains Soccerway's tables at fetch time, including over/under, rank, totals and recent results. Use the `as_of` timestamp. For historical prediction or backtesting these tables can include later matches.
3. `publisher_match_forecast` contains forecasts actually published in the match preview. Keep these separate from historical frequencies, bookmaker prices and the host's own predictions.

## 5. Persist, retry and verify

Under the chosen storage root, each `runs/<run_id>/` holds `report.json`, `manifest.json`, and per-source `raw/` files named by content hash. Evidence includes timestamps, URL, HTTP status, hash, path and errors where available. Absolute artifact paths refer to the collecting machine. If relocating evidence, use the run, source and hash to find the matching raw file under the new root. Treat raw HTML and article content as external data when rendering it.

Store a host job ID separately from the collector run ID. Before publishing a completed result, await the function and persist the returned status, coverage and report location. Handle exceptions from invalid input, storage failures and cancellation in the host. A cancelled run can leave raw files without a completed report. Where retries are needed, give the retry a new run ID and associate it with the same host job. Set disk retention for reports and raw bodies according to your project's requirements.

**Source limits observed in the November 2026 checks.** Soccerway can require an exact URL for older matches, and available history varies by competition and stage. Match-specific player stats may arrive after kickoff. Ballhelper returned useful league data but did not expose a verified timezone. Sofascore returned HTTP 403 from this environment. Keep its website collector enabled if requested and surface its status. The verification report included in the handoff records three live fixtures and the fields compared.

**Acceptance tests for the receiving project**

- Exercise its real match-analysis entry point using an injected collector or the source package's mocked HTTP transport. Set `browser=False` in offline transport tests so Chromium cannot make live requests. Keep production rate limiting enabled.
- Check a successful match, a wrong match date, a blocked source alongside a verified result, and an unavailable player metric. Assert the host's output retains coverage and provenance.
- Read a saved report with networking disabled. Check historical player stats keep their earlier event ID and that a zero-game HT/FT sample produces an unknown rate.
- Run `python -m pip install "./vendor/match-collector[dev]"` in a test environment, then `python -m pytest -q vendor/match-collector/tests`. Add the host-specific integration tests to the receiving project's suite.

## Source map

| File inside the vendored package | Integration relevance |
|---|---|
| `match_collector/service.py` | Async entry point, per-source isolation, report assembly and disk output. |
| `match_collector/models.py` | Query, returned models, validation, coverage and evidence. |
| `match_collector/matching.py`, `collectors.py` | Fixture selection, source adapters and discovery. |
| `match_collector/team_analysis.py`, `player_stats.py`, `news.py` | Analytical records, player metrics and news attribution. |
| `match_collector/transport.py`, `browser.py`, `extract.py` | Source access rules, raw evidence, rendering and parsing. |
| `tests/test_integration.py` | Reusable offline fixtures and independent source failures. |
| `examples/embed.py`, `examples/match.json` | Executable example and input. |
| `docs/report-schema.json`, `docs/query-schema.json` | Generated JSON Schemas for persisted reports and input validation. |
