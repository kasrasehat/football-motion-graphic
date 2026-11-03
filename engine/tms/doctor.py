"""`tms doctor` — verifies the toolchain before any work. Exit 0 = ready."""
from __future__ import annotations

import json
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from tms import envfile, jsonio, paths, proc, remotion

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


# ------------------------------------------------------------------ online checks (--online is free; --probe bills)
PROBE_TEXT = "Watch how one full-back breaks a four-four-two. The right-back steps inside, next to the holding midfielder."
PROBE_MUSIC = "modern broadcast football tactics analysis bed, driving minimal electronic, 100 bpm, no vocals"
PROBE_VOICE = "onwK4e9ZLuTAKqWW03F9"  # premade "Daniel - Steady Broadcaster"; TMS_DEFAULT_VOICE_ID overrides
PROBE_SETTINGS = {"stability": 0.55, "similarity_boost": 0.8, "style": 0.15, "speed": 1.0}
CASSETTE = Path("tests") / "fixtures" / "cassettes" / "elevenlabs_tts_with_timestamps.json"


def check_online(r: Report, client=None) -> object | None:
    """Free account calls. Returns the ElevenLabs client when reachable."""
    from tms.audio.elevenlabs import Client, ElevenLabsError
    from tms.research import api_football as AF
    c = client or Client()
    if not c.key:
        r.add("elevenlabs", False, "no ELEVENLABS_API_KEY", level="warn")
        c = None
    else:
        try:
            s = c.subscription()
            used, limit = int(s.get("character_count") or 0), int(s.get("character_limit") or 0)
            r.add("elevenlabs", True, f"reachable; plan {s.get('tier')}, {limit - used} of {limit} characters left, {s.get('status')}")
        except ElevenLabsError as e:
            hint = " — connect your VPN or set TMS_HTTPS_PROXY" if "403" in str(e) else ""
            r.add("elevenlabs", False, f"{str(e)[:160]}{hint}")
            c = None
    af = AF.Client()
    if not af.available:
        r.add("api-football", False, "no API_FOOTBALL_KEY — match research runs web-only", level="warn")
    else:
        try:
            st = af.get("/status").get("response") or {}
            st = st[0] if isinstance(st, list) and st else st
            sub, req = st.get("subscription") or {}, st.get("requests") or {}
            r.add("api-football", bool(sub.get("active", True)),
                  f"plan {sub.get('plan')}, {req.get('current')}/{req.get('limit_day')} requests used today")
        except AF.ApiError as e:
            r.add("api-football", False, str(e)[:200], level="warn")
    return c


def probe_tts(r: Report, c, record_to: Path | None = None) -> dict | None:
    """~108-character live TTS call (cached by request hash: re-runs are free), parsed by the real voice pipeline."""
    import tempfile
    from tms.audio import wav
    from tms.audio.elevenlabs import ElevenLabsError
    from tms.audio.voiceover import _trim, words_from_alignment
    voice = envfile.get("TMS_DEFAULT_VOICE_ID").strip() or PROBE_VOICE
    try:
        audio, al, h, cached = c.tts(PROBE_TEXT, voice, "eleven_multilingual_v2", PROBE_SETTINGS, 1234)
    except ElevenLabsError as e:
        r.add("probe-tts", False, str(e)[:300])
        return None
    out = paths.scratch_dir() / "probe"
    out.mkdir(parents=True, exist_ok=True)
    (out / "tts.mp3").write_bytes(audio)
    with tempfile.TemporaryDirectory(prefix="tms probe ") as td:
        wav.to_wav48(out / "tts.mp3", Path(td) / "tts.wav")
        x = wav.read(Path(td) / "tts.wav")
    words = words_from_alignment(PROBE_TEXT, PROBE_TEXT, al)
    y, words, corr = _trim(x, words)
    wav.write(out / "tts_trimmed.wav", y)
    span = max(words[-1]["end_s"] - words[0]["start_s"], 0.1)
    wpm = len(words) / span * 60
    ok = len(words) == len(PROBE_TEXT.split()) and abs(corr) <= 0.12 and 100 <= wpm <= 220
    r.add("probe-tts", ok, f"voice {voice}; {len(PROBE_TEXT)} chars {'(cached, not billed)' if cached else 'billed'}; "
                           f"{len(words)}/{len(PROBE_TEXT.split())} words aligned; {len(y) / wav.SR:.2f}s; {wpm:.0f} wpm; "
                           f"onset correction {corr * 1000:.0f} ms; audio: {out / 'tts_trimmed.wav'}")
    if record_to is not None and ok:
        doc = {"_synthetic": False, "_recorded_at": jsonio.now_iso(),
               "_note": "real ElevenLabs /with-timestamps response recorded by `tms doctor --online --probe --record-cassette`",
               "request": {"path": "/v1/text-to-speech/{voice_id}/with-timestamps", "text": PROBE_TEXT, "voice_id": voice,
                           "model_id": "eleven_multilingual_v2", "voice_settings": PROBE_SETTINGS, "seed": 1234},
               "response": {"audio_base64": __import__("base64").b64encode(audio).decode(), "alignment": al}}
        record_to.write_text(json.dumps(doc), encoding="utf-8", newline="\n")
        r.add("cassette", True, f"recorded real response to {record_to.as_posix()}")
    return {"words": words, "onset_correction_s": corr, "wpm": wpm, "cached": cached}


def probe_music(r: Report, c) -> bool:
    """10-second live Music call (cached). A refusal means the plan has no Music access: not an error."""
    from tms.audio import wav
    from tms.audio.elevenlabs import ElevenLabsError
    try:
        audio, h, cached = c.music(PROBE_MUSIC, 10000, seed=7)
    except ElevenLabsError as e:
        msg = str(e)
        if any(f"HTTP {code}" in msg for code in (401, 402, 403)):  # plan / permission: not a bug
            r.add("probe-music", False, f"Music unavailable on this plan ({msg[:200]}) — use your own track "
                                        "(brief.music.source=file) or narration only", level="warn")
        else:  # anything else (e.g. 422 bad request) is our bug or an outage: fail loudly
            r.add("probe-music", False, f"music request failed: {msg[:300]}")
        return False
    out = paths.scratch_dir() / "probe" / "music.mp3"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(audio)
    dur = wav.duration(out)
    r.add("probe-music", 8.0 <= dur <= 13.0, f"{dur:.1f}s instrumental clip {'(cached, not billed)' if cached else 'billed'}; audio: {out}")
    return True


def run_doctor(quick: bool = False, online: bool = False, probe: bool = False, record: bool = False) -> Report:
    r = Report()
    check_python(r)
    check_ffmpeg(r)
    check_node(r)
    check_render_deps(r)
    check_browser(r)
    if not quick:
        check_smoke_render(r)
    check_keys(r)
    if online or probe:
        c = check_online(r)
        if probe and c is not None:
            probe_tts(r, c, paths.root() / CASSETTE if record else None)
            probe_music(r, c)
    return r


def cmd_doctor(args) -> int:
    rep = run_doctor(quick=args.quick, online=args.online, probe=args.probe, record=args.record_cassette)
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
    p.add_argument("--online", action="store_true", help="free account checks: ElevenLabs plan/characters, API-Football status")
    p.add_argument("--probe", action="store_true",
                   help="PAID: ~108-char voice sample + 10 s music clip (cached afterwards); only with the user's OK")
    p.add_argument("--record-cassette", action="store_true", help="with --probe: save the real TTS response as the test cassette")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_doctor)
