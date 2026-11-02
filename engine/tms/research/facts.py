"""Fact-key registry (config/facts.yaml): spec lookup, value typing, agreement between claims."""
from __future__ import annotations

import re
from functools import lru_cache
from urllib.parse import urlparse

import yaml

from tms import paths


@lru_cache(maxsize=1)
def config() -> dict:
    return yaml.safe_load((paths.config_dir() / "facts.yaml").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def sources() -> dict:
    return yaml.safe_load((paths.config_dir() / "sources.yaml").read_text(encoding="utf-8"))


def spec(key: str) -> dict | None:
    facts = config()["facts"]
    if key in facts:
        return facts[key]
    m = re.match(r"^([HA])\.(.+)$", key)
    if not m:
        return None
    rest = m.group(2)
    if f"T.{rest}" in facts:
        return facts[f"T.{rest}"]
    for k, v in facts.items():
        if v.get("prefix") and k.startswith("T.") and rest.startswith(k[2:] + "."):
            return v
    return None


def required_keys() -> list[tuple[str, str]]:
    """(concrete key, level) for every required fact; prefix facts yield 'H.tactics.*' style patterns."""
    out = []
    for k, v in config()["facts"].items():
        if v.get("required", "no") == "no":
            continue
        for team in (("H", "A") if k.startswith("T.") else (None,)):
            key = k if team is None else f"{team}.{k[2:]}"
            out.append((key + (".*" if v.get("prefix") else ""), v["required"]))
    return out


def type_problem(key: str, value) -> str | None:
    sp = spec(key)
    if sp is None:
        return f"unknown fact key {key!r} (see config/facts.yaml)"
    t = sp["type"]
    if t == "number" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
        return f"{key} must be a number"
    if t == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
        return f"{key} must be an integer"
    if t in ("number", "integer") and "range" in sp and not sp["range"][0] <= value <= sp["range"][1]:
        return f"{key}={value} outside plausible range {sp['range']}"
    if t == "string" and not isinstance(value, str):
        return f"{key} must be a string"
    if t == "string" and sp.get("pattern") and not re.match(sp["pattern"], value):
        return f"{key}={value!r} does not match {sp['pattern']}"
    if t == "form" and (not isinstance(value, list) or not value or any(v not in ("W", "D", "L") for v in value)):
        return f"{key} must be a list of W/D/L"
    if t == "xi":
        if not isinstance(value, list) or len(value) != 11:
            return f"{key} must list exactly 11 players"
        if sum(1 for p in value if isinstance(p, dict) and p.get("position") == "G") != 1:
            return f"{key} must have exactly one goalkeeper (position G)"
    if t == "absences" and (not isinstance(value, list) or any(not isinstance(p, dict) or "player" not in p for p in value)):
        return f"{key} must be a list of {{player, reason}}"
    if t == "results" and (not isinstance(value, list) or any(not isinstance(r, dict) or "score" not in r for r in value)):
        return f"{key} must be a list of {{date, home, away, score}}"
    return None


def agree(key: str, a, b) -> bool:
    sp = spec(key) or {}
    t = sp.get("type")
    if t in ("number", "integer"):
        return abs(float(a) - float(b)) <= max(0.06, 0.03 * max(abs(float(a)), abs(float(b))))
    if t == "string":
        return str(a).strip().lower() == str(b).strip().lower()
    if t == "xi":
        na = {str(p.get("name", "")).lower() for p in a}
        nb = {str(p.get("name", "")).lower() for p in b}
        return len(na & nb) >= 9
    if t == "absences":
        return {str(p["player"]).lower() for p in a} == {str(p["player"]).lower() for p in b}
    return a == b


def domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def tier_of(url: str) -> int:
    d = domain(url)
    s = sources()
    for t, name in ((1, "tier1"), (2, "tier2")):
        if any(d == x or d.endswith("." + x) for x in s[name]):
            return t
    return 3


def blocked(url: str) -> bool:
    d = domain(url)
    return any(d == x or d.endswith("." + x) for x in sources()["blocked"])
