"""Run from a host project with match-collector installed. See docs/EMBEDDING.md."""

import argparse
import asyncio
from pathlib import Path

from match_collector.models import CollectionReport, MatchQuery
from match_collector.service import collect


def main():
    parser = argparse.ArgumentParser(description="Collect in-process or inspect a saved report")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--query", type=Path, help="MatchQuery JSON file. Contacts the selected websites.")
    mode.add_argument("--report", type=Path, help="Saved report.json. Reads only this local file.")
    parser.add_argument("--output", type=Path, default=Path("match-data"), help="Storage root for a new run")
    args = parser.parse_args()
    if args.report:
        report = CollectionReport.model_validate_json(args.report.read_bytes())
    else:
        query = MatchQuery.model_validate_json(args.query.read_bytes())
        report = asyncio.run(collect(query, output=args.output.resolve()))
        print(args.output.resolve() / "runs" / report.run_id / "report.json")

    print(f"{report.run_id}  {report.status}")
    for source in report.sources:
        categories = [name for name, rows in source.data.items() if rows]
        print(f"{source.source}  {source.status}  {', '.join(categories)}")
        for entry in source.data.get("team_analysis", []):
            if entry.get("relation") == "prior_competition_results" and source.match:
                for team in entry["value"]["teams"]:
                    sample = team["splits"]["overall"]
                    print(f"  {team['team']}  {sample['played']} prior games  W/D/L {sample['wdl']}")
        for warning in source.warnings:
            print(f"  {warning}")


if __name__ == "__main__":
    main()
