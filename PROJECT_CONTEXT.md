# PROJECT_CONTEXT — architecture map

One-page orientation. The binding rules live in [`AGENTS.md`](AGENTS.md).

## Layers
```
┌─ Harness entry ─────────────────────────────────────────────────────────────────────┐
│ AGENTS.md (contract, read natively by Codex) · CLAUDE.md (@AGENTS.md + Claude notes)   │
├─ Intelligence (markdown, harness-agnostic, canonical) ─────────────────────────────────┤
│ skills/<name>/SKILL.md  → .claude/skills · .agents/skills      (tms sync-harness)      │
│ agents/<name>.md        → .claude/agents · .codex/agents/*.toml                         │
├─ Enforcement ──────────────────────────────────────────────────────────────────────────┤
│ tms CLI gates (derived status, QA bound to hashes, HMAC approvals, staleness)           │
│ hooks/dispatch.py ← .claude/settings.json · .codex/hooks.json  (second layer)           │
├─ Engine (Python, engine/tms) ──────────────────────────────────────────────────────────┤
│ state · validate (rules.yaml) · tactic · choreo · research · predict · audio ·          │
│ timeline · render (props) · qa · harness · doctor                                       │
├─ Renderer (render/, Remotion 4, TypeScript) — pure function of (frame, render_props) ──┤
├─ Contracts ────────────────────────────────────────────────────────────────────────────┤
│ pipeline.yaml · schemas/ (JSON Schema 2020-12) · config/*.yaml                          │
└─ Runtime state (gitignored) projects/<slug>/: artifacts/ build/ media/ state/ history/  │
   reviews/ renders/                                                                       ┘
```

## Pipelines
<!-- BEGIN GENERATED:stages -->
**Mode `tactic`** — Tactic explainer (45–120 s, default 75 s)

| # | Stage | Gate | Produces | Inputs | QA reviewers | Skill |
|---|---|---|---|---|---|---|
| 1 | `intake` | auto | brief | – | – | `skills/stage-intake/SKILL.md` |
| 2 | `tactic` | human: `approve tactic` | tactic_spec | brief | tactics-critic (1–3) | `skills/stage-tactic/SKILL.md` |
| 3 | `storyboard` | human: `approve storyboard` | scene_plan, narration_script, choreography | brief, tactic_spec | tactics-critic (1–4), script-editor (1–4), visual-qa (1–4) | `skills/stage-storyboard/SKILL.md` |
| 4 | `audio` | auto | voiceover_manifest, timeline, music_manifest | brief, scene_plan, narration_script, choreography | – | `skills/stage-audio/SKILL.md` |
| 5 | `render` | human: `approve final` | render_props, render_report | brief, choreography, timeline, voiceover_manifest, music_manifest | visual-qa (1–2) | `skills/stage-render/SKILL.md` |
| 6 | `package` | human: `approve package` (optional) | package | brief, narration_script, render_report | – | `skills/stage-package/SKILL.md` |

**Mode `match_preview`** — Match preview (analysis + prediction) (60–180 s, default 120 s)

| # | Stage | Gate | Produces | Inputs | QA reviewers | Skill |
|---|---|---|---|---|---|---|
| 1 | `intake` | auto | brief | – | – | `skills/stage-intake/SKILL.md` |
| 2 | `research` | auto | web_claims, match_dossier | brief | fact-checker (1–2) | `skills/stage-research/SKILL.md` |
| 3 | `analysis` | human: `approve analysis` | match_analysis, tactic_spec, prediction | brief, match_dossier | tactics-critic (1–3), fact-checker (1–2) | `skills/stage-analysis/SKILL.md` |
| 4 | `storyboard` | human: `approve storyboard` | scene_plan, narration_script, choreography | brief, match_dossier, match_analysis, tactic_spec, prediction | tactics-critic (1–4), script-editor (1–4), visual-qa (1–4), fact-checker (1–2) | `skills/stage-storyboard/SKILL.md` |
| 5 | `audio` | auto | voiceover_manifest, timeline, music_manifest | brief, scene_plan, narration_script, choreography | – | `skills/stage-audio/SKILL.md` |
| 6 | `render` | human: `approve final` | render_props, render_report | brief, choreography, timeline, voiceover_manifest, music_manifest | visual-qa (1–2) | `skills/stage-render/SKILL.md` |
| 7 | `package` | human: `approve package` (optional) | package | brief, narration_script, render_report | – | `skills/stage-package/SKILL.md` |
<!-- END GENERATED:stages -->

## Conventions
- **Clock**: 30 fps, 48 kHz audio (1600 samples per frame). All timing is integer frames from `build/timeline.json`.
- **Pitch**: metres, 105 × 68, origin top-left, +x right, +y down, **home (H) always attacks +x**.
  `tactic_spec` positions are *team-normalized* (each team attacks +x); away → absolute is a 180° rotation
  `(105 − x, 68 − y)`. Portrait (9:16) output is only a different projection.
- **IDs**: players `H1–H11` / `A1–A11`; scenes `S01…`; events `E01…` (scene-local); overlays `N01…`;
  holds `h1…`; reveals `R1…`; principles `P1…`; web claims `W-001…`; dossier claims `C-001…`;
  QA records `Q-001…`; approvals `A-001…`; decisions `d-001…`.
- **Project selection**: inside a harness session a command without `--project` means the project bound to that session
  (`.tms/sessions/<session id>`, written by `tms init` / `tms use`). The session id comes from the hook payload and, for
  shell tools, the environment (`project.SESSION_VARS`). Outside a session (your terminal) it means the pointer in
  `.tms/active_project`, which sessions never read or move. Chat approvals use the session's project or the one named
  in the message, and an unbound session with several projects is refused rather than guessed.
- **Signing keys**: in the home directory, not AppData, because desktop-app processes get a private overlay over AppData
  (`state/approvals.py` explains). A record is valid if a key in the ring verifies it: the signing key plus verify-only
  keys under `trusted/`, added only by the user's `tms key migrate`. A record no ring key verifies never counts and is
  flagged by `tms audit`; there is no waiver.
- **Artifacts**: agent-authored in `artifacts/`, engine-built in `build/` (never edited by hand). Every artifact
  carries `version` and `project_id`; engine artifacts carry `inputs` (sha256 provenance).
- **Facts**: `match_dossier.facts` keys like `H.goals_for_avg`, `A.injuries`, `fixture.kickoff_utc` are the only
  source of numbers for graphics and narration.
- **Windows host**: the repo path contains spaces — subprocesses always use argv lists; never `shell=True`.
