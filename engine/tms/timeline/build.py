"""Real timeline from the voice-over: per-scene warps that anchor spoken words to on-screen events."""
from __future__ import annotations

import math

from tms.timeline import FPS, INTRO_FRAMES, OUTRO_FRAMES, SPF, chunk_captions

VO_START_F = 6          # voice starts 0.2 s into its scene
VO_TAIL_S = 0.35        # breathing room after the last word
SLOPE_MIN, SLOPE_MAX = 0.8, 1.25
MAX_HOLD_F = 90          # 3 s
MAX_SHIFT_F = 30         # the voice may start up to 1 s late to make room for motion


class TimelineError(Exception):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def _ref_tau(choreo: dict, scene_id: str, ref: str, tau0: float) -> float | None:
    """Scene-local tau of an anchor ref (event id, action handle[.start|.end], or graphic reveal)."""
    use = "start"
    base = ref
    if ref.endswith((".start", ".end")):
        base, use = ref.rsplit(".", 1)
    key = f"{scene_id}:{base}"
    for e in choreo["events"]:
        if e["id"] == key:
            return (e["tau0"] if use == "start" else e["tau1"]) - tau0
    for a in choreo["actions"]:
        if a["handle"] == key:
            return (a["tau0"] if use == "start" else a["tau1"]) - tau0
    for s in choreo["scenes"]:
        if s["id"] == scene_id:
            for r in s.get("reveals", []):
                if r["id"] == base:
                    return r["tau"] - tau0
    return None


def _quietest_tau(choreo: dict, scene: dict, a: float, b: float) -> float:
    """Scene-local tau in (a, b) where players move least (best place for an automatic hold)."""
    n = choreo["tracks"]["n"]
    f0 = int(round((scene["tau0"] + a) * FPS)) + 1
    f1 = min(int(round((scene["tau0"] + b) * FPS)) - 1, n - 2)
    if f1 <= f0:
        return (a + b) / 2
    best, best_f = None, f0
    players = choreo["tracks"]["players"]
    for f in range(f0, f1 + 1, 2):
        s = 0.0
        for arr in players.values():
            s += math.hypot(arr[2 * (f + 1)] - arr[2 * f], arr[2 * (f + 1) + 1] - arr[2 * f + 1])
        if best is None or s < best:
            best, best_f = s, f
    return best_f / FPS - scene["tau0"]


