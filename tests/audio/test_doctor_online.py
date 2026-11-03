"""`tms doctor --online/--probe`: offline tests with a fake ElevenLabs client, plus a check of the recorded real
response (skipped while the cassette is still synthetic)."""
from __future__ import annotations

import base64
import json
import tempfile
from pathlib import Path

import pytest

from tms import doctor
from tms.audio import mock, wav
from tms.audio.elevenlabs import ElevenLabsError
from tms.audio.voiceover import _trim, words_from_alignment
from tests.helpers import FIX

pytestmark = pytest.mark.fast


class FakeEL:
    key = "test-key"

    def __init__(self, sub_error=None, music_error=None):
        self.sub_error, self.music_error, self.calls = sub_error, music_error, []

    def subscription(self):
        if self.sub_error:
            raise ElevenLabsError(self.sub_error)
        return {"tier": "payg", "character_count": 100, "character_limit": 10000, "status": "active"}

    def tts(self, text, voice, model, settings, seed, prev=None, nxt=None):
        self.calls.append("tts")
        with tempfile.TemporaryDirectory(prefix="tms fake ") as td:
            al = mock.tts(text, Path(td) / "v.wav")
            wav.run([wav.ffmpeg(), "-v", "error", "-y", "-i", Path(td) / "v.wav", "-ar", 44100, "-b:a", "128k", Path(td) / "v.mp3"])
            return (Path(td) / "v.mp3").read_bytes(), al, "h" * 64, False

    def music(self, prompt, length_ms, seed=None):
        self.calls.append("music")
        if self.music_error:
            raise ElevenLabsError(self.music_error)
        with tempfile.TemporaryDirectory(prefix="tms fake ") as td:
            mock.music(length_ms / 1000, Path(td) / "m.wav")
            wav.run([wav.ffmpeg(), "-v", "error", "-y", "-i", Path(td) / "m.wav", Path(td) / "m.mp3"])
            return (Path(td) / "m.mp3").read_bytes(), "m" * 64, False


def test_probe_tts_parses_and_records(tmp_path):
    r = doctor.Report()
    out = tmp_path / "cassette.json"
    res = doctor.probe_tts(r, FakeEL(), record_to=out)
    check = next(c for c in r.checks if c["check"] == "probe-tts")
    assert check["ok"], check
    assert len(res["words"]) == len(doctor.PROBE_TEXT.split())
    cas = json.loads(out.read_text(encoding="utf-8"))
    assert cas["_synthetic"] is False and cas["request"]["text"] == doctor.PROBE_TEXT
    assert cas["response"]["alignment"]["characters"]


def test_music_refusal_is_a_warning_not_a_failure():
    r = doctor.Report()
    assert doctor.probe_music(r, FakeEL(music_error="ElevenLabs /v1/music -> HTTP 402: payment required")) is False
    assert not r.failed and r.checks[-1]["level"] == "warn"


def test_music_bad_request_is_a_failure_not_a_plan_warning():
    r = doctor.Report()
    doctor.probe_music(r, FakeEL(music_error="ElevenLabs /v1/music -> HTTP 422: `seed` cannot be used with `prompt`."))
    assert r.failed and r.checks[-1]["level"] == "error"


def test_music_request_never_sends_seed_with_prompt(monkeypatch, tmp_path):
    import httpx
    from tms.audio.elevenlabs import Client
    sent = {}

    def fake(method, url, **kw):
        sent.update(kw["json"])
        return httpx.Response(200, content=b"ID3", request=httpx.Request(method, url))
    monkeypatch.setattr(httpx, "request", fake)
    Client(key="k", cache_dir=tmp_path).music("bed", 10000, seed=7)
    assert "prompt" in sent and "seed" not in sent


def test_music_probe_measures_the_clip():
    r = doctor.Report()
    assert doctor.probe_music(r, FakeEL()) is True
    assert r.checks[-1]["ok"], r.checks[-1]


def test_unreachable_api_fails_with_vpn_hint(monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY", "")
    r = doctor.Report()
    assert doctor.check_online(r, client=FakeEL(sub_error="ElevenLabs /v1/user/subscription -> HTTP 403: Forbidden")) is None
    el = next(c for c in r.checks if c["check"] == "elevenlabs")
    assert el["level"] == "error" and "VPN" in el["detail"]


def test_recorded_real_response_goes_through_the_voice_pipeline(tmp_path):
    """Once `--record-cassette` has run, prove our parsing works on genuine ElevenLabs output."""
    cas = json.loads((FIX / "cassettes" / "elevenlabs_tts_with_timestamps.json").read_text(encoding="utf-8"))
    if cas.get("_synthetic", True):
        pytest.skip("cassette is still synthetic — run `tms doctor --online --probe --record-cassette` with ElevenLabs reachable")
    text, al = cas["request"]["text"], cas["response"]["alignment"]
    words = words_from_alignment(text, text, al)
    assert [w["display"] for w in words] == text.split()
    (tmp_path / "v.mp3").write_bytes(base64.b64decode(cas["response"]["audio_base64"]))
    wav.to_wav48(tmp_path / "v.mp3", tmp_path / "v.wav")
    y, ws, corr = _trim(wav.read(tmp_path / "v.wav"), words)
    assert abs(corr) <= 0.12
    assert all(a["start_s"] <= b["start_s"] for a, b in zip(ws, ws[1:]))
    assert ws[-1]["end_s"] <= len(y) / wav.SR + 0.05
