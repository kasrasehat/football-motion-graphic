"""VO / TL / MU rules."""
from __future__ import annotations

import math

import numpy as np

from tms.audio import wav
from tms.timeline import SPF
from tms.validate.registry import rule


def _clip_path(ctx, rel):
    return (ctx.project_dir / rel) if ctx.project_dir is not None else None


# ------------------------------------------------------------------ VO
@rule("VO-01")
def clips_complete(doc, ctx, p):
    nar = ctx.other("narration_script")
    if nar:
        spoken = [ln["scene"] for ln in nar["lines"] if not ln["silent"] and ln["text"].strip()]
        got = [c["scene"] for c in doc["clips"]]
        if got != spoken:
            yield "clips", f"clips for scenes {got}, narration speaks in {spoken}"
    for c in doc["clips"]:
        prev = -1.0
        for w in c["words"]:
            if not w["start_s"] < w["end_s"] or w["start_s"] < prev - 1e-6:
                yield c["id"], f"word {w['i']} {w['display']!r} has bad timing ({w['start_s']}-{w['end_s']})"
                break
            prev = w["start_s"]
        if c["words"] and c["words"][-1]["end_s"] > c["duration_s"] + 0.05:
            yield c["id"], "last word ends after the clip"


@rule("VO-02")
def words_match_text(doc, ctx, p):
    for c in doc["clips"]:
        toks = c["text"].split()
        if [w["display"] for w in c["words"]] != toks:
            yield c["id"], "clip words do not match the narration text token for token"


@rule("VO-03")
def onset(doc, ctx, p):
    for c in doc["clips"]:
        o = abs(c["onset_correction_s"])
        if o > p["max_s"]:
            yield c["id"], f"onset correction {o * 1000:.0f} ms (> {p['max_s'] * 1000:.0f})", "error"
        elif o > p["warn_s"]:
            yield c["id"], f"onset correction {o * 1000:.0f} ms"


@rule("VO-04")
def files_ok(doc, ctx, p):
    for c in doc["clips"]:
        f = _clip_path(ctx, c["file"])
        if f is None:
            return
        if not f.is_file():
            yield c["id"], f"{c['file']} missing"
            continue
        try:
            x = wav.read(f)
        except ValueError as e:
            yield c["id"], str(e)
            continue
        if x.ndim != 1:
            yield c["id"], "voice clip must be mono"
        if len(x) != c["samples"]:
            yield c["id"], f"{len(x)} samples on disk, manifest says {c['samples']}"
        _, b = wav.speech_bounds(x)
        if (len(x) - b) / wav.SR > p["tail_s"]:
            yield c["id"], f"{(len(x) - b) / wav.SR:.2f}s trailing silence"


_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
         "seventeen eighteen nineteen").split()


