---
name: verification-protocol
description: The gate procedure every pipeline stage must follow before it may proceed - validate, independent QA review recorded against artifact hashes, gate-verifier check, submit, and the human approval hand-off. Use whenever you begin, review, submit or present any stage, or when a tms command exits with code 2.
---

# Verification protocol

A stage is **done** only when `.venv/Scripts/tms status` says `completed`. You cannot declare it; the CLI derives it from
validators, QA records bound to artifact hashes, and (for gated stages) a signed approval from the user.

## 1. Begin
```
.venv/Scripts/tms next                 # what to do now (source of truth)
.venv/Scripts/tms stage begin <stage>  # exit 2 => an upstream stage is not completed or is stale: go fix that first
```

## 2. Produce, then validate until clean
Author the stage's artifacts as its stage skill describes (usually by launching the author subagent and writing the JSON
it returns to `projects/<slug>/artifacts/<name>.json`). The PostToolUse hook validates each artifact write and shows
rule ids. Then:
```
.venv/Scripts/tms validate <artifact> [<artifact> ...]
```
- `SCHEMA` errors: the JSON shape is wrong — compare with `schemas/artifacts/<name>.schema.json` and the fixture in
  `tests/fixtures/artifacts/`.
- `XX-NN` errors: a domain rule (see `config/rules.yaml` for the exact threshold). Fix the cause; never weaken a rule.
- Warnings do not block, but list them for the reviewers and at the human gate.

## 3. Independent QA (authors never review their own work)
For each reviewer listed for the stage in `pipeline.yaml` (`tms next` and the stage skill name them):
1. Launch the reviewer subagent with: the stage name, the artifact paths, the upstream artifact paths, the
   `review_focus` list of the stage, and the current validator warnings. Launch independent reviewers in parallel.
2. Save its JSON verbatim to `projects/<slug>/reviews/<stage>-<agent>-r<N>.json` (N = round number).
3. Record it — this binds the verdict to the exact artifact hashes:
   ```
   .venv/Scripts/tms qa record <stage> --agent <agent> --review projects/<slug>/reviews/<stage>-<agent>-r<N>.json
   ```
4. Verdict `fix_and_rereview` → apply every `critical`/`major` proposed fix (or log with `tms decision add` why not),
   re-validate, and run the next round. Any edit after a passing review invalidates it — the reviewer must pass the
   final version.
5. If a reviewer hits `max_rounds` (exit 2), stop and escalate to the user with the open findings. Do not loop.

## 4. Gate-verifier
Launch the `gate-verifier` subagent with the project slug and stage. It re-runs validation, checks QA binding and
`tms audit`, and returns `{"verdict": "pass"|"fail", ...}`. On `fail`, fix what it lists and repeat from step 2.

## 5. Submit
```
.venv/Scripts/tms stage submit <stage>
```
- Exit 2: read every listed problem, fix, repeat. Never try to get around it.
- `completed`: continue with `.venv/Scripts/tms next`.
- `awaiting_human`: present to the user —
  1. a short summary of what was produced and the key decisions,
  2. validator warnings and any reviewer findings you chose not to apply (with reasons),
  3. paths to preview files (stills, animatic, contact sheet, final video),
  4. the exact words to type: `approve <word>` or `reject <word>: <what to change>`.
  Then **end your turn**. Never type or simulate the approval; never run `tms approve` yourself.

## 6. After the user answers
The UserPromptSubmit hook records it and tells you `APPROVAL RECORDED` or `REJECTION RECORDED` (with the feedback).
On rejection the stage is back `in_progress`: address the feedback, re-validate, re-review, resubmit.

## Never
- Edit `state/`, `history/`, `build/`, `project.json` or `.env`, or run `tms approve`.
- Mark something done because it "looks fine". Evidence is the CLI status, nothing else.
- Skip a reviewer, reuse an old review for a changed artifact, or summarise a reviewer's output instead of recording it.
