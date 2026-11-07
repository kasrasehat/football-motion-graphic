"""Theme assembly for render_props (config/themes.yaml + brief team colours)."""
from __future__ import annotations

import base64
import re
import xml.etree.ElementTree as ET

from functools import lru_cache
from pathlib import Path, PureWindowsPath

import yaml

from tms import paths


@lru_cache(maxsize=1)
def config() -> dict:
    return yaml.safe_load((paths.config_dir() / "themes.yaml").read_text(encoding="utf-8"))


def render_theme(brief: dict, name: str | None = None, project_dir: Path | None = None) -> dict:
    """The props theme. Crests go in as data URIs, and only with show_crests on, so props stay self-contained."""
    c = config()
    t = c["themes"][name or c["default"]]
    teams = {k: {"fill": v["fill"], "ring": v["ring"], "text": v["text"], "short": v["short"], "name": v["name"]}
             for k, v in brief["teams"].items()}
    if brief.get("show_crests"):
        if project_dir is None:
            raise ValueError("show_crests is on, but render_theme was not given the project folder")
        for k, v in brief["teams"].items():
            teams[k]["crest"] = crest_data_uri(project_dir, v.get("crest"))
    return {"pitch": dict(t["pitch"]), "teams": teams, **t["ui"]}


CREST_MAX_BYTES = 500_000
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_SVG_ACTIVE_TAGS = {"script", "foreignobject", "animate", "animatetransform", "animatemotion", "animatecolor", "set"}
_SVG_ACTIVE_CSS = re.compile(r"@keyframes|@import|\banimation\b|\btransition\b", re.I)
_SVG_EXTERNAL_URL = re.compile(r"url\(\s*['\"]?\s*(?!#|data:)", re.I)


def _png_problem(raw: bytes) -> str | None:
    """A browser plays an animated PNG on its own clock, which would break byte-identical frames."""
    if not raw.startswith(PNG_SIGNATURE):
        return "is not a PNG"
    at, first = len(PNG_SIGNATURE), None
    while at + 8 <= len(raw):
        size, kind = int.from_bytes(raw[at:at + 4], "big"), raw[at + 4:at + 8]
        first = first or kind
        if kind == b"acTL":
            return "is an animated PNG"
        if kind == b"IDAT":
            return None if first == b"IHDR" else "is not a PNG"
        at += 12 + size
    return "is not a PNG"


def _svg_problem(raw: bytes) -> str | None:
    """An SVG must draw from its own bytes alone: nothing fetched, nothing that moves or runs by itself."""
    if re.search(rb"<!(DOCTYPE|ENTITY)", raw, re.I):
        return "is an SVG with a DOCTYPE or entities"
    try:
        root = ET.fromstring(raw)
    except (ET.ParseError, ValueError):
        return "is not an SVG"
    if not isinstance(root.tag, str) or root.tag.rpartition("}")[2].lower() != "svg":
        return "is not an SVG"
    for el in root.iter():
        tag = el.tag.rpartition("}")[2].lower() if isinstance(el.tag, str) else ""
        if tag in _SVG_ACTIVE_TAGS:
            return f"is an SVG with a <{tag}> element"
        sheet = el.text or "" if tag == "style" else ""
        if _SVG_EXTERNAL_URL.search(sheet):
            return "is an SVG that links to something outside itself"
        if any(_SVG_ACTIVE_CSS.search(c) for c in (sheet, el.attrib.get("style", ""))):
            return "is an SVG with imported or animated CSS"
        for attr, value in el.attrib.items():
            link = attr.rpartition("}")[2].lower() in ("href", "src") and not value.strip().startswith(("#", "data:"))
            if link or _SVG_EXTERNAL_URL.search(value):
                return "is an SVG that links to something outside itself"
    return None


def crest_data_uri(project_dir: Path, rel: str | None) -> str:
    """The crest at `rel` (relative to the project folder) as a data URI; ValueError says why it cannot be used.
    It reads one local file and never fetches anything: the user supplies the image and holds the rights to it."""
    if not rel or not rel.strip():
        raise ValueError("show_crests is on, but this team has no crest")
    if PureWindowsPath(rel).is_absolute() or Path(rel).is_absolute():
        raise ValueError(f"crest {rel!r} must be relative to the project folder")
    root = Path(project_dir).resolve()
    path = (root / rel).resolve()  # also follows symlinks, so a link cannot lead out of the project
    if not path.is_relative_to(root):
        raise ValueError(f"crest {rel!r} is outside the project folder")
    if not path.is_file():
        raise ValueError(f"crest not found: {rel}")
    kind = {".png": ("image/png", _png_problem), ".svg": ("image/svg+xml", _svg_problem)}.get(path.suffix.lower())
    if kind is None:
        raise ValueError(f"crest {rel!r} must be a .png or .svg file")
    size = path.stat().st_size
    if size > CREST_MAX_BYTES:
        raise ValueError(f"crest {rel!r} is {size} bytes, over the {CREST_MAX_BYTES} byte limit")
    raw = path.read_bytes()
    problem = kind[1](raw)
    if problem:
        raise ValueError(f"crest {rel!r} {problem}")
    return f"data:{kind[0]};base64,{base64.b64encode(raw).decode('ascii')}"


def resolution(aspect: str, scale: float = 1.0) -> dict:
    r = dict(config()["resolutions"][aspect])
    r["width"], r["height"] = int(round(r["width"] * scale)), int(round(r["height"] * scale))
    return r


def palette(name: str) -> tuple[str, str, str]:
    return tuple(config()["palettes"][name])  # type: ignore[return-value]


def _luminance(hex_colour: str) -> float:
    channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def kit_colours(spec: str) -> tuple[str, str, str]:
    """(fill, ring, text) from a team's real kit, "#RRGGBB" or "#RRGGBB,#RRGGBB" (shirt, then trim). The number colour is whichever reads better."""
    parts = [p.strip().lower() for p in spec.split(",")]
    if len(parts) > 2 or any(not re.fullmatch(r"#[0-9a-f]{6}", p) for p in parts):
        raise ValueError(f"kit colours must be #RRGGBB or #RRGGBB,#RRGGBB, got {spec!r}")
    fill = parts[0]
    text = max(("#ffffff", "#1a1a1a", "#000000"), key=lambda c: _contrast(fill, c))
    return fill, parts[1] if len(parts) == 2 else text, text
