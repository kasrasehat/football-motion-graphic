"""Standalone command line: `python -m match_data_collector collect --home X --away Y ...` prints the result as JSON."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from match_data_collector.adapters.agent_facts import AgentFactsAdapter
from match_data_collector.adapters.ballhelper import BallhelperAdapter
from match_data_collector.collector import Collector
from match_data_collector.contract import MatchQuery
from match_data_collector.fetch import PoliteFetcher
from match_data_collector.policy import POLICIES


def add_query_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--home", required=True)
    p.add_argument("--away", required=True)
    p.add_argument("--date", help="YYYY-MM-DD")
    p.add_argument("--competition")
    p.add_argument("--home-league", help="the home team's domestic league, e.g. 'Premier League'")
    p.add_argument("--away-league")
    p.add_argument("--agent-facts", help="JSON file of facts a research agent gathered")
    p.add_argument("--out", help="write the JSON here instead of stdout")


def query_from(a: argparse.Namespace, **ids) -> MatchQuery:
    return MatchQuery(home=a.home, away=a.away, date=a.date, competition=a.competition, home_league=a.home_league,
                      away_league=a.away_league, ids={k: str(v) for k, v in ids.items() if v})


def web_adapters(a: argparse.Namespace, cache_dir: Path | None) -> list:
    adapters = [BallhelperAdapter(PoliteFetcher(cache_dir=cache_dir))]
    if a.agent_facts:
        adapters.append(AgentFactsAdapter(a.agent_facts))
    return adapters


def emit(doc: dict, out: str | None) -> None:
    text = json.dumps(doc, indent=2, ensure_ascii=False)
    if out:
        Path(out).write_text(text + "\n", encoding="utf-8")
    else:
        sys.stdout.buffer.write((text + "\n").encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="match_data_collector")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="collect sourced facts and explicit gaps for one match")
    add_query_args(c)
    c.add_argument("--cache-dir")
    sub.add_parser("sources", help="list each source's policy")
    a = ap.parse_args(argv)
    if a.cmd == "sources":
        emit({n: asdict(p) for n, p in POLICIES.items()}, None)
        return 0
    res = Collector(web_adapters(a, Path(a.cache_dir) if a.cache_dir else None)).collect(query_from(a))
    emit(res.to_dict(), a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
