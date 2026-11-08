"""M6: voice-over, timeline, music, mix — clean path on a mock project + one negative test per VO/TL/MU rule."""
from __future__ import annotations

import base64
import copy
import json
from pathlib import Path

import httpx
import numpy as np
import pytest

from tms import jsonio
from tms.audio import music, voiceover, wav
from tms.audio.elevenlabs import Client
from tms.audio.mix import mix
from tms.choreo.cli import compile_project
from tms.state import project as P
from tms.state.project import GateViolation
from tms.timeline.build import TimelineError, build_timeline, solve_scene
from tms.timeline import SPF as SPF_
from tms.validate.registry import Context
from tests.helpers import FIX, expect_clean, expect_violation, findings, fixture, place

pytestmark = pytest.mark.fast


@pytest.fixture(scope="module")
def ap(tmp_path_factory):
    """An audio-ready dry-run project built with the offline providers (module scope: built once)."""
    root = tmp_path_factory.mktemp("audio")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TMS_PROJECTS_DIR", str(root / "projects"))
        mp.setenv("TMS_SCRATCH_DIR", str(root / "scratch"))
        mp.setenv("TMS_KEY_DIR", str(root / "keys"))
        pr = P.init("fx-ifb-442", "tactic", "audio", dry_run=True)
        for n in ("brief", "tactic_spec", "scene_plan", "narration_script"):
            place(pr.dir, n, fixture(n))
        compile_project(pr)
        vo = voiceover.build(pr, {})
        jsonio.write_json(pr.artifact_path("voiceover_manifest"), vo)
        tl, warns = build_timeline(pr.load_artifact("choreography"), vo, pr.load_artifact("narration_script"), pr.id, {})
        jsonio.write_json(pr.artifact_path("timeline"), tl)
        mm = music.build(pr, tl, {})
        jsonio.write_json(pr.artifact_path("music_manifest"), mm)
    return pr


def ctx(pr, **override):
    arts = {n: pr.load_artifact(n) for n in ("brief", "narration_script", "choreography", "timeline", "voiceover_manifest")}
    arts.update(override)
    return Context(project_dir=pr.dir, mode="tactic", artifacts=arts)


def doc(pr, name):
    return copy.deepcopy(pr.load_artifact(name))


def test_clean_path(ap):
    for name in ("voiceover_manifest", "timeline", "music_manifest"):
        expect_clean(name, doc(ap, name), ctx(ap))


def test_mix_meets_loudness_and_ducking(ap, tmp_path):
    info = mix(ap.dir, ap.load_artifact("timeline"), ap.load_artifact("music_manifest"), tmp_path / "mix.wav")
    assert -15.0 <= info["integrated_lufs"] <= -13.0, info
    assert info["true_peak_dbtp"] <= -1.0, info
    assert info["vo_music_margin_db"] >= 9.0, info
    assert len(wav.read(tmp_path / "mix.wav")) == ap.load_artifact("timeline")["frames"] * 1600


def test_anchors_land_on_their_words(ap):
    tl = ap.load_artifact("timeline")
    assert tl["anchors"] and all(abs(a["err"]) <= 2 for a in tl["anchors"])


# ------------------------------------------------------------------ warp solver
def _scene(ap, sid):
    ch = ap.load_artifact("choreography")
    return ch, next(s for s in ch["scenes"] if s["id"] == sid)


def _clip(ap, sid, k):
    c = copy.deepcopy(next(c for c in ap.load_artifact("voiceover_manifest")["clips"] if c["scene"] == sid))
    for w in c["words"]:
        w["start_s"], w["end_s"] = round(w["start_s"] * k, 4), round(w["end_s"] * k, 4)
    c["duration_s"] = round(c["duration_s"] * k, 4)
    return c


