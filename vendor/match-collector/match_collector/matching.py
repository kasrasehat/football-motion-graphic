import re
import unicodedata
from zoneinfo import ZoneInfo

from rapidfuzz.fuzz import ratio

from .models import Candidate, MatchQuery


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w]+", " ", value).split())


def team_score(a: str, b: str) -> float:
    a, b = normalize(a), normalize(b)

    def club_name(value):
        tokens = ["united" if word == "utd" else word for word in value.split()]
        return " ".join(word for word in tokens if word not in {"fc", "cf", "afc", "sc"})

    a, b = club_name(a), club_name(b)
    if not a or not b:
        return 0
    # A youth, reserve or women's side must not silently match the senior men's team.
    qualifiers = lambda s: set(re.findall(r"\b(?:u\d{2}|women|w|reserves?|ii|b|am)\b", s))
    if qualifiers(a) != qualifiers(b):
        return 0
    return ratio(a, b) / 100


def mentions(text: str, names: list[str]) -> bool:
    value = " " + normalize(text) + " "
    return any(" " + normalize(n) + " " in value for n in names if n.strip())


def rank_candidates(candidates: list[Candidate], query: MatchQuery) -> list[Candidate]:
    ranked = {}
    for c in candidates:
        a = [query.opponent_a, *query.aliases_a]
        b = [query.opponent_b, *query.aliases_b]
        sim = lambda names, team: max(team_score(n, team) for n in names)
        c.confidence = round(max(min(sim(a, c.home), sim(b, c.away)), min(sim(a, c.away), sim(b, c.home))), 4)
        if c.kickoff is not None and c.kickoff.tzinfo is not None:
            c.date_verified = c.kickoff.astimezone(ZoneInfo(query.timezone)).date() == query.date
            if not c.date_verified:
                continue
        elif c.source_date is not None and c.source_date != query.date:
            continue
        if c.confidence >= 0.70:
            old = ranked.get(c.source_id)
            if old is None or c.confidence > old.confidence:
                ranked[c.source_id] = c
    return sorted(ranked.values(), key=lambda c: (c.date_verified, c.confidence), reverse=True)


def choose(candidates: list[Candidate]) -> tuple[Candidate | None, str]:
    if not candidates:
        return None, "not_found"
    verified = [c for c in candidates if c.date_verified and c.confidence >= 0.88]
    if not verified:
        return None, "unverified"
    if len(verified) > 1 and verified[0].confidence - verified[1].confidence < 0.08:
        return None, "ambiguous"
    return verified[0], "partial"
