"""`tms audio build` — voice-over -> timeline -> music, each validated (VO / TL / MU rules)."""
from __future__ import annotations

from tms import jsonio
from tms import validate as V
from tms.audio import music, voiceover
from tms.audio.elevenlabs import ElevenLabsError
from tms.commands.common import add_project_arg, handled
from tms.state import machine, project as P
from tms.timeline.build import TimelineError, build_timeline


def _h(pr, *names):
    return {n: jsonio.sha256_file(pr.artifact_path(n)) for n in names}


def build_all(pr, only: str | None = None) -> list:
    machine.require_active(pr, "audio")
    findings = []
    try:
        if only in (None, "vo"):
            vo = voiceover.build(pr, _h(pr, "narration_script", "brief"))
            jsonio.write_json(pr.artifact_path("voiceover_manifest"), vo)
            findings += V.validate_file(pr.dir, "voiceover_manifest", pr.mode)
        if only in (None, "timeline"):
            tl, warns = build_timeline(pr.load_artifact("choreography"), pr.load_artifact("voiceover_manifest"),
                                       pr.load_artifact("narration_script"), pr.id,
                                       _h(pr, "choreography", "voiceover_manifest", "narration_script"))
            jsonio.write_json(pr.artifact_path("timeline"), tl, compact=True)
            for w in warns:
                print(f"  WARNING {w}")
            findings += V.validate_file(pr.dir, "timeline", pr.mode)
        if only in (None, "music"):
            mm = music.build(pr, pr.load_artifact("timeline"), _h(pr, "timeline", "brief"))
            jsonio.write_json(pr.artifact_path("music_manifest"), mm)
            findings += V.validate_file(pr.dir, "music_manifest", pr.mode)
    except TimelineError as e:
        raise P.ProjectError("timeline cannot be solved — revise the storyboard (narration/anchors/holds):\n  - "
                             + "\n  - ".join(e.problems))
    except ElevenLabsError as e:
        raise P.ProjectError(str(e))
    return findings


@handled
def cmd_build(a):
    pr = P.load(a.project)
    findings = build_all(pr, a.only)
    errs = V.errors_only(findings)
    for f in findings:
        print(f"  {f.severity.upper():7s} [{f.rule}] {f.location + ': ' if f.location else ''}{f.message}")
    tl = pr.load_artifact("timeline")
    vo = pr.load_artifact("voiceover_manifest")
    if tl and vo:
        print(f"voice: {len(vo['clips'])} clips via {vo['provider']}, {vo['chars_billed_total']} chars billed; "
              f"timeline {tl['frames']} frames = {tl['frames'] / 30:.1f} s")
    print(f"audio: {len(errs)} error(s), {len(findings) - len(errs)} warning(s)")
    return 1 if errs else 0


def register(sub) -> None:
    p = sub.add_parser("audio", help="voice-over, timeline and music for the audio stage")
    asub = p.add_subparsers(dest="audio_action", required=True)
    b = asub.add_parser("build", help="build voiceover_manifest, timeline, music_manifest (dry runs use offline mocks)")
    add_project_arg(b)
    b.add_argument("--only", choices=["vo", "timeline", "music"], help="rebuild one step (later steps then need rebuilding)")
    b.set_defaults(func=cmd_build)