def test_long_narration_uses_the_declared_hold(ap):
    # S02's declared hold (after the full-back's run) lies in the segment that the longer narration overfills
    ch, s = _scene(ap, "S02")
    anchors = next(ln for ln in fixture("narration_script")["lines"] if ln["scene"] == "S02")["anchors"]
    warns: list[str] = []
    clip = _clip(ap, "S02", 1.0)
    clip["duration_s"] += 8.0  # the voice keeps talking well past the end of the motion
    warp, length, _, _ = solve_scene(ch, s, clip, anchors, warns)
    flats = [(a, b) for (a, b) in zip(warp, warp[1:]) if a[0] == b[0] and b[1] > a[1]]
    hold_tau = s["holds"][0]["tau"] - s["tau0"]
    assert any(abs(a[0] - hold_tau) < 1e-3 for a, _ in flats), (warp, hold_tau)


def test_compressed_narration_is_rejected_with_a_fix(ap):
    ch, s = _scene(ap, "S03")
    anchors = next(ln for ln in fixture("narration_script")["lines"] if ln["scene"] == "S03")["anchors"]
    with pytest.raises(TimelineError, match="compression"):
        solve_scene(ch, s, _clip(ap, "S03", 0.4), anchors, [])


# ------------------------------------------------------------------ live client via cassette (no network)
def test_elevenlabs_path_with_cassette(tmp_projects, monkeypatch, tmp_path):
    cas = json.loads((FIX / "cassettes" / "elevenlabs_tts_with_timestamps.json").read_text(encoding="utf-8"))
    calls = []

    def fake_request(method, url, **kw):
        calls.append(url)
        text = kw["json"]["text"]
        audio = base64.b64decode(cas["response"]["audio_base64"])
        n = len(text)
        al = {"characters": list(text), "character_start_times_seconds": [0.1 + 2.5 * i / n for i in range(n)],
              "character_end_times_seconds": [0.1 + 2.5 * (i + 1) / n for i in range(n)]}
        body = {"audio_base64": base64.b64encode(audio).decode(), "alignment": al, "normalized_alignment": al}
        return httpx.Response(200, json=body, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "request", fake_request)
    pr = P.init("live-proj", "tactic", "live", dry_run=False)
    b = dict(fixture("brief"), project_id="live-proj")
    b["voice"] = dict(b["voice"], voice_id="testvoice123")
    place(pr.dir, "brief", b)
    place(pr.dir, "narration_script", dict(fixture("narration_script"), project_id="live-proj"))
    client = Client(key="test-key-not-real", cache_dir=tmp_path / "cache")
    vo = voiceover.build(pr, {}, client=client)
    assert vo["provider"] == "elevenlabs" and vo["chars_billed_total"] > 0 and len(calls) == len(vo["clips"])
    assert all(c["words"][0]["display"] == c["text"].split()[0] for c in vo["clips"])
    jsonio.write_json(pr.artifact_path("voiceover_manifest"), vo)
    again = voiceover.build(pr, {}, client=client)
    assert all(c["cached"] for c in again["clips"]) and len(calls) == len(vo["clips"])  # cache: no new requests
    assert again["chars_billed_total"] == vo["chars_billed_total"]
    b["budget"]["tts_chars_max"] = 10
    place(pr.dir, "brief", b)
    with pytest.raises(GateViolation, match="TTS budget"):
        voiceover.build(pr, {}, client=Client(key="k", cache_dir=tmp_path / "empty-cache"))


# ------------------------------------------------------------------ VO negatives
def test_VO01_missing_clip(ap):
    d = doc(ap, "voiceover_manifest")
    del d["clips"][1]
    expect_violation("VO-01", "voiceover_manifest", d, ctx(ap))


def test_VO02_words_do_not_match(ap):
    d = doc(ap, "voiceover_manifest")
    d["clips"][0]["words"][0]["display"] = "Look"
    expect_violation("VO-02", "voiceover_manifest", d, ctx(ap))


def test_VO03_onset_off(ap):
    d = doc(ap, "voiceover_manifest")
    d["clips"][0]["onset_correction_s"] = 0.2
    expect_violation("VO-03", "voiceover_manifest", d, ctx(ap))


def test_VO04_sample_mismatch(ap):
    d = doc(ap, "voiceover_manifest")
    d["clips"][0]["samples"] += 4800
    expect_violation("VO-04", "voiceover_manifest", d, ctx(ap))


