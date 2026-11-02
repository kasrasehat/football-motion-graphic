# Tactic Motion Studio — agent contract

This repository turns football tactics into broadcast-style motion graphics with an English voice-over and music.
Two modes: **`tactic`** (explain a tactic given by the user or designed by you) and **`match_preview`**
(research a fixture such as "Real Madrid vs Arsenal tonight", analyse it, predict it, render it).
This file is the complete operating contract for Claude Code and Codex. Architecture: [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md).

## Rule zero — how to act
1. Run every tool through the project venv: **`.venv/Scripts/tms <command>`** (works in Bash and PowerShell).
   Never use bare `python` (it is Python 3.8 here) — use `.venv/Scripts/python.exe` when you must run Python.
2. **`.venv/Scripts/tms next`** tells you what to do. Trust it over your memory of the conversation.
3. Open the stage skill it names (`skills/stage-*/SKILL.md`, or invoke the skill) and follow it exactly.
4. Every stage follows **`skills/verification-protocol/SKILL.md`**. No stage proceeds until its output is tested and verified.

## Hard rules (enforced by the CLI; hooks are a second layer)
- **You never approve your own work.** Human-gated stages (`tactic`, `analysis`, `storyboard`, `final`, `package`) complete
  only when the **user** types `approve <word>` in chat (recorded by the UserPromptSubmit hook) or runs
  `.venv/Scripts/tms approve <word>` in their own terminal. There is no flag that approves. After
  `tms stage submit` reports `awaiting_human`: present the summary and preview files, ask the user to type
  `approve <word>` (or `reject <word>: <reason>`), then **end your turn**.
- **Never edit** `projects/*/state/**`, `projects/*/history/**`, `projects/*/build/**`, `projects/*/project.json`,
  `.env*`, or the generated mirrors (`.claude/skills|agents`, `.agents/skills`, `.codex/agents`). Edit the canonical
  source (`skills/`, `agents/`) and run `.venv/Scripts/tms sync-harness`.
- **Never read or print `.env`.** The CLI loads keys itself. Never call ElevenLabs or API-Football directly
  (curl etc.) — only through `tms` commands, which cache, cap spend and log cost.
- **You write intent, the engine writes numbers.** Never type coordinates for players beyond what a skill allows
  (`start.overrides`, `to.pitch` targets), never type statistics into graphics or narration — bind them to dossier
  fact keys / prediction paths. The engine solves motion, timing and values, and its validators check them.
- **Authors never review their own work.** QA is done by the reviewer subagents listed for the stage in
  `pipeline.yaml`; record each review with `tms qa record` (it binds the verdict to the exact artifact hashes).
- **Research never fabricates.** Every fact has a source (API field or URL + quote + retrieval time). Unverifiable
  means unused. Predictions are labelled as analysis, never betting advice.
- **Log decisions** the user makes (and any fallback you take) with `tms decision add`.
- **Paid live runs** (non-dry-run projects) spend only within the budget the user approved with the storyboard.
  Ask before anything beyond it.

## Stage loop (per stage)
```
.venv/Scripts/tms stage begin <stage>
  -> author subagent produces the artifact(s) (stage skill says which and how)
  -> .venv/Scripts/tms validate <artifact...>          # fix every error (rule ids explain why)
  -> reviewer subagents -> save JSON to projects/<slug>/reviews/<stage>-<agent>-r<N>.json
  -> .venv/Scripts/tms qa record <stage> --agent <agent> --review <file>     # repeat until verdict pass
  -> gate-verifier subagent (independent check of the evidence)
  -> .venv/Scripts/tms stage submit <stage>            # exit 2 = refused, read why
  -> if awaiting_human: present, ask for `approve <word>`, END TURN
```
Exit codes: `0` ok · `1` error · `2` gate violation (refused — read the message, fix the cause, never work around it).

## Subagents and skills in each harness
- **Claude Code**: subagents in `.claude/agents/` — launch with the Agent tool (`subagent_type` = agent name).
  Skills in `.claude/skills/` — the entry skills are `/tactic-video` and `/match-preview`.
- **Codex**: custom agents in `.codex/agents/` — spawn them with `agent_type` = agent name (e.g. ask to
  "spawn the tactics-critic agent"). Skills in `.agents/skills/` — invoke with `$tactic-video`, `$match-preview`.
- Subagents return JSON in their final message; **only the orchestrating agent writes files**.
- Run independent reviewers/researchers in parallel when the harness allows it; sequentially otherwise.

<!-- BEGIN GENERATED:index -->
**Skills** (`skills/` canonical → `.claude/skills/`, `.agents/skills/`)

