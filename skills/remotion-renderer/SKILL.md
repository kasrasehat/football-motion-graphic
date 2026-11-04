---
name: remotion-renderer
description: How the Remotion renderer in render/ turns render_props.json into broadcast-style frames - the props-to-component map, projection, overlays, captions, cards and graphics registry, how to add a component, overlay kind or graphic template, the determinism rules, and the verify / studio / still-preview commands. Use when changing anything under render/, previewing a still, or debugging how a frame looks.
---

# Remotion renderer (render/)

The renderer is a **pure function of (frame, render_props)**. Python (`engine/tms`) computes every position, camera
value and timing and writes `render_props.json` (one sample per frame). The renderer only draws it. It never
interpolates motion, never decides timing and never invents text or numbers (the one exception is the
`distance` overlay, which formats the length between its two points).

Contract: `schemas/artifacts/render_props.schema.json`. Fixture: `tests/fixtures/artifacts/render_props.json`
(90 frames, copied to `render/src/fixtures/render_props.fixture.json` as the composition's `defaultProps`; after the
fixture changes, run `npm --prefix render run sync:fixture`).

## Map: props key to code
| props | where | notes |
|---|---|---|
| `width/height/fps/durationInFrames` | `src/TacticVideo.meta.ts` `calculateTacticMetadata` | ajv validation (`src/lib/validate.ts`) + per-frame length checks; throws `Invalid render_props (N problems): /path message` |
| `camera` `[cx,cy,w]` cm | `components/CameraRig.tsx` → `useProjector()` | `w` = visible extent along pitch x |
| `orientation` | `lib/projection.ts` | landscape/square: x→right; portrait: home attacks UP, pitch y→screen right |
| `theme.pitch` | `components/Pitch.tsx` | FIFA markings in metres under an SVG matrix; 18 mowing stripes; 6 m striped run-off |
| `entities` + `tracks.players` | `components/Players.tsx` `PlayerToken`, `PlayerLabels` | 2.0 m diameter, never < 26 px at 1080p (`tokenRadiusPx`); `label` as a pill placed by `lib/playerLabels.ts` (see "Player labels") |
| `tracks.ball` `[x,y,z]` | `components/Ball.tsx` | drawn at ground point; z moves/softens the shadow |
| `pitchVisible` | `TacticVideo.tsx` | world layer hidden outside spans (6-frame fade at inner span edges) |
| `overlays` | `components/overlays/Overlays.tsx` | see below |
| `captions` | `components/Captions.tsx`, `lib/captions.ts` | ≤ 2 lines, 44 px at 1080p (shrinks only to fit), active word highlighted |
| `scenes[].title` | `components/SceneTitle.tsx`, `lib/hud.ts` | lower-third for the first 60 frames; lifted above a bottom caption |
| `titleCard` / `endCard` | `components/Cards.tsx` | full-screen, null = none |
| `freeze` | `components/Hud.tsx` `FreezeVignette` | edge vignette + PAUSED badge (tracks are already frozen by the engine) |
| `graphics` | `components/graphics/registry.tsx` | all 11 templates implemented; see "Graphic templates" below |
| `principleRail` | `components/PrincipleRail.tsx`, `lib/rail.ts` | tactic still only: key panel in `rect` (title, teams, ball holder, whole principle names, players as chips); type sized to fit (`railMetrics`) |
| `debug.overlay` | `components/Hud.tsx` `DebugOverlay` | frame / camera readout + safe-area guide |

