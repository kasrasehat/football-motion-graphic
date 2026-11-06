"""`tms fixture resolve`, `tms research api|build|status` — match research commands."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from tms import envfile, jsonio
from tms import validate as V
from tms.commands.common import add_project_arg, handled
from tms.research import api_football as AF
from tms.research.dossier import merge, now_iso, parse_query
from tms.state import machine, project as P


WEB_FALLBACK = ("Resolve the fixture by web search (official competition/club site + one more independent source); fill "
                "brief.match with resolution.method='web', fixture_id null and >= 2 sources.")


def _client(pr=None) -> AF.Client:
    if pr is None:
        return AF.Client()
    brief = pr.load_artifact("brief") or {}
    cap = min(int(envfile.get("TMS_MAX_API_FOOTBALL_CALLS_PER_PROJECT") or 40),
              (brief.get("budget") or {}).get("api_calls_max", 40))
    return AF.Client(max_calls=cap, usage_file=pr.dir / "media" / "research" / "api_usage.json")


@handled
def cmd_resolve(a):
    try:
        q = parse_query(a.query, datetime.now())
    except ValueError as e:
        raise P.ProjectError(str(e))
    out = {"query": a.query, **q, "mode": "api", "candidates": []}
    c = _client()
    if not c.available:
        out["mode"] = "web"
        out["instructions"] = ("No API_FOOTBALL_KEY: resolve the fixture by web search (official competition/club site + one "
                               "more independent source); fill brief.match with resolution.method='web' and >= 2 sources.")
    else:
        try:
            out["candidates"] = AF.resolve(c, q["home"], q["away"], q["date_from"], q["date_to"])
        except AF.PlanRestricted as e:
            out["mode"] = "web"
            out["api_status"] = "plan_restricted"
            out["api_message"] = str(e)
            out["instructions"] = WEB_FALLBACK
        except AF.ApiError as e:
            out["mode"] = "web"
            out["instructions"] = f"API unavailable ({e}); resolve via web search with >= 2 sources."
    print(json.dumps(out, indent=2, ensure_ascii=False))
    if out.get("api_status") == "plan_restricted":
        print(f"Your API-Football plan cannot access this fixture: {out['api_message']}")
        print("This is a limit of the plan, not an error in tms. Resolve the fixture by web search instead.")
    if out["mode"] == "api" and len(out["candidates"]) != 1:
        print(f"{len(out['candidates'])} candidates — ask the user which fixture they mean" if out["candidates"]
              else "no matching fixture in that window — check spelling/date with the user")
        return 1
    return 0


@handled
def cmd_api(a):
    pr = P.load(a.project)
    machine.require_active(pr, "research")
    brief = pr.load_artifact("brief")
    fid = brief["match"]["fixture_id"]
    c = _client(pr)
    if not c.available:
        raise P.ProjectError("no API_FOOTBALL_KEY — web-only research: skip this command")
    if fid is None:
        if brief["match"]["resolution"]["method"] == "web":
            print("Fixture was resolved by web search, so there is no API fixture to pull. Nothing to do here: "
                  "continue with web research; the dossier builds without API claims.")
            return 0
        raise P.ProjectError("brief.match.fixture_id is empty — resolve the fixture via the API first")
    try:
        claims, raw = AF.pull(c, int(fid), now_iso())
    except AF.QuotaExceeded as e:
        raise P.GateViolation(str(e))
    except AF.PlanRestricted as e:
        print(f"Your API-Football plan cannot access fixture {fid}: {e}")
        print("This is a limit of the plan, not an error in tms. No API claims were written: continue with web research; "
              "the dossier builds without them.")
        return 0
    except AF.ApiError as e:
        raise P.ProjectError(str(e))
    rdir = pr.dir / "media" / "research"
    for k, v in raw.items():
        jsonio.write_json(rdir / "api_raw" / f"{k}.json", v, compact=True)
    jsonio.write_json(rdir / "api_claims.json", {"claims": claims, "pulled_at": now_iso()})
    for part, why in raw.get("_plan_refused", {}).items():
        print(f"  plan refused {part}: {why}")
    print(f"API-Football: {len(claims)} claims from {c.calls} new calls (project total {c._used()}) -> media/research/api_claims.json")


@handled
def cmd_inspect(a):
    """Pull one fixture's bundle without a project, to check the parsing against live answers or record them for tests."""
    c = _client()
    if not c.available:
        raise P.ProjectError("no API_FOOTBALL_KEY — nothing to inspect")
    try:
        claims, raw = AF.pull(c, a.fixture_id, now_iso())
    except AF.QuotaExceeded as e:
        raise P.GateViolation(str(e))
    except AF.ApiError as e:
        raise P.ProjectError(str(e))
    for k, v in raw.items():
        if k != "_plan_refused":
            print(f"  {k}: results={v.get('results')}")
        if a.out:
            jsonio.write_json(Path(a.out) / f"{k}.json", v)
    for part, why in raw.get("_plan_refused", {}).items():
        print(f"  plan refused {part}: {why}")
    print(f"{len(claims)} claims from {c.calls} new calls: {', '.join(sorted(x['fact_key'] for x in claims))}")


@handled
def cmd_collect(a):
    from match_data_collector.__main__ import emit, query_from, web_adapters
    from match_data_collector.collector import Collector
    from tms import paths
    from tms.research.collect import ApiFootballAdapter
    adapters = [ApiFootballAdapter(_client()), *web_adapters(a, paths.scratch_dir() / "cache" / "collector")]
    emit(Collector(adapters).collect(query_from(a, api_football_fixture=a.fixture_id)).to_dict(), a.out)
    return 0