- `api-football` — How this project uses the API-Football v3 service (fixtures, standings, team statistics, form, head-to-head, injuries, line-ups, odds) through tms commands with caching and a per-project call budget, and how to fall back to web-only research.
- `choreo-dsl` — Exact reference for scene_plan.json, the storyboard language - pitch scenes made of actions (move, carry, pass, press, mark, tackle, intercept, shot, duel), time references, holds, overlays and camera keys, plus data-bound graphic scenes - with engine semantics, validator rules and proven patterns.
- `elevenlabs-audio` — How this project uses ElevenLabs - text-to-speech with character timestamps, Music, and speech-to-text QA - including voice settings, caching, budgets, proxy routing, failure handling and the offline mock.
- `ffmpeg-av` — Audio/video engineering conventions of this project - the 30 fps / 48 kHz clock, sample-exact voice placement, envelope ducking, two-pass loudnorm targets, muxing without re-encoding, probes, and the A/V sync calibration test.
- `football-tactics` — Football tactics domain reference for this project - pitch coordinate conventions, phases of play, formation templates, realistic distances and speeds, tactical vocabulary, and how to write precise, observable principles.
- `match-data-sources` — Rules for researching football facts for match previews - which sources to trust (tiers), how to write a sourced claim with quote and retrieval time, fact keys, freshness, corroboration of key facts, conflicts, paywalls, and never fabricating.
- `match-preview` — Entry point to create or resume a MATCH PREVIEW video for a fixture such as "Real Madrid vs Arsenal tonight" - research both teams with sourced, fact-checked data, analyse the tactical matchup, compute a transparent prediction, storyboard data graphics plus animated tactical battles, and render with voice-over and music.
- `narration-craft` — How to write the English voice-over script (narration_script.json) for tactics videos - broadcast-analyst tone, a hook in the first seconds, one line per scene sized to the scene, words anchored to on-screen events, pronunciation respellings, and number binding for match previews.
- `prediction-model` — How the match_preview prediction (build/prediction.json) is computed, adjusted, validated and explained - Dixon-Coles goals model fed by dossier facts, optional market-odds blend, bounded analyst adjustments, rules PR-01 to PR-07, backtesting, and how to talk about uncertainty to viewers.
- `remotion-renderer` — How the Remotion renderer in render/ turns render_props.json into broadcast-style frames - the props-to-component map, projection, overlays, captions, cards and graphics registry, how to add a component, overlay kind or graphic template, the determinism rules, and the verify / studio / still-preview commands.
- `stage-analysis` — Match-preview analysis - the match-analyst writes match_analysis.json (cited assertions, key player battles, tactical battles, bounded prediction adjustments) and the expected tactic_spec for both teams from the predicted line-ups; the engine computes the prediction; tactics-critic and fact-checker review; hand off for approve analysis.
- `stage-audio` — Audio stage - generate the voice-over (ElevenLabs, or the offline mock in dry runs), solve the master timeline that anchors spoken words to on-screen events, and fit the music bed, all validated by VO/TL/MU rules.
- `stage-intake` — Stage 1 (intake) - turn the user's request into a validated brief.json (mode, duration, aspect, teams and colours, focus team, voice, music, budget, and the tactic text or match fixture).
- `stage-package` — Optional publishing stage - write package.json (title, description, chapters, tags, thumbnail frame) for the approved final video and export the thumbnail.
- `stage-render` — Render stage - build render_props from the approved storyboard and audio timeline, render the final 1080p video with Remotion, mix and mux the audio, write captions.srt, measure the FQ quality checks, run visual QA on sampled frames, and hand off for approve final.
- `stage-research` — Match-preview research - resolve the fixture during intake, pull API-Football data when a key exists, run parallel web research for tactics, xG, team news and predicted line-ups as sourced claims, merge everything into the match dossier and get it fact-checked.
- `stage-storyboard` — Storyboard stage - author scene_plan.json and narration_script.json together, compile them into the engine choreography, render the silent animatic and contact sheet, run the tactics, script, visual (and fact) reviews, and hand off for approve storyboard.
- `stage-tactic` — Stage 2 of tactic explainers - produce and verify tactic_spec.json (both teams' shapes with engine-solved positions, principles, triggers, strengths, weaknesses, counters) and the tactic still image for the approve tactic gate.
- `tactic-video` — Entry point to create or resume a football TACTIC EXPLAINER motion-graphic video (top-down animated pitch, English voice-over, music) from a tactic the user describes or a topic for you to design.
- `verification-protocol` — The gate procedure every pipeline stage must follow before it may proceed - validate, independent QA review recorded against artifact hashes, gate-verifier check, submit, and the human approval hand-off.

**Subagents** (`agents/` canonical → `.claude/agents/`, `.codex/agents/`)

- `audio-engineer` — Runs and diagnoses the audio stage - voice-over generation, timeline solving and music fitting.
- `fact-checker` — Independent fact-checker for match previews.
- `gate-verifier` — Independent verifier run before every stage submit and every milestone close.
- `match-analyst` — Author of match_analysis.json and the match-mode tactic_spec - reads the sourced dossier, identifies the decisive tactical and player battles, models both teams' expected shapes from the predicted line-ups, and proposes only bounded, evidence-backed prediction adjustments.
- `match-researcher` — Web researcher for one scope of a match preview (home team, away team, or the fixture itself).
- `motion-designer` — Development-time owner of the Remotion renderer (render/) - components, overlays, captions, cards, graphic templates and themes.
- `script-editor` — Independent reviewer of narration_script.json - accuracy against the tactic or analysis, hook, clarity for the brief's audience, pacing against scene lengths, anchors on the right words, pronunciation and number binding.
- `storyboarder` — Author of the storyboard - writes scene_plan.json (pitch scenes in the choreography language plus data-bound graphic scenes) and narration_script.json together so every spoken idea is shown on screen at the moment it is said.
- `tactician` — Author of tactic_spec.json.
- `tactics-critic` — Independent football-realism reviewer for tactic_spec, match_analysis and storyboards.
- `visual-qa` — Independent visual reviewer of rendered output - contact sheets, stills and sampled final frames.
<!-- END GENERATED:index -->

## Changing the system itself (development rules)
- Plan → implement → **test → verify → only then proceed**. `.venv/Scripts/tms verify` must be green before a
  milestone or change is called done. The Stop hook runs the fast suite after code edits and blocks on failure.
- Every validator rule lives in `config/rules.yaml` with an implementation and a negative test
  (`tests/**/test_rules_*.py`). Every artifact schema has a fixture in `tests/fixtures/artifacts/`.
- Edit skills/agents only in `skills/` and `agents/`, then `.venv/Scripts/tms sync-harness`. Keep this file < 24 KiB.
- Renderer changes: `npm --prefix render run verify`. Remotion components are pure functions of (frame, props):
  no `Math.random`, `Date`, timers or CSS animations.
