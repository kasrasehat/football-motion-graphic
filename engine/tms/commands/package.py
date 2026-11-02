"""`tms package chapters|thumbnail` — helpers for the optional package stage."""
from __future__ import annotations

from tms.audio import wav
from tms.commands.common import add_project_arg, handled
from tms.state import project as P

FPS = 30


@handled
def cmd_chapters(a):
    pr = P.load(a.project)
    tl, plan = pr.load_artifact("timeline"), pr.load_artifact("scene_plan")
    if not tl or not plan:
        raise P.ProjectError("needs build/timeline.json and artifacts/scene_plan.json")
    titles = {s["id"]: s["title"] for s in plan["scenes"]}
    print('{"t_s": 0, "title": "Intro"}')
    for s in tl["scenes"]:
        print(f'{{"t_s": {s["from"] / FPS:.1f}, "title": "{titles.get(s["id"], s["id"])}"}}')


@handled
def cmd_thumbnail(a):
    pr = P.load(a.project)
    video = pr.dir / "renders" / "final.mp4"
    if not video.is_file():
        raise P.ProjectError("renders/final.mp4 not found — render first")
    out = pr.dir / "renders" / "thumbnail.png"
    wav.run([wav.ffmpeg(), "-v", "error", "-y", "-ss", f"{a.frame / FPS + 0.001:.4f}", "-i", video, "-frames:v", "1", out])
    print(f"thumbnail: {out}")


def register(sub) -> None:
    p = sub.add_parser("package", help="publishing helpers (optional package stage)")
    psub = p.add_subparsers(dest="package_action", required=True)
    c = psub.add_parser("chapters", help="chapter marks from the timeline")
    add_project_arg(c)
    c.set_defaults(func=cmd_chapters)
    t = psub.add_parser("thumbnail", help="export a frame of final.mp4 as renders/thumbnail.png")
    add_project_arg(t)
    t.add_argument("--frame", type=int, required=True)
    t.set_defaults(func=cmd_thumbnail)
