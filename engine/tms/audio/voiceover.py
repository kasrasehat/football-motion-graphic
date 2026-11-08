"""Voice-over: one clip per spoken narration line -> media/vo/Vnn.wav (48 kHz mono) + word timings."""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

import numpy as np

from tms import jsonio
from tms.audio import mock, wav
from tms.audio.elevenlabs import Client, request_hash
from tms.state.project import GateViolation, Project, ProjectError

PRE_ROLL_S = 0.08
TAIL_S = 0.22
BURST_MAX_S = 0.08   # a loud stretch this short at the very end, after silence, is a TTS artefact, not speech
BURST_GAP_S = 0.10
FADE_IN_S = 0.01
FADE_OUT_S = 0.04


def tts_text(text: str, pron: dict[str, str]) -> str:
    """Replace whole-word display tokens by single-token respellings (keeps punctuation, keeps token count)."""
    out = []
    for tok in text.split():
        m = re.match(r"^([\W_]*)(.*?)([\W_]*)$", tok)
        pre, core, post = m.group(1), m.group(2), m.group(3)
        out.append(pre + pron.get(core, core) + post)
    return " ".join(out)


def words_from_alignment(spoken: str, display: str, al: dict) -> list[dict]:
    """Map character timings onto whitespace tokens of `spoken`; pair 1:1 with `display` tokens."""
    chars = al["characters"]
    starts, ends = al["character_start_times_seconds"], al["character_end_times_seconds"]
    text = "".join(chars)
    if text != spoken:  # providers may normalise whitespace; fall back to a tolerant search
        text = "".join(chars)
    toks_s, toks_d = spoken.split(), display.split()
    if len(toks_s) != len(toks_d):
        raise ProjectError("pronunciation respelling changed the word count")
    out, pos = [], 0
    for i, (ts, td) in enumerate(zip(toks_s, toks_d)):
        j = text.find(ts, pos)
        if j < 0:
            raise ProjectError(f"alignment does not contain word {ts!r}")
        k = j + len(ts) - 1
        out.append({"i": i, "display": td, "spoken": ts, "start_s": round(float(starts[j]), 4), "end_s": round(float(ends[k]), 4)})
        pos = k + 1
    return out


def _drop_end_burst(x: np.ndarray, b: int, win: int = 480) -> tuple[int, int]:
    """TTS files sometimes end with a short noise burst after the speech has gone quiet. If the last loud stretch is
    shorter than BURST_MAX_S and follows at least BURST_GAP_S of silence, the speech really ended before it.
    Returns (speech end, limit): the trim must not reach the burst, which starts at `limit`."""
    mono = x.mean(axis=1) if x.ndim > 1 else x
    n = b // win
    if n < 3:
        return b, len(x)
    rms_db = 20 * np.log10(np.sqrt(np.mean(mono[: n * win].reshape(n, win) ** 2, axis=1) + 1e-12))
    loud = rms_db > -40.0
    k = n - 1
    while k >= 0 and loud[k]:
        k -= 1
    burst = n - 1 - k
    gap_end = k
    while k >= 0 and not loud[k]:
        k -= 1
    gap = gap_end - k
    if 0 < burst * win <= BURST_MAX_S * wav.SR and gap * win >= BURST_GAP_S * wav.SR and k >= 0:
        return (k + 1) * win, (gap_end + 1) * win
    return b, len(x)


def _fade_edges(y: np.ndarray) -> np.ndarray:
    """Short raised-cosine fades so no clip can start or stop with a click."""
    y = y.copy()
    fi, fo = min(int(FADE_IN_S * wav.SR), len(y) // 2), min(int(FADE_OUT_S * wav.SR), len(y) // 2)
    if fi:
        y[:fi] *= (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, fi))).reshape(-1, *([1] * (y.ndim - 1)))
    if fo:
        y[-fo:] *= (0.5 + 0.5 * np.cos(np.linspace(0, np.pi, fo))).reshape(-1, *([1] * (y.ndim - 1)))
    return y


def _trim(x: np.ndarray, words: list[dict]) -> tuple[np.ndarray, list[dict], float]:
    """Trim leading silence to PRE_ROLL_S and trailing to TAIL_S (ignoring an end burst); shift words; fade the edges;
    return onset correction."""
    a, b = wav.speech_bounds(x)
    b, limit = _drop_end_burst(x, b)
    start = max(0, a - int(PRE_ROLL_S * wav.SR))
    end = min(limit, b + int(TAIL_S * wav.SR))
    y = _fade_edges(x[start:end])
    shift = start / wav.SR
    ws = [dict(w, start_s=round(max(w["start_s"] - shift, 0.0), 4), end_s=round(max(w["end_s"] - shift, 0.0), 4)) for w in words]
    onset_measured = (a - start) / wav.SR
    correction = round(onset_measured - ws[0]["start_s"], 4) if ws else 0.0
    if abs(correction) > 0.04:  # align word clock to the audible onset
        ws = [dict(w, start_s=round(max(w["start_s"] + correction, 0.0), 4), end_s=round(max(w["end_s"] + correction, 0.0), 4)) for w in ws]
    dur = len(y) / wav.SR
    ws = [dict(w, end_s=min(w["end_s"], round(dur, 4))) for w in ws]
    return y, ws, correction