def solve_scene(choreo: dict, scene: dict, clip: dict | None, anchors: list[dict], warnings: list[str]) -> tuple[list, int, int, list]:
    """Returns (warp knots [[tau, frame_offset]...], length_frames, vo_start_frames, anchor records)."""
    L = scene["len"]
    n = int(round(L * FPS))
    if clip is None:  # silent scene: motion at 1x
        return [[0.0, 0], [round(L, 4), n]], n, 0, []
    words = clip["words"]
    D = clip["duration_s"]
    # choreography stores hold times on the global tau clock; the solver works scene-local
    holds = sorted((dict(h, tau=h["tau"] - scene["tau0"]) for h in scene["holds"]), key=lambda h: h["tau"])
    knots_src = []
    for an in anchors:
        toks = [w["display"].lower() for w in words]
        idx = [k for k, t in enumerate(toks) if t == an["word"].lower()]
        if len(idx) < an["occurrence"]:
            raise TimelineError([f"{scene['id']}: anchor word {an['word']!r} not in the voice-over"])
        wi = idx[an["occurrence"] - 1]
        tau = _ref_tau(choreo, scene["id"], an["ref"], scene["tau0"])
        if tau is None:
            raise TimelineError([f"{scene['id']}: anchor ref {an['ref']!r} not found in the choreography"])
        knots_src.append((tau, words[wi]["start_s"] + an.get("lead_s", 0.0), wi, an["ref"]))
    knots_src.sort()
    for (t1, w1, *_), (t2, w2, *_) in zip(knots_src, knots_src[1:]):
        if w2 <= w1:
            raise TimelineError([f"{scene['id']}: anchors out of order — the narration says them in a different order than they happen"])

    # 1) spacing between consecutive anchors is fixed by the voice: it may compress motion to 0.8x at most
    for (ta, wa, _, ra), (tb, wb, _, rb) in zip(knots_src, knots_src[1:]):
        if tb > ta and (wb - wa) < SLOPE_MIN * (tb - ta) - 1e-9:
            raise TimelineError([f"{scene['id']}: {ra} -> {rb} takes {tb - ta:.2f}s on the pitch but only {wb - wa:.2f}s in the "
                                 f"voice-over (compression {(wb - wa) / (tb - ta):.2f} < {SLOPE_MIN}): add words between the two "
                                 "anchors, anchor different words, or shorten the motion"])
    # 2) the voice may start late (up to 1 s) so the first anchored event is not compressed
    vo_f = VO_START_F
    if knots_src:
        t1, w1 = knots_src[0][0], knots_src[0][1]
        need = math.ceil(SLOPE_MIN * t1 * FPS - w1 * FPS - VO_START_F)
        if need > MAX_SHIFT_F:
            raise TimelineError([f"{scene['id']}: the first anchored event happens {t1:.2f}s into the motion but its word is "
                                 f"spoken at {w1:.2f}s — say it later (more words before it) or start the action earlier"])
        vo_f = VO_START_F + max(0, need)
    pts = [(0.0, 0.0)] + [(t, vo_f + w * FPS) for t, w, _, _ in knots_src]
    # 3) after the last anchor the motion plays at 1x; the scene lasts until both motion and voice are done
    t_last, f_last = pts[-1]
    end_f = max(f_last + (L - t_last) * FPS, vo_f + (D + VO_TAIL_S) * FPS)
    pts.append((L, float(math.ceil(end_f))))

    warp: list[list[float]] = [[0.0, 0]]
    cur_f = 0.0
    for (ta, fa), (tb, fb) in zip(pts, pts[1:]):
        dt_tau = tb - ta
        dt_out = (fb - fa) / FPS
        if dt_tau <= 1e-9:
            if fb > fa:  # two knots at the same tau: an explicit hold
                cur_f = fb
                warp.append([round(tb, 4), int(round(cur_f))])
            continue
        slope = dt_out / dt_tau
        if slope <= SLOPE_MAX:
            cur_f = fb
            warp.append([round(tb, 4), int(round(cur_f))])
            continue
        excess = dt_out - dt_tau  # time to place in holds (motion keeps 1x)
        seg_holds = [h for h in holds if ta < h["tau"] <= tb]
        plan = []
        for h in seg_holds:
            if excess <= 1e-6:
                break
            take = min(h["max_s"], excess, MAX_HOLD_F / FPS)
            plan.append((h["tau"], take))
            excess -= take
        stretch = 1.0
        if excess > 1e-6:  # stretch motion up to SLOPE_MAX before inventing a hold
            add = min(excess, (SLOPE_MAX - 1.0) * dt_tau)
            stretch = (dt_tau + add) / dt_tau
            excess -= add
        if excess > 1e-6:
            if excess > MAX_HOLD_F / FPS:
                raise TimelineError([f"{scene['id']}: narration runs {excess:.1f}s longer than the motion can hold between tau "
                                     f"{ta:.2f}s and {tb:.2f}s — cut words, add holds, or lengthen the scene"])
            qt = _quietest_tau(choreo, scene, ta, tb)
            plan.append((qt, excess))
            warnings.append(f"TL-03 {scene['id']}: automatic {excess:.1f}s hold at tau {qt:.2f}s (declare a hold to control it)")
        plan.sort()
        # motion pieces get exact (rounded) frame counts at `stretch`; the holds absorb all rounding
        cuts = [ta] + [ht for ht, _ in plan] + [tb]
        motion = [int(round((b - a) * stretch * FPS)) for a, b in zip(cuts, cuts[1:])]
        hold_total = int(round(fb - cur_f)) - sum(motion)
        want = [d for _, d in plan]
        hold_f = [int(round(hold_total * d / sum(want))) for d in want] if want and sum(want) > 0 else []
        if hold_f:
            hold_f[-1] = hold_total - sum(hold_f[:-1])
        f_prev = int(round(cur_f))
        for k, (ht, _) in enumerate(plan):
            f_at = f_prev + motion[k]
            warp.append([round(ht, 4), f_at])
            f_prev = f_at + max(hold_f[k], 0)
            warp.append([round(ht, 4), f_prev])
        cur_f = fb
        warp.append([round(tb, 4), int(round(cur_f))])
    # dedupe identical consecutive knots
    clean = [warp[0]]
    for k in warp[1:]:
        if k != clean[-1]:
            clean.append(k)
    length = int(round(cur_f))
    recs = []
    from tms.timeline import frame_of_tau
    for t, w, wi, ref in knots_src:
        recs.append({"ref": ref, "word": wi, "word_frame": vo_f + int(round(words[wi]["start_s"] * FPS)),
                     "event_frame": int(round(frame_of_tau(clean, t))), "lead_f": int(round((w - words[wi]["start_s"]) * FPS))})
    return clean, length, vo_f, recs