def test_VO05_rate(ap):
    d = doc(ap, "voiceover_manifest")
    c = d["clips"][0]
    for k, w in enumerate(c["words"]):
        w["start_s"], w["end_s"] = round(0.1 + 0.1 * k, 3), round(0.18 + 0.1 * k, 3)
    expect_violation("VO-05", "voiceover_manifest", d, ctx(ap))


def _too_fast(ap, provider):
    d = doc(ap, "voiceover_manifest")
    d["provider"] = provider
    for k, w in enumerate(d["clips"][0]["words"]):
        w["start_s"], w["end_s"] = round(0.1 + 0.1 * k, 3), round(0.18 + 0.1 * k, 3)
    return [f for f in findings("voiceover_manifest", d, ctx(ap)) if f.rule == "VO-05"]


def test_VO05_out_of_range_only_warns_for_the_mock_voice(ap):
    assert {f.severity for f in _too_fast(ap, "mock_flite")} == {"warning"}


def test_VO05_out_of_range_is_an_error_for_a_real_voice(ap):
    assert "error" in {f.severity for f in _too_fast(ap, "elevenlabs")}


def test_VO06_stale_after_narration_edit(ap):
    nar = fixture("narration_script")
    nar["lines"][0]["text"] = "A different opening line for this video."
    expect_violation("VO-06", "voiceover_manifest", doc(ap, "voiceover_manifest"), ctx(ap, narration_script=nar))


# ------------------------------------------------------------------ TL negatives
def test_TL01_gap(ap):
    d = doc(ap, "timeline")
    d["scenes"][1]["from"] += 3
    expect_violation("TL-01", "timeline", d, ctx(ap))


def test_TL02_clip_outside_scene(ap):
    d = doc(ap, "timeline")
    d["vo"][1]["from"] = d["scenes"][1]["from"] - 20
    expect_violation("TL-02", "timeline", d, ctx(ap))


def test_TL03_fast_motion(ap):
    d = doc(ap, "timeline")
    s = next(x for x in d["scenes"] if x["id"] == "S05")
    end = s["warp"][-1]
    s["warp"] = [[0.0, 0], [3.0, 30], end]
    expect_violation("TL-03", "timeline", d, ctx(ap))


def test_TL04_anchor_off(ap):
    d = doc(ap, "timeline")
    d["anchors"][0]["err"] = 5
    expect_violation("TL-04", "timeline", d, ctx(ap))


def test_TL05_duration_vs_target(ap):
    b = fixture("brief")
    b["target_duration_s"] = 120
    expect_violation("TL-05", "timeline", doc(ap, "timeline"), ctx(ap, brief=b))


def test_TL06_three_line_caption(ap):
    d = doc(ap, "timeline")
    d["captions"][0]["lines"] = ["a", "b"]
    d["captions"][0]["to"] = d["captions"][0]["from"] + 5
    expect_violation("TL-06", "timeline", d, ctx(ap))


def test_TL07_word_outside_clip(ap):
    d = doc(ap, "timeline")
    d["words"][0]["from"] = 0
    expect_violation("TL-07", "timeline", d, ctx(ap))


def test_TL09_late_first_word(ap):
    d = doc(ap, "timeline")
    d["vo"][0]["from"] = d["scenes"][0]["from"] + 80
    expect_violation("TL-09", "timeline", d, ctx(ap))


def test_TL10_short_end_card(ap):
    d = doc(ap, "timeline")
    d["outro"]["to"] = d["outro"]["from"] + 30
    d["frames"] = d["outro"]["to"]
    expect_violation("TL-10", "timeline", d, ctx(ap))


# ------------------------------------------------------------------ MU negatives
def test_MU01_too_many_splices(ap):
    d = doc(ap, "music_manifest")
    d["raw_duration_s"] = 8.0
    expect_violation("MU-01", "music_manifest", d, ctx(ap))


