---
name: tactic-video
description: Entry point to create or resume a football TACTIC EXPLAINER motion-graphic video (top-down animated pitch, English voice-over, music) from a tactic the user describes or a topic for you to design. Use when the user asks to explain, animate or visualise a tactic, formation or pattern of play.
harness:
  user_only: true
---

# Tactic explainer — orchestration

Arguments: the user's tactic description or topic, optionally `--dry-run` (mock voice/music, zero cost) and a slug.

## Start
1. If `.venv/Scripts/tms status` shows an active project in mode `tactic` that is not finished and the user did not ask
   for a new video, **resume** it: go to the loop below.
2. Otherwise create a project. Pick a short slug from the topic (lowercase, hyphens), then:
   ```
   .venv/Scripts/tms init <slug> --mode tactic --title "<working title>" [--dry-run]
   ```
   Use `--dry-run` when the user asked for it or when no ElevenLabs key is present (SessionStart tells you which keys exist).

## Loop
Repeat until `.venv/Scripts/tms next` says all required stages are completed:
1. `.venv/Scripts/tms next` → stage + status + the skill to follow.
2. Follow that stage skill (`skills/stage-<stage>/SKILL.md`) and `skills/verification-protocol/SKILL.md`.
3. At every `awaiting_human` gate: present and **end your turn**.

| Stage | Skill | You hand the user |
|---|---|---|
| intake | `stage-intake` | (no gate) |
| tactic | `stage-tactic` | tactic still image + principles → `approve tactic` |
| storyboard | `stage-storyboard` | animatic MP4 + contact sheet + script → `approve storyboard` |
| audio | `stage-audio` | (no gate) |
| render | `stage-render` | final MP4 + QA report → `approve final` |
| package (optional) | `stage-package` | title/description/chapters → `approve package` |

## Finish
Report the final video path (`projects/<slug>/renders/final.mp4`), duration, and `tms audit` result.
