"""`tms doctor` — verifies the toolchain before any work. Exit 0 = ready."""
from __future__ import annotations

import json
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from tms import envfile, paths, proc, remotion

REQUIRED_FILTERS = ("loudnorm", "ebur128", "flite", "sidechaincompress", "signalstats",
                    "astats", "silencedetect", "blackdetect", "volume", "aresample")
REQUIRED_ENCODERS = ("libx264", "aac")
ANSI = re.compile(r"\x1b\[[0-9;]*m")  # colour codes in npx output


@dataclass
class Report:
    checks: list[dict] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "", level: str = "error") -> None:
        self.checks.append({"check": name, "ok": ok, "level": "ok" if ok else level, "detail": detail})

    @property
    def failed(self) -> bool:
        return any(c["level"] == "error" for c in self.checks)


def check_python(r: Report) -> None:
    ok_ver = sys.version_info >= (3, 12)
    venv = (paths.root() / ".venv").resolve()
    in_venv = Path(sys.prefix).resolve() == venv
    r.add("python", ok_ver and in_venv, f"{sys.version.split()[0]} prefix={'.venv' if in_venv else sys.prefix}")


def check_ffmpeg(r: Report) -> None:
    for tool in ("ffmpeg", "ffprobe"):
        res = proc.run([tool, "-version"])
        r.add(tool, res.code == 0, res.out.splitlines()[0] if res.out else res.err[:120])
    filt = proc.run(["ffmpeg", "-hide_banner", "-filters"]).out
    names = {m.group(1) for m in re.finditer(r"^\s*[TSC.|]{3}\s+(\S+)", filt, re.M)}
    missing = [f for f in REQUIRED_FILTERS if f not in names]
    r.add("ffmpeg-filters", not missing, "missing: " + ", ".join(missing) if missing else "all present")
    enc = proc.run(["ffmpeg", "-hide_banner", "-encoders"]).out
    missing_enc = [e for e in REQUIRED_ENCODERS if not re.search(rf"\s{e}\s", enc)]
    r.add("ffmpeg-encoders", not missing_enc, "missing: " + ", ".join(missing_enc) if missing_enc else "libx264, aac")


def check_node(r: Report) -> None:
    res = proc.run(["node", "--version"])
    m = re.match(r"v(\d+)", res.out.strip())
    r.add("node", bool(m and int(m.group(1)) >= 20), res.out.strip() or res.err[:120])


def check_render_deps(r: Report) -> None:
    rd = paths.render_dir()
    has_nm = (rd / "node_modules" / "remotion").is_dir()
    r.add("render-node_modules", has_nm, "installed" if has_nm else "run: npm --prefix render ci")
    res = proc.run(["npx", "remotion", "versions"], cwd=rd, timeout=120)
    text = ANSI.sub("", res.out + res.err)
    m = re.search(r"On version:\s*(\d+\.\d+\.\d+)", text)
    ok = res.code == 0 and bool(m) and "All packages have the correct version" in text
    r.add("remotion-versions", ok, f"single version {m.group(1)}" if ok else text[-400:])
    fonts = sorted(p.name for p in (rd / "public" / "fonts").glob("*.woff2"))
    r.add("fonts", len(fonts) >= 3, ", ".join(fonts) or "run: npm --prefix render run fonts")


def check_browser(r: Report) -> None:
    exe = remotion.browser_executable()
    r.add("browser", bool(exe) and Path(exe).is_file(), exe or "set TMS_BROWSER_EXECUTABLE (headless-shell download is geo-blocked)")


def check_smoke_render(r: Report) -> None:
    """60-frame render into a directory whose name contains spaces, then count frames with ffprobe."""
    with tempfile.TemporaryDirectory(prefix="tms doctor ") as td:
        out = Path(td) / "smoke render.mp4"
        try:
            remotion.render("Smoke", out, timeout=600)
        except Exception as e:  # noqa: BLE001 - report any failure verbatim
            r.add("smoke-render", False, str(e)[-600:])
            return
        probe = proc.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                          "stream=nb_read_frames,width,height,r_frame_rate", "-of", "json", str(out)])
        s = json.loads(probe.out)["streams"][0]
        ok = s.get("nb_read_frames") == "60" and s.get("width") == 320 and s.get("r_frame_rate") == "30/1"
        r.add("smoke-render", ok, f"frames={s.get('nb_read_frames')} {s.get('width')}x{s.get('height')} {s.get('r_frame_rate')}")


def check_keys(r: Report) -> None:
    r.add("key:ELEVENLABS_API_KEY", envfile.present("ELEVENLABS_API_KEY"), "present" if envfile.present("ELEVENLABS_API_KEY") else "missing — live audio disabled (mock only)", level="warn")
    r.add("key:API_FOOTBALL_KEY", envfile.present("API_FOOTBALL_KEY"), "present" if envfile.present("API_FOOTBALL_KEY") else "missing — match research runs web-only", level="warn")


def run_doctor(quick: bool = False) -> Report:
    r = Report()
    check_python(r)
    check_ffmpeg(r)
    check_node(r)
    check_render_deps(r)
    check_browser(r)
    if not quick:
        check_smoke_render(r)
    check_keys(r)
    return r


def cmd_doctor(args) -> int:
    rep = run_doctor(quick=args.quick)
    if args.json:
        print(json.dumps({"ok": not rep.failed, "checks": rep.checks}, indent=2))
    else:
        for c in rep.checks:
            mark = {"ok": "PASS", "warn": "WARN", "error": "FAIL"}[c["level"]]
            print(f"[{mark}] {c['check']}: {c['detail']}")
        print("doctor: " + ("FAILED" if rep.failed else "ready"))
    return 1 if rep.failed else 0


def register(sub) -> None:
    p = sub.add_parser("doctor", help="verify toolchain, render smoke test, key presence (names only)")
    p.add_argument("--quick", action="store_true", help="skip the smoke render")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_doctor)