def test_MU02_dropout(ap):
    d = doc(ap, "music_manifest")
    x = wav.read(ap.dir / d["fitted_file"]).copy()
    x[48000 * 10: 48000 * 13] = 0.0
    wav.write(ap.dir / "media" / "music" / "dropout.wav", x)
    d["fitted_file"] = "media/music/dropout.wav"
    expect_violation("MU-02", "music_manifest", d, ctx(ap))


def test_MU03_wrong_length(ap):
    d = doc(ap, "music_manifest")
    d["samples"] -= 1600
    expect_violation("MU-03", "music_manifest", d, ctx(ap))


def test_MU04_abrupt_ending(ap):
    d = doc(ap, "music_manifest")
    d["fade_out_frames"] = 10
    expect_violation("MU-04", "music_manifest", d, ctx(ap))


@pytest.mark.render
def test_sync_calibration_end_to_end():
    from tms.qa.sync import run
    res = run()
    assert res["ok"], res


def test_music_request_stays_within_the_approved_budget():
    assert music.music_request_s(100.0, 180) == pytest.approx(100.0 + music.EXTRA_S)  # fits: video + extra
    assert music.music_request_s(179.0, 180) == 180.0  # over by the extra only: generate the cap, fit() loops the rest
    with pytest.raises(GateViolation, match="music budget"):
        music.music_request_s(179.0, 80)  # would need more than one loop


def test_fit_loops_a_bed_shorter_than_the_video():
    sr = wav.SR
    raw = (np.sin(np.linspace(0, 2000, sr * 10)) * 0.2).astype(np.float32)
    frames = 12 * 30  # 12 s video from a 10 s bed
    out, info = music.fit(raw, frames)
    assert len(out) == frames * music.SPF
    assert info["splices"] == 1


