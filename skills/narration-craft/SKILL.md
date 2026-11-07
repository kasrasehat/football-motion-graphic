---
name: narration-craft
description: How to write the English voice-over script (narration_script.json) for tactics videos - broadcast-analyst tone, a hook in the first seconds, one line per scene sized to the scene, words anchored to on-screen events, pronunciation respellings, and number binding for match previews. Use when writing or reviewing narration.
---

# Narration craft (`artifacts/narration_script.json`)

The voice-over **is** the explanation, and its words are the on-screen captions verbatim. Write for the ear.
Schema: `schemas/artifacts/narration_script.schema.json`; rules `NS-xx` in `config/rules.d/narration.yaml`.

## Shape
- Exactly **one line per scene**, same order as scene_plan (`NS-01`). `silent: true` (empty text) for at most two
  short scenes (e.g. a title graphic).
- `title_card` (≤ 40 / ≤ 60 chars) and `end_card` (≤ 60) are on-screen text, not spoken.

## Timing (the engine measures the real voice later, so estimate honestly)
- Speech ≈ **2.6 words per second** plus ~0.25 s per sentence break.
- Per scene: at most 1.6 × scene length + 1 s of speech (holds absorb the excess, ≤ 3 s each). If you need more
  words, lengthen the scene or add a hold after the key moment.
- Whole script: 0.6–1.15 × the brief's target duration (`NS-03`).

## Hold attention (match previews and tactic videos)
- **The hook earns the watch.** In the first 5 seconds: a surprising true fact, a contradiction, or a stake, from the dossier or the tactic. "Arsenal have won eight of nine, and the one team that beat them plays the way Madrid will." It is true and specific to this match, never a generic "this is a huge game".
- **Open a question the end answers.** Say what the video will settle, and pay it off in the last scene. A hook the video doesn't pay off is clickbait: rewrite it.
- **Something new every 15 to 20 seconds:** a new fact, a turn ("but"), or a shift from numbers to the pitch. No two graphic scenes in a row saying the same kind of thing.
- **A little fun.** Sound like a sharp pundit having a good time: a dry aside, a rivalry, a playful comparison. One or two per video, about football. Never about injuries, illness, private lives, nationality or a person's looks, and never at the cost of accuracy.
- **Caveats once, up front, in plain words.** "Three games each, so a small sample" is enough; let "if" carry a scenario and let on-screen labels repeat it. Stacking "reportedly" and "according to" sounds like a sourcing memo.
- **Rumours are said as rumours,** naming the outlet when it helps. Experts are named, and viewers should hear the disagreement.

## Style
- **Hook** first sentence: ≤ 12 words (`NS-04`), see "Hold attention".
- Short sentences (≤ 24 words; ≤ 45 words per line — `NS-05`). Present tense, active voice, concrete verbs:
  *steps inside, drags, pins, screens, releases, arrives*.
- Name roles or players the viewer can see ("the right-back", "Rice"), never ids like H7/E01 (`NS-02`).
- Spell formations for the voice: "four-three-three" (`NS-08`). No filler: basically, really, just… (`NS-09`).
- Audience: *beginner* — define each term once; *intermediate* — standard vocabulary; *expert* — dense, precise.
- Explain the **why** after the **what**: show it, name it, say why it works, say what it costs.
- Match previews: balanced, evidence-led, uncertainty stated plainly; the prediction is "what the numbers suggest",
  never a certainty; no betting language ("odds", "bet", "lock", "banker").

## Anchors (sync words to motion)
`{"word":"inside,","occurrence":1,"ref":"E01","lead_s":0.0}` ties the spoken word to an on-screen event; the
timeline warps motion so they land within ±2 frames. `word` is matched against the line's tokens including
punctuation (`inside,`). `ref` = event id, action handle (`H2@move#1.start`), or a graphic reveal (`R1`).
Anchor at least half of the explain/demonstrate/exploit/battle scenes (`NS-06`) — anchor the verb of the action.

## Pronunciation
`"pronunciations": {"Gvardiol": "Gvar-dee-ol"}` — key must occur in the text, value is ONE token so word timing
stays aligned (`NS-07`). Use it for player names and foreign words the voice may mangle.

## Numbers (match previews — `NS-10`)
Every number you speak must be declared on that line:
`"numbers":[{"text":"2.3","ref":"H.goals_for_avg"},{"text":"47%","ref":"prediction.probs_final.home"}]`.
The validator checks the value against the dossier/prediction. Round the way you speak ("two point three goals").
Probabilities may be spoken as percentages of the 0–1 value.