Z-order: pitch → overlays "under" (zone, polygon, line, pass_line, run_arrow, distance) → players → ball → overlays
"over" (spotlight first, then ring, label callouts and every overlay's label pill) → player labels → key panel → graphics → freeze →
scene title →
title/end card → captions → debug.

## Projection (keep the twins identical)
`render/src/lib/projection.ts` and `engine/tms/render/projection.py` implement the same maths:
`s = width / w` (portrait: `height / w`); landscape `(W/2 + (x-cx)s, H/2 + (y-cy)s)`; portrait
`(W/2 + (y-cy)s, H/2 - (x-cx)s)`. Both are tested against `tests/fixtures/projection_vectors.json` (≤ 1e-6 px;
regenerate with `.venv/Scripts/python.exe tests/render/gen_projection_vectors.py`, which uses an independent
matrix formulation). Pixel probes use the Python side: `tms.render.project_player(props, "H4", frame)`,
`token_radius_px(w, width, height, orientation)`.

A camera of `w = 105` does **not** show the whole pitch in 16:9 or 9:16 (the touchlines are cut). A full-pitch shot
needs `w >= (68 + margin) * width / height` in landscape (about 125 m) and `w >= (68 + margin) * height / width` in
portrait; that is the engine's camera solver's job, not the renderer's.

## Overlays
Visible on `[from, to)`. Geometry: `{static: [[x,y],...]}` metres or `{perFrame: [...]}` indexed by `frame - from`
(clamped). `inAnim`/`outAnim` (`lib/anim.ts`): `draw` reveals a path over its length (out-draw erases from the
start), `fade`, `pop` (ease-out-back scale), `none`. Non-path kinds treat `draw` as a fade. Colours:
`accent|warn|ink` → theme, `H|A` → team fill. Kinds: `run_arrow` (curved spline unless `style.curved: false`,
glow, arrowhead), `pass_line` (dashed, arrowhead, trimmed to the token edge when an end sits on a player), `line`,
`polygon`, `zone` (light fill + hatching), `ring` (frame-derived pulse), `spotlight` (dims everything else),
`label` (callout above the point), `distance` ("12.3 m").
Label pills are placed by `lib/labels.ts`: a slot is chosen once per overlay over its whole window so the label never
jumps, minimising overlap with player tokens and HUD boxes (`lib/hud.ts hudRects`). Zone/polygon labels sit on the
visible part of the area.

## Player labels
`lib/playerLabels.ts` `placePlayerLabels(props, frame)` is the only source of pill positions:
- **Video** (`durationInFrames > 1`): always straight below the token, whatever is there. A pill that changed side as
  players move would be worse than a passing overlap (pinned by `render/test/player-labels.test.ts`).
- **One-frame still** (`durationInFrames === 1`, i.e. `tms tactic still`): the whole set is solved at once. Every pill
  clears every token and ring, the ball, every other pill and the key panel; it stays against its token if it can and
  takes a leader line if not. The search counts nodes, so a still is reproducible.

The still's frame comes from `engine/tms/tactic/still.py`: the camera leaves `principleRail.rect` free, the principle
titles live in the panel (never as `label` overlays on the pitch), and the ball sits fully outside the holder's token
and ring, clear of other players, so it is never covered (rings draw over the ball). `ball_radius_px` and
`ring_outer_radius_px` in `engine/tms/render/projection.py` are twins of `ballRadiusPx` and `ringOuterRadiusPx`.
Dense fixture: `tests/fixtures/still/` (regenerate the `props.*.json` with
`.venv/Scripts/python.exe tests/render/gen_still_fixtures.py`).

## Add things
- **Component**: pure props in, `useCurrentFrame()` only at the top (`TacticVideo.tsx` passes `frame`); world-space
  components read `useProjector()`; sizes are authored at 1080p and multiplied by `unit(width, height)`; put pure
  logic in `src/lib/` with a vitest; mount it in `TacticVideo.tsx` at the right z-order.
- **Overlay kind**: schema change first (`schemas/`, owned by the contract), then `npm --prefix render run gen:types`,
  add the renderer to `RENDERERS` in `Overlays.tsx`, its layer to `UNDER_KINDS`/`OVER_KINDS`/`PATH_KINDS`
  (`lib/overlays.ts`), and tests in `render/test/overlays.test.ts`. Render a still and look at it.
- **Graphic template**: add a component to `GRAPHIC_TEMPLATES` in `components/graphics/registry.tsx` (one file per
  template), wrap it in `Shell` (`common.tsx`) and follow the rules below. Values come from props only, never typed in
  code; add a fixture in `tests/fixtures/graphics/`, edge data in `render/test/graphics-templates.test.ts`, and look
  at a still in landscape, portrait and square.

## Graphic templates (full-screen data cards; the pitch is hidden during graphic scenes)
Shared rules (`components/graphics/common.tsx`, pure helpers in `lib/graphics.ts`):
- **Shell**: `CardBackdrop` + centred panel (accent strip, accent kicker, Barlow Condensed 800 title, `RMA v ARS`
  team lock-up) inside `contentRect()` = the 90% safe area minus the bottom 22% (captions live there).
  `shellLayout(width, height, {panelW, bodyH})` gives the body box; layouts switch on `layoutMode()`
  (`landscape` / `portrait` / `square`). Sizes are authored at 1080p × `unit()`.
- **Reveals**: `revealFrame(g, i)` = `reveals[i].frame` (absolute, never before `from`); items past the last reveal
  come with it; no reveals = staggered from `from` (6 frames). `revealProgress` eases 0→1. Card fade in/out 8 frames.
- **Data is read leniently** (`asRecord`, `asArray`, `str`, `normResults`, `normLineup`, ...): missing / junk values
  render as "–" or an empty-state line, never throw (vitest renders every template with empty, null, junk and long
  data in all orientations and asserts no `NaN`/`undefined` in the markup).
- **Text never overflows**: `Txt` shrinks to fit (estimate) then CSS-ellipsizes; `Para` clamps to 2 lines;
  player names use `fitName` (full → surname with particles/suffixes → known-as name).
- **Colours**: theme only. Team fills `theme.teams.H/A` (`Swatch`), win/draw/loss = `resultColors(theme)`
  (grass hue / ink-panel grey / warn), neutral = ink-panel mix.

| template | data (fixed contract) | items / reveals | notes |
|---|---|---|---|
| `title_card` / `text_card` | headline, sub / title, body, bullets[] | bullets | existing |
| `stat_compare` | title?, labels[], home[], away[], units?[] | one per row (≤ 10) | mirrored bars from the centre, length = value / max of the pair; strings/null: value only |
| `form_guide` | home[], away[] of W/D/L, most recent last | home row, away row | chips centred, latest outlined, points from last N (W3 D1) |
| `h2h_strip` | results[{date, home, away, score}] | one per meeting | newest first (ISO dates); wins/draws summary when names match the theme; landscape tiles, else rows; loser dimmed |
| `lineup_board` | home[], away[] {name, number, position G/D/M/F}, home_/away_formation? | home, away | mini vertical pitches (stacked in portrait); rows from the formation if it sums to the outfield count, else from positions (rows > 5 split) |
| `team_news` | home[], away[] {player, reason, status?} | home, away | max 6 rows (5 + "+N more"); out = warn ✕, doubt = accent ?; "No reported absences" |
| `key_player_duel` | title, home_player, away_player {name, number}, why?, home_stats[], away_stats[] {label, value} | cards, stats, why | jersey with the shirt number in team colours; stats ≤ 5 rows aligned by index |
| `probability_bar` | home, draw, away (0–1) | home, draw, away segment | kicker "Model probabilities"; `largestRemainder` → integers summing to 100 |
| `scoreline_grid` | scorelines[{home, away, p}] | one per tile (rank order) | top 6 tiles + 0–4 × 0–4 heat grid when ≥ 6 entries, else ≤ 5 tiles |
| `prediction_card` | result home/draw/away, scoreline, confidence low/medium/high, note? | result, score, confidence+note | footer "Statistical analysis, not betting advice" ALWAYS rendered (`PREDICTION_DISCLAIMER`) |

Fixtures: `tests/fixtures/graphics/<template>.json` (Real Madrid v Arsenal, 90 frames, pitch hidden, one graphic over
all frames). Real stills: `.venv/Scripts/python.exe -m pytest tests/render/test_graphics.py -q -m render` (late
frame, scale 0.5: not blank, both team fills present at CIEDE2000 < 12, portrait renders, byte-identical twice).

## Determinism rules (enforced by `render/test/determinism.test.ts`)
No `Math.random`, `Date`, `performance.now`, timers, `requestAnimationFrame`, CSS `animation`/`transition`/
`@keyframes`, SMIL `<animate>`. Everything derives from the frame number and props; a still rendered twice is
byte-identical (checked by `tests/render`). Fonts are local (`public/fonts`, loaded with `@remotion/fonts`):
Barlow Condensed 600/800 for titles and labels, Inter 500/700 for captions.

## Commands
```
npm --prefix render run verify          # gen:types check + tsc --noEmit + vitest (must be green)
npm --prefix render run verify:fast     # tsc only
npm --prefix render run gen:types       # regenerate src/generated/render_props.ts after a schema change
npm --prefix render run studio          # Remotion Studio (TacticVideo with the fixture as default props)
.venv/Scripts/python.exe -m pytest tests/render -q -m render   # real renders: frame counts, pixel probes, byte-identical stills
```
Preview a still (Python sets the browser for you):
```
.venv/Scripts/python.exe -c "from tms import remotion; print(remotion.render('TacticVideo', 'out.png', 'props.json', still=45))"
```
or directly: `node render/scripts/render.mjs --composition TacticVideo --out out.png --props props.json --still 45`
(video: `--out out.mp4 [--scale 0.5] [--frames 0-89]`). Then open the PNG with Read and look at it.

**Browser note:** Remotion's headless-shell download is geo-blocked here, so renders use the system Chrome/Edge via
`TMS_BROWSER_EXECUTABLE` with `chromeMode: "chrome-for-testing"` (`render.mjs`); `tms.remotion.render` finds the
browser automatically. When calling `render.mjs` yourself, set `TMS_BROWSER_EXECUTABLE` first.
