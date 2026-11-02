"""Motion primitives: speed profiles, curved paths, pursuit integration. Units: metres, seconds."""
from __future__ import annotations

import math

FPS = 30
DT = 1.0 / FPS
PACE = {"walk": 1.5, "jog": 3.5, "run": 5.5, "sprint": 7.5}
ACCEL = 4.0  # m/s^2 speeding up
DECEL = 4.5  # m/s^2 slowing down
PASS_SPEED = {"ground": 14.0, "driven": 20.0, "through": 16.0, "lofted": 16.0, "cross": 18.0}
SHOT_SPEED = 26.0
P = tuple[float, float]


def sub(a: P, b: P) -> P:
    return (a[0] - b[0], a[1] - b[1])


def add(a: P, b: P) -> P:
    return (a[0] + b[0], a[1] + b[1])


def mul(a: P, k: float) -> P:
    return (a[0] * k, a[1] * k)


def norm(a: P) -> float:
    return math.hypot(a[0], a[1])


def unit(a: P, fallback: P = (1.0, 0.0)) -> P:
    n = norm(a)
    return (a[0] / n, a[1] / n) if n > 1e-9 else fallback


def lerp(a: P, b: P, t: float) -> P:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


class Path:
    """Straight segment or quadratic Bezier bulging `curve_m` metres to the left (+) / right (-) of travel."""

    def __init__(self, a: P, b: P, curve_m: float = 0.0, samples: int = 64):
        self.a, self.b = a, b
        d = sub(b, a)
        perp = (-d[1], d[0])
        u = unit(perp, (0.0, 1.0))
        mid = lerp(a, b, 0.5)
        self.c = add(mid, mul(u, -2.0 * curve_m))  # control point: max deviation ~= curve_m
        self.curved = abs(curve_m) > 1e-6 and norm(d) > 1e-6
        pts = [self._bez(i / samples) for i in range(samples + 1)]
        self.cum = [0.0]
        for i in range(1, len(pts)):
            self.cum.append(self.cum[-1] + norm(sub(pts[i], pts[i - 1])))
        self.pts = pts
        self.length = self.cum[-1]

    def _bez(self, t: float) -> P:
        if not self.curved:
            return lerp(self.a, self.b, t)
        u = 1 - t
        return (u * u * self.a[0] + 2 * u * t * self.c[0] + t * t * self.b[0],
                u * u * self.a[1] + 2 * u * t * self.c[1] + t * t * self.b[1])

    def at_distance(self, s: float) -> P:
        if self.length <= 1e-9:
            return self.b
        s = min(max(s, 0.0), self.length)
        lo, hi = 0, len(self.cum) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.cum[mid] < s:
                lo = mid
            else:
                hi = mid
        seg = self.cum[hi] - self.cum[lo]
        k = 0.0 if seg <= 1e-12 else (s - self.cum[lo]) / seg
        return lerp(self.pts[lo], self.pts[hi], k)

    def polyline(self, n: int = 12) -> list[P]:
        return [self.at_distance(self.length * i / n) for i in range(n + 1)]


class Profile:
    """1-D speed profile covering distance L: accelerate from v0 to vmax, cruise, decelerate to 0."""

    def __init__(self, L: float, vmax: float, v0: float = 0.0):
        self.L, self.v0 = max(L, 0.0), min(max(v0, 0.0), vmax)
        d_acc = (vmax ** 2 - self.v0 ** 2) / (2 * ACCEL)
        d_dec = vmax ** 2 / (2 * DECEL)
        if d_acc + d_dec <= self.L:
            self.vpeak = vmax
            self.t1 = (vmax - self.v0) / ACCEL
            self.t2 = self.t1 + (self.L - d_acc - d_dec) / vmax
        else:  # triangular: v0^2 + 2a s1 = vp^2 = 2 d s2, s1 + s2 = L
            vp2 = (2 * ACCEL * DECEL * self.L + DECEL * self.v0 ** 2) / (ACCEL + DECEL)
            self.vpeak = math.sqrt(max(vp2, self.v0 ** 2))
            self.t1 = (self.vpeak - self.v0) / ACCEL
            self.t2 = self.t1
        self.T = self.t2 + self.vpeak / DECEL
        self.s1 = self.v0 * self.t1 + 0.5 * ACCEL * self.t1 ** 2
        self.s2 = self.s1 + self.vpeak * (self.t2 - self.t1)

    def s(self, t: float) -> float:
        if t <= 0:
            return 0.0
        if t <= self.t1:
            return self.v0 * t + 0.5 * ACCEL * t * t
        if t <= self.t2:
            return self.s1 + self.vpeak * (t - self.t1)
        if t <= self.T:
            u = t - self.t2
            return min(self.s2 + self.vpeak * u - 0.5 * DECEL * u * u, self.L)
        return self.L


def pursue(pos: P, vel: P, target: P, vmax: float, tau: float = 0.35, accel: float = ACCEL) -> tuple[P, P]:
    """One integration step toward `target` with speed <= vmax and acceleration caps."""
    desired = sub(target, pos)
    dist = norm(desired)
    # never overshoot: desired speed limited by what can be braked within the remaining distance
    vbrake = math.sqrt(2 * DECEL * dist)
    dv_speed = min(vmax, dist / tau, vbrake)
    dvel = mul(unit(desired, (0.0, 0.0)), dv_speed)
    change = sub(dvel, vel)
    cmag = norm(change)
    speeding = norm(dvel) > norm(vel)
    cap = (accel if speeding else min(DECEL + 1.0, accel + 1.5)) * DT
    if cmag > cap:
        change = mul(change, cap / cmag)
    nv = add(vel, change)
    return add(pos, mul(nv, DT)), nv


def drift(pid: str, t: float) -> P:
    """Deterministic idle sway (~0.25 m, ~0.2 Hz) so static players look alive."""
    ph = (sum(ord(c) for c in pid) % 17) / 17 * 2 * math.pi
    return (0.25 * math.sin(2 * math.pi * 0.17 * t + ph), 0.2 * math.cos(2 * math.pi * 0.21 * t + 1.3 * ph))


def ease_in_out_cubic(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2
