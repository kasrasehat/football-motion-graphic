"""Theme assembly for render_props (config/themes.yaml + brief team colours)."""
from __future__ import annotations

from functools import lru_cache

import yaml

from tms import paths


@lru_cache(maxsize=1)
def config() -> dict:
    return yaml.safe_load((paths.config_dir() / "themes.yaml").read_text(encoding="utf-8"))


def render_theme(brief: dict, name: str | None = None) -> dict:
    c = config()
    t = c["themes"][name or c["default"]]
    teams = {k: {"fill": v["fill"], "ring": v["ring"], "text": v["text"], "short": v["short"], "name": v["name"]}
             for k, v in brief["teams"].items()}
    return {"pitch": dict(t["pitch"]), "teams": teams, **t["ui"]}


def resolution(aspect: str, scale: float = 1.0) -> dict:
    r = dict(config()["resolutions"][aspect])
    r["width"], r["height"] = int(round(r["width"] * scale)), int(round(r["height"] * scale))
    return r


def palette(name: str) -> tuple[str, str, str]:
    return tuple(config()["palettes"][name])  # type: ignore[return-value]
