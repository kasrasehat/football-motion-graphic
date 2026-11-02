"""ElevenLabs REST client (TTS with timestamps, Music, Speech-to-Text, account info).

Shapes verified against the official SDK source (elevenlabs-python, Fern-generated from their API definition):
  POST /v1/text-to-speech/{voice_id}/with-timestamps  json{text, model_id, voice_settings, seed, previous_text,
       next_text, apply_text_normalization}  -> {audio_base64, alignment{characters, character_start_times_seconds,
       character_end_times_seconds}, normalized_alignment}
  POST /v1/music  json{prompt, music_length_ms (3000..600000), model_id?, seed?, force_instrumental} -> audio bytes
  POST /v1/speech-to-text  multipart{model_id, file, timestamps_granularity} -> {text, words[{text,start,end,type}]}
Every billable request is cached by a hash of its body, so re-runs never pay twice. The key is never logged.
"""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import httpx

from tms import envfile, jsonio, paths

BASE = "https://api.elevenlabs.io"
RETRY_STATUS = {429, 500, 502, 503, 504}


class ElevenLabsError(Exception):
    pass


def request_hash(kind: str, body: dict) -> str:
    return jsonio.sha256_bytes(jsonio.canonical({"kind": kind, **body}))


class Client:
    def __init__(self, key: str | None = None, cache_dir: Path | None = None, timeout: float = 180.0):
        self.key = key if key is not None else envfile.get("ELEVENLABS_API_KEY").strip()
        self.cache = cache_dir or paths.scratch_dir() / "cache" / "elevenlabs"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

    # ------------------------------------------------------------------ http
    def _req(self, method: str, path: str, **kw) -> httpx.Response:
        if not self.key:
            raise ElevenLabsError("ELEVENLABS_API_KEY is not set (.env) — use a dry-run project for mock audio")
        headers = {"xi-api-key": self.key, **kw.pop("headers", {})}
        proxy = envfile.get("TMS_HTTPS_PROXY").strip() or None  # opt-in route (e.g. a local VPN client)
        delay = 1.0
        for attempt in range(4):
            try:
                r = httpx.request(method, BASE + path, headers=headers, timeout=self.timeout, proxy=proxy, **kw)
            except httpx.HTTPError as e:
                if attempt == 3:
                    raise ElevenLabsError(f"network error calling ElevenLabs {path}: {type(e).__name__}: {e}") from e
                time.sleep(delay)
                delay *= 2
                continue
            if r.status_code in RETRY_STATUS and attempt < 3:
                time.sleep(float(r.headers.get("retry-after", delay)))
                delay *= 2
                continue
            if r.status_code >= 400:
                detail = r.text[:400].replace(self.key, "***") if self.key else r.text[:400]
                raise ElevenLabsError(f"ElevenLabs {path} -> HTTP {r.status_code}: {detail}")
            return r
        raise ElevenLabsError(f"ElevenLabs {path}: retries exhausted")

    # ------------------------------------------------------------------ account
    def subscription(self) -> dict:
        return self._req("GET", "/v1/user/subscription").json()

    def voices(self) -> list[dict]:
        return self._req("GET", "/v2/voices", params={"page_size": 100}).json().get("voices", [])

    # ------------------------------------------------------------------ TTS
    def tts(self, text: str, voice_id: str, model_id: str, settings: dict, seed: int,
            previous_text: str | None = None, next_text: str | None = None) -> tuple[bytes, dict, str, bool]:
        """Returns (mp3 bytes, alignment, request_hash, cached)."""
        body = {"text": text, "model_id": model_id, "voice_settings": settings, "seed": seed,
                "previous_text": previous_text, "next_text": next_text, "apply_text_normalization": "auto"}
        h = request_hash(f"tts:{voice_id}", body)
        f = self.cache / f"tts-{h}.json"
        if f.is_file():
            d = jsonio.read_json(f)
            return base64.b64decode(d["audio_base64"]), d["alignment"], h, True
        r = self._req("POST", f"/v1/text-to-speech/{voice_id}/with-timestamps", params={"output_format": "mp3_44100_128"},
                      json={k: v for k, v in body.items() if v is not None})
        d = r.json()
        if not d.get("alignment"):
            raise ElevenLabsError("TTS response has no alignment")
        jsonio.write_json(f, {"audio_base64": d["audio_base64"], "alignment": d["alignment"]}, compact=True)
        return base64.b64decode(d["audio_base64"]), d["alignment"], h, False

    # ------------------------------------------------------------------ music
    def music(self, prompt: str, length_ms: int, seed: int | None = None) -> tuple[bytes, str, bool]:
        length_ms = max(3000, min(int(length_ms), 600000))
        body = {"prompt": prompt, "music_length_ms": length_ms, "force_instrumental": True}
        if seed is not None:
            body["seed"] = seed
        h = request_hash("music", body)
        f = self.cache / f"music-{h}.mp3"
        if f.is_file():
            return f.read_bytes(), h, True
        r = self._req("POST", "/v1/music", params={"output_format": "mp3_44100_128"}, json=body)
        f.write_bytes(r.content)
        return r.content, h, False

    # ------------------------------------------------------------------ STT (final QA)
    def stt(self, audio: Path) -> dict:
        h = jsonio.sha256_file(audio)
        f = self.cache / f"stt-{h}.json"
        if f.is_file():
            return jsonio.read_json(f)
        with open(audio, "rb") as fh:
            r = self._req("POST", "/v1/speech-to-text", data={"model_id": "scribe_v1", "timestamps_granularity": "word",
                                                               "language_code": "en"}, files={"file": (audio.name, fh)})
        d = r.json()
        jsonio.write_json(f, d, compact=True)
        return d


def alignment_to_json(al: dict) -> str:
    return json.dumps(al)
