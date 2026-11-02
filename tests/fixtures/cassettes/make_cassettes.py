"""Builds tests/fixtures/cassettes/*.json — SYNTHETIC responses in the exact shape of the ElevenLabs API
(verified against the official SDK source). Audio is offline flite speech encoded to MP3.
Replace with recorded responses once the API is reachable from this machine (it currently returns HTTP 403 here).

Run: .venv/Scripts/python tests/fixtures/cassettes/make_cassettes.py
"""
from __future__ import annotations

import base64
import json
import tempfile
from pathlib import Path

from tms.audio import mock, wav

HERE = Path(__file__).resolve().parent
TEXT = "Watch how one full-back breaks a four-four-two."


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="tms cassette ") as td:
        tdp = Path(td)
        al = mock.tts(TEXT, tdp / "v.wav")
        wav.run([wav.ffmpeg(), "-v", "error", "-y", "-i", tdp / "v.wav", "-ar", 44100, "-b:a", "128k", tdp / "v.mp3"])
        audio = base64.b64encode((tdp / "v.mp3").read_bytes()).decode()
    doc = {"_synthetic": True, "_note": "shape from elevenlabs-python AudioWithTimestampsResponse; audio is flite speech",
           "request": {"path": "/v1/text-to-speech/{voice_id}/with-timestamps", "text": TEXT},
           "response": {"audio_base64": audio, "alignment": al, "normalized_alignment": al}}
    (HERE / "elevenlabs_tts_with_timestamps.json").write_text(json.dumps(doc), encoding="utf-8", newline="\n")
    print("wrote elevenlabs_tts_with_timestamps.json")


if __name__ == "__main__":
    main()