@handled
def cmd_scrape(a):
    from tms.research import scrape
    from tms.research.scrape_map import map_report
    pr = P.load(a.project)
    machine.require_active(pr, "research")
    sources = [s.strip() for s in a.sources.split(",") if s.strip()]
    if a.replay:
        scrape.replay(pr, Path(a.replay))
    else:
        scrape.collect(pr, sources, browser=not a.no_browser)
    _, report = scrape.load_latest(pr)
    print("\n".join(scrape.coverage_lines(report)))
    mapped = map_report(report, pr.load_artifact("brief"))
    jsonio.write_json(pr.dir / "media" / "research" / "collector_claims.json", mapped)
    print(f"mapped {len(mapped['claims'])} claims for the dossier; {len(mapped['gaps'])} gaps for the researchers:")
    print("\n".join(f"  gap: {g['source']}: {g['need']}: {g['why']}" for g in mapped["gaps"]))
    machine.log_decision(pr, "data", "agent", f"Collector run {report.run_id} ({'replayed' if a.replay else 'live'}, sources "
                         f"{', '.join(report.query.sources)}): {report.status}.", "research")
    return 0


def build(pr) -> list:
    machine.require_active(pr, "research")
    brief = pr.load_artifact("brief")
    api_file = pr.dir / "media" / "research" / "api_claims.json"
    api_claims = jsonio.read_json(api_file)["claims"] if api_file.is_file() else []
    usage = pr.dir / "media" / "research" / "api_usage.json"
    calls = jsonio.read_json(usage)["calls"] if usage.is_file() else 0
    web = pr.load_artifact("web_claims")
    inputs = {"brief": jsonio.sha256_file(pr.artifact_path("brief"))}
    if web is not None:
        inputs["web_claims"] = jsonio.sha256_file(pr.artifact_path("web_claims"))
    if api_file.is_file():
        inputs["api_claims"] = jsonio.sha256_file(api_file)
    collector_file = pr.dir / "media" / "research" / "collector_claims.json"
    collector_claims = jsonio.read_json(collector_file)["claims"] if collector_file.is_file() else []
    if collector_file.is_file():
        inputs["collector_claims"] = jsonio.sha256_file(collector_file)
    doc = merge(pr.id, brief, api_claims, web, now_iso(), inputs, calls, collector_claims)
    jsonio.write_json(pr.artifact_path("match_dossier"), doc)
    return V.validate_file(pr.dir, "match_dossier", pr.mode)


@handled
def cmd_build(a):
    pr = P.load(a.project)
    findings = build(pr)
    doc = pr.load_artifact("match_dossier")
    for f in findings:
        print(f"  {f.severity.upper():7s} [{f.rule}] {f.location + ': ' if f.location else ''}{f.message}")
    print(f"dossier: {len(doc['claims'])} claims, {len(doc['facts'])} facts, {len(doc['conflicts'])} conflicts, mode {doc['data_mode']}")
    errs = V.errors_only(findings)
    print(f"match_dossier: {len(errs)} error(s), {len(findings) - len(errs)} warning(s)")
    return 1 if errs else 0


def register(sub) -> None:
    p = sub.add_parser("fixture", help="fixture resolution for match previews")
    fsub = p.add_subparsers(dest="fixture_action", required=True)
    r = fsub.add_parser("resolve", help="'<home> vs <away> [tonight|tomorrow|YYYY-MM-DD]' -> candidate fixtures (API) or web instructions")
    r.add_argument("query")
    r.set_defaults(func=cmd_resolve)
    i = fsub.add_parser("inspect", help="development aid: pull one fixture's bundle without a project (cached, uses the daily quota)")
    i.add_argument("fixture_id", type=int)
    i.add_argument("--out", help="write the raw responses to this directory")
    i.set_defaults(func=cmd_inspect)
    p = sub.add_parser("research", help="match research: API pull and dossier build")
    rsub = p.add_subparsers(dest="research_action", required=True)
    x = rsub.add_parser("api", help="pull the standard API-Football bundle for brief.match.fixture_id (cached, budgeted)")
    add_project_arg(x)
    x.set_defaults(func=cmd_api)
    from match_data_collector.__main__ import add_query_args
    k = rsub.add_parser("collect", help="sourced facts and explicit gaps for one match from every permitted source (no project needed)")
    add_query_args(k)
    k.add_argument("--fixture-id", type=int, help="API-Football fixture id, if known")
    k.set_defaults(func=cmd_collect)
    s = rsub.add_parser("scrape", help="run the vendored match collector for the brief's fixture into media/research/collector (or --replay a saved report)")
    add_project_arg(s)
    s.add_argument("--sources", default="soccerway,ballhelper,sofascore", help="comma-separated: soccerway, ballhelper, sofascore")
    s.add_argument("--no-browser", action="store_true", help="plain HTTP only; rendered tabs and published totals may be absent")
    s.add_argument("--replay", metavar="REPORT", help="use a saved report.json for this fixture, with no network")
    s.set_defaults(func=cmd_scrape)
    b = rsub.add_parser("build", help="merge API claims + artifacts/web_claims.json -> build/match_dossier.json, then MD validation")
    add_project_arg(b)
    b.set_defaults(func=cmd_build)