def expected_hash(provider: str, voice: dict, text: str, prev: str | None, nxt: str | None) -> str:
    if provider == "mock_flite":
        return request_hash("mock_flite", {"text": text})
    settings = {k: voice[k] for k in ("stability", "similarity_boost", "style", "speed")}
    body = {"text": text, "model_id": voice["model_id"], "voice_settings": settings, "seed": voice["seed"],
            "previous_text": prev, "next_text": nxt, "apply_text_normalization": "auto"}
    return request_hash(f"tts:{voice['voice_id']}", body)


def plan_lines(narration: dict) -> list[dict]:
    spoken = [ln for ln in narration["lines"] if not ln["silent"] and ln["text"].strip()]
    out = []
    for k, ln in enumerate(spoken):
        t = tts_text(ln["text"], narration["pronunciations"])
        prev = tts_text(spoken[k - 1]["text"], narration["pronunciations"]) if k > 0 else None
        nxt = tts_text(spoken[k + 1]["text"], narration["pronunciations"]) if k + 1 < len(spoken) else None
        out.append({"id": f"V{k + 1:02d}", "scene": ln["scene"], "text": ln["text"], "tts_text": t, "prev": prev, "next": nxt})
    return out


def build(pr: Project, inputs: dict, client: Client | None = None) -> dict:
    narration = pr.load_artifact("narration_script")
    brief = pr.load_artifact("brief")
    provider = "mock_flite" if pr.dry_run else "elevenlabs"
    voice = brief["voice"]
    if provider == "elevenlabs" and not voice["voice_id"]:
        raise ProjectError("brief.voice.voice_id is empty — pick a voice (live projects need one)")
    lines = plan_lines(narration)
    if provider == "elevenlabs":
        client = client or Client()
        settings = {k: voice[k] for k in ("stability", "similarity_boost", "style", "speed")}
        uncached = [ln for ln in lines if not (client.cache / f"tts-{expected_hash(provider, voice, ln['tts_text'], ln['prev'], ln['next'])}.json").is_file()]
        need = sum(len(ln["tts_text"]) for ln in uncached)
        prior = 0
        old = pr.load_artifact("voiceover_manifest")
        if old:
            prior = old.get("chars_billed_total", 0)
        if prior + need > brief["budget"]["tts_chars_max"]:
            raise GateViolation(f"TTS budget: {prior} already billed + {need} new chars > approved {brief['budget']['tts_chars_max']}")
    clips, billed = [], 0
    vo_dir = pr.dir / "media" / "vo"
    for ln in lines:
        rel = f"media/vo/{ln['id']}.wav"
        if provider == "mock_flite":
            with tempfile.TemporaryDirectory(prefix="tms vo ") as td:
                raw = Path(td) / "raw.wav"
                al = mock.tts(ln["tts_text"], raw)
                x = wav.read(raw)
            cached, chars, h = False, 0, expected_hash(provider, voice, ln["tts_text"], None, None)
        else:
            audio, al, h, cached = client.tts(ln["tts_text"], voice["voice_id"], voice["model_id"], settings, voice["seed"],
                                              ln["prev"], ln["next"])
            with tempfile.TemporaryDirectory(prefix="tms vo ") as td:
                (Path(td) / "raw.mp3").write_bytes(audio)
                wav.to_wav48(Path(td) / "raw.mp3", Path(td) / "raw.wav")
                x = wav.read(Path(td) / "raw.wav")
            chars = 0 if cached else len(ln["tts_text"])
        words = words_from_alignment(ln["tts_text"], ln["text"], al)
        y, words, corr = _trim(x, words)
        wav.write(vo_dir / f"{ln['id']}.wav", y)
        billed += chars
        clips.append({"id": ln["id"], "scene": ln["scene"], "text": ln["text"], "tts_text": ln["tts_text"], "request_hash": h,
                      "cached": cached, "file": rel, "sample_rate": wav.SR, "samples": int(len(y)),
                      "duration_s": round(len(y) / wav.SR, 4), "onset_correction_s": corr, "chars_billed": chars, "words": words})
    prior = (pr.load_artifact("voiceover_manifest") or {}).get("chars_billed_total", 0) if provider == "elevenlabs" else 0
    return {"version": "1", "project_id": pr.id, "inputs": inputs, "provider": provider,
            "voice_id": voice["voice_id"] or "mock", "model_id": voice["model_id"] if provider == "elevenlabs" else "flite",
            "clips": clips, "chars_billed_total": prior + billed}
