---
name: match-preview
description: Entry point to create or resume a MATCH PREVIEW video for a fixture such as "Real Madrid vs Arsenal tonight" - research both teams with sourced, fact-checked data, analyse the tactical matchup, compute a transparent prediction, storyboard data graphics plus animated tactical battles, and render with voice-over and music. Use when the user names a fixture or asks for a match preview or prediction video.
harness:
  user_only: true
---

# Match preview — orchestration

Arguments: the fixture text (e.g. `"Real Madrid vs Arsenal tonight"`), optionally `--dry-run` and a slug.

## Start
1. Resume this session's unfinished `match_preview` project if `.venv/Scripts/tms status` shows one and the user did not ask
   for a new one. If it says the session is not bound, it lists the projects: when the user clearly means one of them, run
   `.venv/Scripts/tms use <slug>`; if unclear, ask.
2. Else: `.venv/Scripts/tms init <home>-<away>-<yyyymmdd> --mode match_preview --title "<Home> v <Away>" [--dry-run]`.

## Loop (`.venv/Scripts/tms next` each time; follow the named skill + `skills/verification-protocol/SKILL.md`)
| Stage | Skill | Notes |
|---|---|---|
| intake | `stage-intake` → `stage-research` § Intake | resolve the fixture first; ask the user if ambiguous |
| research | `stage-research` | parallel **match-researcher** runs (home, away, fixture) + **fact-checker** |
| analysis | `stage-analysis` | **match-analyst**: analysis + expected shapes; engine prediction; gate `approve analysis` |
| storyboard | `stage-storyboard` | data graphics + 2–3 animated battles + prediction; gate `approve storyboard` |
| audio | `stage-audio` | |
| render | `stage-render` | gate `approve final` |
| package | `stage-package` (optional) | |

## Rules specific to previews
- Every number on screen or in the voice-over comes from the dossier/prediction (bind refs, `numbers` in narration).
- Time matters: team news goes stale (48 h). If kick-off is near and line-ups appear (about 1 h before), offer to
  refresh research — downstream stages become stale and must be redone.
- The prediction is presented as probabilities with uncertainty; never betting advice.
