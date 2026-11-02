---
name: stage-render
description: Render stage - build render_props from the approved storyboard and audio timeline, render the final 1080p video with Remotion, mix and mux the audio, write captions.srt, measure the FQ quality checks, run visual QA on sampled frames, and hand off for approve final. Use when tms next names the render stage.
---

# Stage: render → `build/render_props.json`, `build/render_report.json`, `renders/final.mp4`

Reviewer: **visual-qa** (1–2 rounds). Gate: user types `approve final`.

## Steps
1. `.venv/Scripts/tms stage begin render`
2. `.venv/Scripts/tms render final` (default 1920×1080 for 16:9; `--scale 0.5` only for quick internal checks).
   It builds render_props (RP rules), renders the silent video, mixes voice + ducked music to −14 LUFS, muxes without
   re-encoding the video, writes `renders/captions.srt`, and measures:
   FQ-01 format/frames · FQ-02 audio/length · FQ-03 loudness · FQ-04 voice over music · FQ-05 black frames ·
   FQ-06 pixel probes · FQ-07 speech-to-text (live) · FQ-08 bitrate.
   Exit 1 = a check failed: read `build/render_report.json` and fix the cause (usually upstream: reopen the stage
   that owns it). Never edit render_props or the report.
3. QA: launch **visual-qa** with `renders/final_contact_sheet.png`, the frames in `renders/qa/`, the timeline captions
   and the render_report; record with `.venv/Scripts/tms qa record render --agent visual-qa --review <file>`.
4. **gate-verifier** → pass; `.venv/Scripts/tms stage submit render` → `awaiting_human`.
5. Present: `projects/<slug>/renders/final.mp4` (duration, resolution), `renders/captions.srt`, the FQ table, mock vs
   live audio, total spend (voice characters, music seconds). "Type `approve final`, or `reject final: <what to change>`."
