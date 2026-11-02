---
name: elevenlabs-audio
description: How this project uses ElevenLabs - text-to-speech with character timestamps, Music, and speech-to-text QA - including voice settings, caching, budgets, proxy routing, failure handling and the offline mock. Use when choosing a voice, debugging voice-over or music generation, or planning a paid live run.
---

# ElevenLabs in Tactic Motion Studio

All calls go through `engine/tms/audio/elevenlabs.py` (never curl; hooks block it). Key: `ELEVENLABS_API_KEY` in `.env`
(the CLI reads it; never print or open `.env`).

## Endpoints used (shapes verified from the official SDK source)
| purpose | call | notes |
|---|---|---|
| narration | `POST /v1/text-to-speech/{voice_id}/with-timestamps` | returns `audio_base64` + `alignment` (characters, start/end seconds) → word timings |
| music | `POST /v1/music` | `prompt`, `music_length_ms` 3 000–600 000, `force_instrumental: true`, `seed` |
| final QA | `POST /v1/speech-to-text` | `model_id: scribe_v1`, word timestamps → WER + timing check |
| account | `GET /v1/user/subscription`, `GET /v2/voices` | free; plan tier and remaining characters |

## Voice settings (`brief.voice`)
`model_id` `eleven_multilingual_v2` (default), `stability` 0.5–0.6 (analysis tone), `similarity_boost` 0.8, `style`
0.1–0.25, `speed` 0.95–1.05, `seed` fixed for repeatability. Neighbouring lines are sent as `previous_text` /
`next_text` for natural continuity. Respellings come from `narration_script.pronunciations` (single tokens).

## Cost control
- Every billable request is cached by a hash of its exact body (`.tms/cache/elevenlabs/`): rebuilding the same
  narration costs 0 characters. Changing one line re-bills that line and its neighbours (context changed).
- `brief.budget.tts_chars_max` / `music_s_max` are hard caps (exit 2 before calling). The user approves them with
  the storyboard; raising them needs the user.

## Network
From some regions the API answers HTTP 403. If the user runs a VPN/proxy client, they can set
`TMS_HTTPS_PROXY=http://127.0.0.1:<port>` in `.env`; the client then routes through it. Never enable a proxy for them.

## Dry runs
Projects created with `--dry-run` use the offline flite voice (robotic, timing-realistic) and a synthesized bed;
nothing is billed. Live projects refuse mock audio unless the user decides otherwise (logged decision).