def build_timeline(choreo: dict, vo: dict, narration: dict, project_id: str, inputs: dict) -> tuple[dict, list[str]]:
    clips = {c["scene"]: c for c in vo["clips"]}
    lines = {ln["scene"]: ln for ln in narration["lines"]}
    scenes, vo_out, words_out, anchors_out, caps = [], [], [], [], []
    warnings: list[str] = []
    problems: list[str] = []
    f = INTRO_FRAMES
    wi = 0
    for s in choreo["scenes"]:
        clip = clips.get(s["id"])
        try:
            warp, length, vo_f, recs = solve_scene(choreo, s, clip, lines.get(s["id"], {}).get("anchors", []), warnings)
        except TimelineError as e:
            problems += e.problems
            continue
        scenes.append({"id": s["id"], "from": f, "to": f + length, "vo": clip["id"] if clip else None, "warp": warp})
        if clip:
            vfrom = f + vo_f
            vo_out.append({"id": clip["id"], "scene": s["id"], "from": vfrom, "samples": clip["samples"], "file": clip["file"]})
            cw = []
            for w in clip["words"]:
                a = vfrom + int(round(w["start_s"] * FPS))
                b = max(vfrom + int(round(w["end_s"] * FPS)), a + 1)
                cw.append({"i": wi, "clip": clip["id"], "display": w["display"], "from": a, "to": b})
                wi += 1
            words_out += cw
            caps += [dict(c, to=min(c["to"], f + length)) for c in chunk_captions(cw)]
            for r in recs:
                g = cw[r["word"]]
                anchors_out.append({"scene": s["id"], "word": g["i"], "ref": r["ref"], "word_frame": g["from"],
                                    "event_frame": f + r["event_frame"], "err": f + r["event_frame"] - (g["from"] + r["lead_f"])})
        f += length
    if problems:
        raise TimelineError(problems)
    total = f + OUTRO_FRAMES
    windows = []
    for v in vo_out:
        a, b = v["from"], v["from"] + math.ceil(v["samples"] / SPF)
        if windows and a - windows[-1][1] <= 8:
            windows[-1][1] = b
        else:
            windows.append([a, b])
    return {
        "version": "1", "project_id": project_id, "inputs": inputs, "fps": FPS, "sr": SPF * FPS, "frames": total,
        "intro": {"from": 0, "to": INTRO_FRAMES}, "outro": {"from": f, "to": total},
        "scenes": scenes, "vo": vo_out, "words": words_out, "anchors": anchors_out,
        "captions": [{"id": f"C{k + 1:02d}", "from": c["from"], "to": max(c["to"], c["from"] + 1), "lines": c["lines"],
                      "words": c["word_index"], "place": "bottom"} for k, c in enumerate(caps)],
        "duck": {"windows": windows, "depth_db": -10.0, "attack_ms": 150.0, "release_ms": 450.0},
    }, warnings
