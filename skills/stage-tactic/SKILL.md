---
name: stage-tactic
description: Stage 2 of tactic explainers - produce and verify tactic_spec.json (both teams' shapes with engine-solved positions, principles, triggers, strengths, weaknesses, counters) and the tactic still image for the approve tactic gate. Use when tms next names the tactic stage.
---

# Stage: tactic → `artifacts/tactic_spec.json` (+ `renders/tactic_still.png`)

Author: **tactician** subagent. Reviewer: **tactics-critic** (1–3 rounds, blocking). Gate: user types `approve tactic`.
Read `skills/football-tactics/SKILL.md` first.

## Steps
1. `.venv/Scripts/tms stage begin tactic`
2. Launch the **tactician** subagent with: project slug, `projects/<slug>/artifacts/brief.json`, and (when
   `tactic.source = user`) the instruction to stay faithful to the user's description — normalize, do not reinvent.
   It returns the complete tactic_spec JSON. Write it to `projects/<slug>/artifacts/tactic_spec.json`.
3. `.venv/Scripts/tms validate tactic_spec` — errors go back to the tactician with the rule ids; warnings are listed for
   the reviewer. Repeat until 0 errors.
4. Render the snapshot: `.venv/Scripts/tms tactic still` → `projects/<slug>/renders/tactic_still.png`. Look at it.
5. QA (see `skills/verification-protocol/SKILL.md`): launch **tactics-critic** with the spec, the brief, the still image
   path and the validator warnings; save to `projects/<slug>/reviews/tactic-tactics-critic-r<N>.json`;
   `.venv/Scripts/tms qa record tactic --agent tactics-critic --review <file>`. Apply fixes until verdict `pass`.
   Re-render the still after every change.
6. **gate-verifier** subagent → must return `pass`.
7. `.venv/Scripts/tms stage submit tactic` → `awaiting_human`. Present:
   - the still image path, the title and summary;
   - each principle (name + statement + which players), triggers, the main weakness and its counter;
   - for `source: user`: anything you normalized or assumed (also logged with `tms decision add`);
   - "Type `approve tactic`, or `reject tactic: <what to change>`." Then end your turn.