def test_fit_drops_a_silent_outro_and_loops_instead():
    sr = wav.SR
    tone = (np.sin(np.linspace(0, 4000, sr * 20)) * 0.2).astype(np.float32)
    raw = np.concatenate([tone, np.zeros(sr * 4, dtype=np.float32)])  # 20 s of music, then a 4 s silent outro
    frames = 22 * 30  # the raw file (24 s) is long enough, but its last 4 s are silent
    out, info = music.fit(raw, frames)
    assert info["splices"] == 1
    mono = out[music.FADE_IN_F * music.SPF: -music.FADE_OUT_F * music.SPF].mean(axis=1)  # between the fades
    win = sr // 10
    tail = mono[-(len(mono) // win) * win:].reshape(-1, win)
    assert np.sqrt((tail ** 2).mean(axis=1)).min() > 0.01  # no silent window before the fade-out


@pytest.mark.parametrize("token, n", [("goals", 1), ("1.56", 4), ("1.21.", 4), ("45%", 3), ("45%,", 3), ("17th", 1),
                                       ("12", 1), ("31", 2), ("2026", 4), ("seven", 1)])
def test_VO05_counts_numbers_as_spoken(token, n):
    from tms.validate.audio_rules import spoken_words
    assert spoken_words(token) == n


def test_VO05_decimals_do_not_make_a_normal_voice_look_slow(ap):
    d = doc(ap, "voiceover_manifest")
    d["provider"] = "elevenlabs"
    c = d["clips"][0]
    words = ["United", "create", "1.56", "expected", "goals", "while", "Villa", "create", "1.21."]
    t = 0.0
    c["words"] = []
    for k, w in enumerate(words):  # numbers take as long as the four or five words they are spoken as
        dur = 1.6 if any(ch.isdigit() for ch in w) else 0.3
        c["words"].append({"i": k, "display": w, "spoken": w, "start_s": round(t, 3), "end_s": round(t + dur, 3)})
        t += dur + 0.08
    errs = [f for f in findings("voiceover_manifest", d, ctx(ap)) if f.rule == "VO-05" and f.location == c["id"] and f.severity == "error"]
    assert not errs  # 7 words + 2 x 4 spoken = 15 words in about 5.5 s: well over 100 wpm


def test_duck_stays_down_across_scene_gaps_and_after_the_last_line():
    from tms.timeline.build import DUCK_BRIDGE_F, duck_windows
    vo = [{"from": 60, "samples": 400 * SPF_}, {"from": 470, "samples": 300 * SPF_},  # 10-frame gap: bridged
          {"from": 770 + DUCK_BRIDGE_F + 30, "samples": 200 * SPF_}]               # a real pause: its own window
    w = duck_windows(vo, 2000)
    assert w == [[60, 770], [875, 2000]]  # the last window runs to the end of the video


def test_duck_envelope_never_jumps():
    from tms.audio.mix import duck_envelope
    from tms.timeline.build import DUCK_ATTACK_MS, DUCK_DEPTH_DB, DUCK_RELEASE_MS
    tl = {"frames": 900, "duck": {"windows": [[60, 300], [450, 900]], "depth_db": DUCK_DEPTH_DB,
                                  "attack_ms": DUCK_ATTACK_MS, "release_ms": DUCK_RELEASE_MS}}
    g = 20 * np.log10(duck_envelope(tl) + 1e-9)
    step = wav.SR // 10
    assert np.abs(np.diff(g[::step])).max() <= 6.0  # at most 6 dB change per 100 ms: no sudden swells
    assert g[-1] == pytest.approx(DUCK_DEPTH_DB, abs=0.01)  # still ducked at the very end


def _clip_with_end_burst():
    sr = wav.SR
    speech = (np.sin(np.linspace(0, 3000, sr)) * 0.3).astype(np.float32)          # 1 s "speech"
    gap = np.zeros(int(0.15 * sr), dtype=np.float32)                               # 150 ms silence
    burst = (np.sin(np.linspace(0, 200, int(0.03 * sr))) * 0.2).astype(np.float32)  # 30 ms burst at the very end
    lead = np.zeros(int(0.2 * sr), dtype=np.float32)                                # real clips start with silence
    return np.concatenate([lead, speech, gap, burst]), len(lead) + len(speech)


def test_trim_drops_a_tts_end_burst_and_fades_the_edges():
    x, speech_end = _clip_with_end_burst()
    words = [{"i": 0, "display": "Hello", "spoken": "Hello", "start_s": 0.2, "end_s": 1.2}]
    y, ws, _ = voiceover._trim(x, words)
    assert len(y) < len(x)  # the burst is gone
    edge = int(0.01 * wav.SR)
    assert 20 * np.log10(np.sqrt(np.mean(y[-edge:] ** 2)) + 1e-12) < -45  # ends quietly
    assert 20 * np.log10(np.sqrt(np.mean(y[:edge] ** 2)) + 1e-12) < -45   # starts quietly


def test_trim_keeps_real_speech_at_the_end():
    sr = wav.SR
    x = (np.sin(np.linspace(0, 3000, sr)) * 0.3).astype(np.float32)  # speech right to the last sample, no gap
    y, _, _ = voiceover._trim(x, [{"i": 0, "display": "Hi", "spoken": "Hi", "start_s": 0.0, "end_s": 1.0}])
    assert len(y) >= len(x) - int(0.02 * sr)


def test_VO07_flags_a_clip_that_ends_loud(tmp_path):
    from tms.validate.audio_rules import clean_edges
    x, _ = _clip_with_end_burst()
    wav.write(tmp_path / "v.wav", x)
    d = {"clips": [{"id": "V01", "file": "v.wav"}]}
    found = list(clean_edges(d, Context(project_dir=tmp_path, mode="tactic", artifacts={}), {"edge_s": 0.01, "max_db": -45.0}))
    assert any("ends at" in msg for _, msg in found)


def test_VO07_clip_ending_on_a_click(ap):
    d = doc(ap, "voiceover_manifest")
    c = d["clips"][0]
    x = wav.read(ap.dir / c["file"]).copy()
    x[-int(0.02 * wav.SR):] = 0.3  # the last 20 ms jump to full level, as a TTS end burst would
    rel = "media/vo/vo07_loud_end.wav"
    wav.write(ap.dir / rel, x)
    c["file"] = rel
    expect_violation("VO-07", "voiceover_manifest", d, ctx(ap))
