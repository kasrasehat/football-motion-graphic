---
name: stage-package
description: Optional publishing stage - write package.json (title, description, chapters, tags, thumbnail frame) for the approved final video and export the thumbnail. Use only when the user asks for publishing metadata after approve final.
---

# Stage: package (optional) → `artifacts/package.json` (+ `renders/thumbnail.png`)

1. `.venv/Scripts/tms stage begin package`
2. `.venv/Scripts/tms package chapters` prints chapter marks (scene starts and titles) from the timeline.
3. Write `projects/<slug>/artifacts/package.json`: `title` (≤ 100, clear and searchable, no clickbait claims),
   `description` (what the viewer learns; for match previews: fixture, kickoff, "analysis, not betting advice"),
   `chapters` (from step 2), `tags`, `thumbnail_frame` (a frame showing the key idea clearly).
4. `.venv/Scripts/tms package thumbnail --frame <N>` → `renders/thumbnail.png`; look at it.
5. `.venv/Scripts/tms validate package`, then `.venv/Scripts/tms stage submit package` → present → `approve package`.
Never publish or upload anything yourself; the user publishes.
