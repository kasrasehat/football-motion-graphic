---
name: stage-analysis
description: Match-preview analysis - the match-analyst writes match_analysis.json (cited assertions, key player battles, tactical battles, bounded prediction adjustments) and the expected tactic_spec for both teams from the predicted line-ups; the engine computes the prediction; tactics-critic and fact-checker review; hand off for approve analysis. Use when tms next names the analysis stage.
---

# Stage: analysis → `artifacts/match_analysis.json`, `artifacts/tactic_spec.json`, engine `build/prediction.json`

Author: **match-analyst**. Reviewers: **tactics-critic**, **fact-checker**. Gate: `approve analysis`.
Read `skills/football-tactics/SKILL.md` and `skills/prediction-model/SKILL.md`.

## Steps
1. `.venv/Scripts/tms stage begin analysis`
2. Launch **match-analyst** with the brief, dossier and web_claims. It returns `{"match_analysis": {...}, "tactic_spec": {...}}`:
   - tactic_spec: `focus_team: "both"`, each team's expected shape (scaffold with `.venv/Scripts/tms tactic scaffold`),
     real names and shirt numbers from `H/A.predicted_xi`, one principle per tactical battle (2–3 total).
   - match_analysis: every assertion cites dossier fact keys or claim ids; `prediction_adjustments` only for evidence the
     model cannot see (injuries to key players, rotation, motivation), each |delta| ≤ 10 pp with refs.
   Write both to `artifacts/`.
3. `.venv/Scripts/tms validate match_analysis tactic_spec`, then `.venv/Scripts/tms predict build` → `build/prediction.json`
   (PR rules). If facts are missing for the model, research more (reopen research) — never invent numbers.
4. `.venv/Scripts/tms tactic still` for the expected shapes image.
5. QA: **tactics-critic** (matchup realism, battles demonstrable) and **fact-checker** (every assertion supported by
   its refs) → record both with `.venv/Scripts/tms qa record analysis --agent <agent> --review <file>`.
6. **gate-verifier**, `.venv/Scripts/tms stage submit analysis`, then present: headline and angle, key battles, the
   prediction (probabilities, most likely score, confidence, adjustments with reasons), single-source facts and
   uncertainties, and the still. "Type `approve analysis`, or `reject analysis: <what to change>`." End your turn.
