import argparse
import asyncio
import json
from pathlib import Path

from pydantic import ValidationError

from .models import MatchQuery
from .service import collect


def main():
    parser = argparse.ArgumentParser(description="Collect football match data and related news")
    sub = parser.add_subparsers(dest="command", required=True)
    scrape = sub.add_parser("collect", help="Collect a match and write a JSON report")
    scrape.add_argument("--opponent-a")
    scrape.add_argument("--opponent-b")
    scrape.add_argument("--date", help="YYYY-MM-DD in --timezone (UTC by default)")
    scrape.add_argument("--timezone", default="UTC")
    scrape.add_argument("--source", action="append", choices=["soccerway", "ballhelper", "sofascore"])
    scrape.add_argument("--alias-a", action="append", default=[])
    scrape.add_argument("--alias-b", action="append", default=[])
    scrape.add_argument(
        "--url", action="append", default=[], help="source=exact_match_or_league_url (repeatable)"
    )
    scrape.add_argument("--query", type=Path, help="JSON request file; replaces individual query flags")
    scrape.add_argument("--output", type=Path, default=Path("data"))
    scrape.add_argument("--no-browser", action="store_true")
    scrape.add_argument("--no-news", action="store_true")
    scrape.add_argument("--max-pages", type=int, default=30)
    scrape.add_argument("--news-days", type=int, default=7)
    scrape.add_argument(
        "--ballhelper-timezone", help="Only set after verifying Ballhelper's wall-clock timezone"
    )
    serve = sub.add_parser("serve", help="Start the local API and interactive documentation")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn

        uvicorn.run("match_collector.api:app", host="127.0.0.1", port=args.port)
        return
    try:
        if args.query:
            query = MatchQuery.model_validate_json(args.query.read_text(encoding="utf-8-sig"))
        else:
            seeds = {}
            for item in args.url:
                source, url = item.split("=", 1)
                seeds.setdefault(source, []).append(url)
            query = MatchQuery(
                opponent_a=args.opponent_a,
                opponent_b=args.opponent_b,
                date=args.date,
                timezone=args.timezone,
                sources=args.source or ["soccerway", "ballhelper", "sofascore"],
                aliases_a=args.alias_a,
                aliases_b=args.alias_b,
                seed_urls=seeds,
                browser=not args.no_browser,
                include_news=not args.no_news,
                max_pages_per_source=args.max_pages,
                news_days=args.news_days,
                ballhelper_timezone=args.ballhelper_timezone,
            )
    except (ValueError, ValidationError, OSError) as exc:
        parser.error(str(exc))
    report = asyncio.run(collect(query, args.output))
    path = (args.output / "runs" / report.run_id / "report.json").resolve()
    print(
        json.dumps(
            {
                "run_id": report.run_id,
                "status": report.status,
                "report": str(path),
                "sources": {
                    s.source: {
                        "status": s.status,
                        "candidates": len(s.candidates),
                        "collected": [k for k, v in s.data.items() if v],
                    }
                    for s in report.sources
                },
            },
            indent=2,
        )
    )
    if report.status == "no_verified_match":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
