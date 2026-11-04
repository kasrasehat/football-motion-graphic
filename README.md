# Tactic Motion Studio

Football tactic explainers and match previews as broadcast-style motion graphics — English voice-over, music,
word-synced captions — produced by AI coding agents (Claude Code or Codex) through gated, verified stages.

- **Tactic explainer**: `/tactic-video Explain how an inverted full-back beats a 4-4-2` (Claude) · `$tactic-video …` (Codex)
- **Match preview**: `/match-preview "Real Madrid vs Arsenal tonight"` · `$match-preview "…"` — sourced research,
  tactical analysis, a transparent Dixon-Coles prediction, data graphics and animated tactical battles.
- You approve each creative gate by typing `approve tactic|analysis|storyboard|final` (or `reject <stage>: why`).

### Several projects at once
Each chat session works on its own project, and `approve <word>` in a chat goes to that chat's project. To approve a
different one, name it: `approve storyboard --project <slug>` (also `reject storyboard --project <slug>: why`). In your own
terminal: `.venv\Scripts\tms approve <word> [--project <slug>]` and `.venv\Scripts\tms reject <word> --reason "..." [--project <slug>]`.

### Approval keys
Approvals and state records are signed with keys kept in `%USERPROFILE%\.TacticMotionStudio`. Older versions kept the key in
`%LOCALAPPDATA%`, where the Claude desktop app's processes and its Terminal panel see different files. If `tms doctor` or a
new session says keys are not migrated, run this once in the Terminal panel; no records are changed:
`.venv\Scripts\tms key migrate`. `.venv\Scripts\tms key status` shows key ids and locations, never key contents.

## Setup (Windows)
```
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
npm --prefix render ci
.venv\Scripts\tms doctor
```
`.env` (gitignored, never read by agents): `ELEVENLABS_API_KEY` (voice + music), `API_FOOTBALL_KEY` (optional —
without it research is web-only), `TMS_BROWSER_EXECUTABLE` (system Chrome; Remotion's own download is geo-blocked here),
`TMS_HTTPS_PROXY` (optional, e.g. `http://127.0.0.1:10809` if ElevenLabs/API-Football answer 403 from your network).

## First runs
1. **Dry run in Claude Code** (no cost): open a new Claude Code session in this folder and run
   `/tactic-video --dry-run Explain how an inverted full-back turns a 4-3-3 into a 3-2-5`. Answer each gate with
   `approve <word>`. Then `.venv\Scripts\tms audit -p <slug>` should print OK.
2. **Dry run in Codex**: run `codex` in this folder, accept "trust this project", open `/hooks` and trust the project
   hooks, then `$match-preview --dry-run "Real Madrid vs Arsenal tonight"`.
3. **Live run**: create a project without `--dry-run`; the voice uses ElevenLabs within the budget you approve at the
   storyboard gate (`brief.budget`).

## Verify
`.venv\Scripts\tms verify` — harness mirrors, every pytest suite (contract, harness, engine, audio, research, predict,
render, and both offline end-to-end runs), renderer type-check and tests. `.venv\Scripts\tms qa sync-test` proves
audio/video sync through the real render → mux chain.

See [AGENTS.md](AGENTS.md) (contract) and [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) (architecture).