def _int_words(n: int) -> int:
    """How many words an integer takes to say ('forty-five' counts as two, as it is spoken)."""
    if n < 20:
        return 1
    if n < 100:
        return 1 + (n % 10 != 0)
    if n < 1000:
        return 2 + (_int_words(n % 100) if n % 100 else 0)
    return _int_words(n // 1000) + 1 + (_int_words(n % 1000) if n % 1000 else 0)


def spoken_words(token: str) -> int:
    """Words a token takes to say aloud: '1.56' -> one point five six (4), '45%' -> forty five percent (3), '17th' -> 1."""
    t = token.strip(".,;:!?\"'()")
    digits = "".join(ch for ch in t if ch.isdigit() or ch == ".")
    if not any(ch.isdigit() for ch in t):
        return 1
    whole, _, frac = digits.partition(".")
    n = _int_words(int(whole)) if whole.isdigit() else 0
    n += (1 + len(frac)) if frac.isdigit() else 0
    return max(1, n) + ("%" in t)


@rule("VO-05")
def speaking_rate(doc, ctx, p):
    for c in doc["clips"]:
        if len(c["words"]) < 4:
            continue
        span = c["words"][-1]["end_s"] - c["words"][0]["start_s"]
        spoken = sum(spoken_words(w.get("display") or w.get("text") or "") for w in c["words"])
        wpm = spoken / max(span, 0.1) * 60
        if not p["min"] <= wpm <= p["max"]:
            if doc["provider"] == "mock_flite":  # rewording barely slows flite, and its pace says nothing about a real voice, so it only warns
                yield c["id"], f"{wpm:.0f} words per minute (mock voice)"
            else:
                yield c["id"], f"{wpm:.0f} words per minute", "error"
        elif not p["lo"] <= wpm <= p["hi"]:
            yield c["id"], f"{wpm:.0f} words per minute"


@rule("VO-07")
def clean_edges(doc, ctx, p):
    for c in doc["clips"]:
        f = _clip_path(ctx, c["file"])
        if f is None:
            return
        if not f.is_file():
            continue
        x = wav.read(f)
        n = max(1, int(p["edge_s"] * wav.SR))
        if len(x) < 2 * n:
            continue
        for where, seg in (("start", x[:n]), ("end", x[-n:])):
            level = 20 * math.log10(float(np.sqrt(np.mean(np.asarray(seg, dtype=np.float64) ** 2))) + 1e-12)
            if level > p["max_db"]:
                yield c["id"], f"clip {where}s at {level:.0f} dBFS: it will click against the next line (rebuild the voice-over)"


@rule("VO-06")
def not_stale(doc, ctx, p):
    nar, brief = ctx.other("narration_script"), ctx.other("brief")
    if not nar or not brief:
        return
    from tms.audio.voiceover import expected_hash, plan_lines
    plan = {ln["id"]: ln for ln in plan_lines(nar)}
    for c in doc["clips"]:
        ln = plan.get(c["id"])
        if ln is None or ln["text"] != c["text"]:
            yield c["id"], "narration changed since this clip was made — rebuild the voice-over"
            continue
        want = expected_hash(doc["provider"], brief["voice"], ln["tts_text"], ln["prev"], ln["next"])
        if want != c["request_hash"]:
            yield c["id"], "voice settings or neighbouring lines changed since this clip was made — rebuild the voice-over"


# ------------------------------------------------------------------ TL
@rule("TL-01")
def contiguous(doc, ctx, p):
    cur = doc["intro"]["to"]
    if doc["intro"]["from"] != 0:
        yield "intro", "must start at frame 0"
    for s in doc["scenes"]:
        if s["from"] != cur or s["to"] <= s["from"]:
            yield s["id"], f"scene spans {s['from']}-{s['to']}, expected to start at {cur}"
        cur = s["to"]
    if doc["outro"]["from"] != cur or doc["outro"]["to"] != doc["frames"]:
        yield "outro", f"outro {doc['outro']} does not close the timeline at {doc['frames']}"


@rule("TL-02")
def clips_in_scene(doc, ctx, p):
    scenes = {s["id"]: s for s in doc["scenes"]}
    prev_end = -1
    for v in sorted(doc["vo"], key=lambda v: v["from"]):
        s = scenes.get(v["scene"])
        end = v["from"] + math.ceil(v["samples"] / SPF)
        if s is None or v["from"] < s["from"] or end > s["to"]:
            yield v["id"], f"clip {v['from']}-{end} outside its scene"
        if v["from"] < prev_end:
            yield v["id"], "overlaps the previous clip"
        prev_end = end


@rule("TL-03")
def warp_slopes(doc, ctx, p):
    hold_total = 0
    for s in doc["scenes"]:
        w = s["warp"]
        if w[-1][1] != s["to"] - s["from"]:
            yield s["id"], "warp does not end on the scene's last frame"
        for (t0, f0), (t1, f1) in zip(w, w[1:]):
            if t1 < t0 or f1 < f0:
                yield s["id"], "warp goes backwards"
            elif t1 == t0:
                if f1 - f0 > p["max_hold_f"]:
                    yield s["id"], f"hold of {(f1 - f0) / 30:.1f}s at tau {t0}s (> {p['max_hold_f'] / 30:.0f}s)"
                hold_total += f1 - f0
            else:
                slope = (f1 - f0) / 30 / (t1 - t0)
                lo_f, hi_f = p["lo"] * (t1 - t0) * 30 - 1, p["hi"] * (t1 - t0) * 30 + 1  # one frame of rounding
                if not lo_f <= (f1 - f0) <= hi_f:
                    yield s["id"], f"motion runs at {slope:.2f}x between tau {t0}s and {t1}s"
    if hold_total > p["hold_share"] * doc["frames"]:
        yield "scenes", f"{hold_total / 30:.1f}s of frozen holds ({hold_total / doc['frames']:.0%} of the video)", "warning"


@rule("TL-04")
def anchors_hit(doc, ctx, p):
    for a in doc["anchors"]:
        if abs(a["err"]) > p["max_f"]:
            yield a["scene"], f"anchor {a['ref']} is {a['err']} frames off its word"


@rule("TL-05")
def duration_ok(doc, ctx, p):
    brief = ctx.other("brief")
    if not brief:
        return
    r = doc["frames"] / 30 / brief["target_duration_s"]
    if not p["lo"] <= r <= p["hi"]:
        yield "frames", f"{doc['frames'] / 30:.0f}s is {r:.2f}x the {brief['target_duration_s']}s target"
    elif not p["wlo"] <= r <= p["whi"]:
        yield "frames", f"{doc['frames'] / 30:.0f}s is {r:.2f}x the target", "warning"


@rule("TL-06")
def captions_ok(doc, ctx, p):
    words = {w["i"]: w for w in doc["words"]}
    covered = []
    for c in doc["captions"]:
        if len(c["lines"]) > 2 or any(len(ln) > 42 for ln in c["lines"]):
            yield c["id"], "more than 2 lines or a line over 42 chars"
        dur = c["to"] - c["from"]
        if not p["min_f"] <= dur <= p["max_f"]:
            yield c["id"], f"on screen {dur / 30:.2f}s (0.8-6 s)"
        chars = len(" ".join(c["lines"]))
        if dur > 0 and chars / (dur / 30) > p["cps"] + 0.5:
            yield c["id"], f"{chars / (dur / 30):.0f} chars/s (> {p['cps']})"
        a, b = c["words"]
        clips = {words[i]["clip"] for i in range(a, b + 1) if i in words}
        if len(clips) > 1:
            yield c["id"], "caption spans two voice clips"
        covered += list(range(a, b + 1))
    if covered != sorted(words):
        yield "captions", "captions do not cover every spoken word exactly once, in order"


@rule("TL-07")
def words_monotonic(doc, ctx, p):
    clips = {v["id"]: (v["from"], v["from"] + math.ceil(v["samples"] / SPF)) for v in doc["vo"]}
    prev = -1
    for w in doc["words"]:
        a, b = clips.get(w["clip"], (None, None))
        if a is None or not a <= w["from"] < w["to"] <= b + 1:
            yield f"word {w['i']}", f"{w['display']!r} at {w['from']}-{w['to']} outside clip {w['clip']}"
        if w["from"] < prev:
            yield f"word {w['i']}", "words out of order"
        prev = w["from"]


@rule("TL-09")
def intro_and_first_word(doc, ctx, p):
    if doc["intro"]["to"] - doc["intro"]["from"] > p["intro_max_f"]:
        yield "intro", "title card longer than 2 s"
    if doc["vo"] and doc["scenes"]:
        if doc["vo"][0]["from"] - doc["scenes"][0]["from"] > p["first_word_max_f"]:
            yield "vo", "the narration starts too late after the title card"


@rule("TL-10")
def outro_length(doc, ctx, p):
    if doc["outro"]["to"] - doc["outro"]["from"] < p["min_f"]:
        yield "outro", "end card shorter than 2 s"


# ------------------------------------------------------------------ MU
@rule("MU-01")
def splices(doc, ctx, p):
    tl = ctx.other("timeline")
    if not tl or doc["source"] == "none":
        return
    need = tl["frames"] / 30
    avail = doc["raw_duration_s"] - doc["body"]["start_s"]
    if avail <= 2.5:
        yield "raw_file", "music too short to use"
        return
    n = 0 if avail >= need else math.ceil((need - avail) / (avail - 2.0))
    if n > 2:
        yield "raw_file", f"{n} loop splices needed (max 2): generate or supply a longer track"


@rule("MU-02")
def no_dropouts(doc, ctx, p):
    if not doc.get("fitted_file") or ctx.project_dir is None:
        return
    x = wav.read(ctx.project_dir / doc["fitted_file"])
    mono = x.mean(axis=1) if x.ndim > 1 else x
    win = wav.SR // 10
    n = len(mono) // win
    rms = 20 * np.log10(np.sqrt(np.mean(mono[: n * win].reshape(n, win) ** 2, axis=1)) + 1e-12)
    silent = rms < p["db"]
    silent[:10] = False   # fade-in
    silent[-30:] = False  # fade-out
    run = 0
    for k, s in enumerate(silent):
        run = run + 1 if s else 0
        if run > p["s"] * 10:
            yield "fitted_file", f"music drops to silence around {k / 10:.1f}s"
            return


@rule("MU-03")
def exact_length(doc, ctx, p):
    tl = ctx.other("timeline")
    if not doc.get("fitted_file"):
        return
    if tl and doc["samples"] != tl["frames"] * SPF:
        yield "samples", f"{doc['samples']} samples, timeline needs {tl['frames'] * SPF}"
    if ctx.project_dir is not None:
        x = wav.read(ctx.project_dir / doc["fitted_file"])
        if x.ndim != 2 or x.shape[1] != 2 or len(x) != doc["samples"]:
            yield "fitted_file", "fitted bed must be stereo with exactly the manifest's sample count"


@rule("MU-04")
def fades(doc, ctx, p):
    if not doc.get("fitted_file"):
        return
    if doc["fade_in_frames"] > p["in_max"]:
        yield "fade_in_frames", "fade-in longer than 1 s"
    if not p["out_min"] <= doc["fade_out_frames"] <= p["out_max"]:
        yield "fade_out_frames", "fade-out must be 2-3 s"
