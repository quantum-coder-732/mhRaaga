"""Rigid-body physics for musical feel, on the real Box2D engine (pybox2d 2.3.10) when it is importable.

Backend: `import Box2D` (the C++ engine by Erin Catto, via pybox2d; bodies, a wheel-joint spring, contact with restitution).
If it cannot be imported (a laptop without the wheel, an arm64 build), the same models run on a small pure-Python solver
that ports the same algorithms: semi-implicit Euler, mass and damping, a soft spring, and a sequential-impulse floor contact
with restitution. `BACKEND` says which one ran, and it is written into every score's meta.physics.

What it does to a score:
  rubato  - a heavy body on a damped spring. Long phrase-ending notes kick it, it swings back; its displacement is the
            note-onset offset (a few ms), so phrases lean into their ends and recover, the way a player breathes.
  weight  - a ball dropped onto a floor whose height follows the melody. The impact speed of each landing sets the
            note's dynamic, so leaps strike harder, steps are soft, and stressed notes (vadi/samvadi) are heavier.
  meend   - a critically damped spring pulling the pitch from the old note to the new one. A bigger interval is a heavier
            mass, so the slide is longer. The settling time of the simulation is the glide time.
  drift   - a tiny spring-driven pitch wander (vibrato and breath), which autotune.py then pulls back toward the shruti.
"""
from __future__ import annotations

import math
import random

DT = 1 / 240.0
try:
    import Box2D as _b2
    BACKEND = "box2d " + getattr(_b2, "__version__", "2.3.x")
except Exception:  # pragma: no cover - depends on the platform
    _b2 = None
    BACKEND = "box2d-style (pure python)"
SCALE = 10.0   # Box2D is tuned for 0.1 to 10 metre objects: 1 world unit = 0.1 second of timing, 1 semitone = 1 unit


class Body:
    __slots__ = ("m", "x", "v")

    def __init__(self, m: float = 1.0, x: float = 0.0, v: float = 0.0):
        self.m, self.x, self.v = m, x, v


class World1D:
    """One-dimensional world: a body, an optional spring to an anchor, linear damping, optional floor with restitution."""

    def __init__(self, k: float = 0.0, damping: float = 0.0, gravity: float = 0.0, floor: float | None = None, restitution: float = 0.0):
        self.k, self.c, self.g, self.floor, self.e = k, damping, gravity, floor, restitution
        self.anchor = 0.0
        self.last_impact = 0.0

    def step(self, b: Body, dt: float = DT) -> None:
        f = self.g * b.m - self.k * (b.x - self.anchor) - self.c * b.v
        b.v += f / b.m * dt                # semi-implicit Euler: velocity first,
        b.x += b.v * dt                    # then position with the new velocity
        if self.floor is not None and b.x < self.floor:   # contact: sequential-impulse with restitution
            self.last_impact = max(self.last_impact, -b.v)
            b.x = self.floor
            b.v = -b.v * self.e if -b.v > 0.05 else 0.0


def _py_rubato(events: list[list], beat: float, seed: int, limit_ms: float = 28.0) -> list[float]:
    """Onset offsets in seconds for each lead note. Phrase-ending (long) notes push the body; spring and damping return it."""
    rng = random.Random(seed ^ 0x5EED)
    w = World1D(k=14.0, damping=2.2)
    body = Body(m=1.0)
    out, t_prev = [], 0.0
    for t, _f, d, _o, *_ in events:
        steps = int(max(0.0, t - t_prev) / DT)
        for _ in range(min(steps, 4000)):
            w.step(body)
        t_prev = t
        if d >= 1.6 * beat:                               # a held note ends a phrase: it leans back
            body.v += rng.uniform(0.12, 0.22)
        else:
            body.v += rng.uniform(-0.03, 0.05)            # small human jitter
        out.append(max(-limit_ms, min(limit_ms, body.x * 1000.0)) / 1000.0)
    return out


def _py_weights(pitches: list[float], stress: list[bool]) -> list[float]:
    """Dynamic 0.62 to 1.0 per note from the impact of a ball landing on a floor that follows the melody."""
    if not pitches:
        return []
    lo, hi = min(pitches), max(pitches)
    span = (hi - lo) or 1.0
    w = World1D(gravity=-9.8, damping=0.4, floor=0.0, restitution=0.35)
    body = Body(m=1.0, x=0.0)
    out, prev = [], (pitches[0] - lo) / span
    for p, s in zip(pitches, stress):
        h = (p - lo) / span
        drop = abs(h - prev) * 1.2 + 0.08                  # a leap is a long fall
        body.x, body.v, w.last_impact, w.floor = drop, 0.0, 0.0, 0.0
        for _ in range(600):
            w.step(body)
            if body.x <= 1e-6 and w.last_impact > 0:
                break
        v = min(1.0, 0.62 + 0.34 * min(1.0, w.last_impact / 3.2) + (0.06 if s else 0.0))
        out.append(round(v, 3))
        prev = h
    return out


def _py_glide_time(interval_semitones: float, available: float) -> float:
    """Settling time of a critically damped spring whose mass grows with the interval. Longer for bigger slides."""
    interval = abs(interval_semitones)
    if interval < 1:
        return 0.0
    m = 0.6 + 0.12 * interval
    k = 900.0
    c = 2 * math.sqrt(k * m)                               # critical damping, no overshoot
    w = World1D(k=k, damping=c)
    b = Body(m=m, x=interval)
    n = 0
    while abs(b.x) > 0.04 * interval and n < 960:          # settled to within 4% of the gap
        w.step(b)
        n += 1
    return round(min(n * DT, 0.30, available * 0.5), 3)


def _py_drift_cents(n: int, seed: int, amount: float = 7.0) -> list[float]:
    """Slow spring-driven pitch wander in cents; autotune then corrects it by a fraction."""
    rng = random.Random(seed ^ 0xD71F7)
    w = World1D(k=30.0, damping=4.0)
    b = Body()
    out = []
    for _ in range(n):
        b.v += rng.gauss(0, 0.9)
        for _ in range(60):
            w.step(b)
        out.append(max(-amount, min(amount, b.x * amount * 3)))
    return out


def humanise(events: list[list], beat: float, seed: int, stress_notes: set[int], sa: float, guard_from: float | None = None) -> list[list]:
    """Apply rubato, weight, meend glide time and pitch drift to lead events [t, hz, dur, orn].
    Returns events [t, hz, dur, orn, velocity, glide]. Notes at or after guard_from (the tihai) keep exact timing so the
    last note still lands on sam."""
    if not events:
        return events
    offs = rubato(events, beat, seed)
    semis = [12 * math.log2(e[1] / sa) for e in events]
    vel = weights(semis, [round(s) % 12 in stress_notes for s in semis])
    out, prev_s = [], None
    for i, (t, f, d, o, *_rest) in enumerate(events):
        exact = guard_from is not None and t >= guard_from - 1e-6
        t2 = t if exact else max(0.0, t + offs[i])
        g = glide_time(semis[i] - prev_s, d) if (o == 1 and prev_s is not None) else 0.0
        out.append([round(t2, 3), round(f, 2), d, o, vel[i], g])
        prev_s = semis[i]
    return out


# ---------------------------------------------------------------- real Box2D backend
def _spring_world(k: float, m: float, zeta: float):
    """A static ground and one dynamic body joined by a wheel-joint spring along x (Box2D's soft constraint)."""
    w = _b2.b2World(gravity=(0, 0), doSleep=False)
    ground = w.CreateStaticBody(position=(0, 0))
    bob = w.CreateDynamicBody(position=(0, 0), fixedRotation=True, linearDamping=0.0)
    bob.CreateCircleFixture(radius=0.1, density=m / (math.pi * 0.01), friction=0.0)
    freq = math.sqrt(k / m) / (2 * math.pi)
    w.CreateWheelJoint(bodyA=ground, bodyB=bob, anchor=(0, 0), axis=(1, 0), enableMotor=False, frequencyHz=freq, dampingRatio=zeta)
    return w, bob


def _b2_rubato(events: list[list], beat: float, seed: int, limit_ms: float = 28.0) -> list[float]:
    rng = random.Random(seed ^ 0x5EED)
    w, bob = _spring_world(14.0, 1.0, 0.3)
    out, t_prev = [], 0.0
    for t, _f, d, _o, *_ in events:
        for _ in range(min(int(max(0.0, t - t_prev) / (1 / 120.0)), 2400)):
            w.Step(1 / 120.0, 8, 3)
        t_prev = t
        kick = rng.uniform(0.12, 0.22) if d >= 1.6 * beat else rng.uniform(-0.03, 0.05)   # held note: phrase end, lean back
        bob.ApplyLinearImpulse((kick * SCALE, 0), bob.worldCenter, True)
        out.append(max(-limit_ms, min(limit_ms, bob.position.x / SCALE * 1000.0)) / 1000.0)
    return out


def _b2_weights(pitches: list[float], stress: list[bool]) -> list[float]:
    if not pitches:
        return []
    lo, hi = min(pitches), max(pitches)
    span = (hi - lo) or 1.0
    out, prev = [], (pitches[0] - lo) / span
    for p, s in zip(pitches, stress):
        h = (p - lo) / span
        drop = (abs(h - prev) * 1.2 + 0.08) * 4.0           # metres: a leap is a long fall
        w = _b2.b2World(gravity=(0, -9.8), doSleep=False)
        ground = w.CreateStaticBody(position=(0, 0))
        ground.CreateEdgeFixture(vertices=[(-5, 0), (5, 0)], friction=0.4, restitution=0.35)
        ball = w.CreateDynamicBody(position=(0, drop + 0.1))
        ball.CreateCircleFixture(radius=0.1, density=1.0, restitution=0.35, friction=0.3)
        fall = 0.0
        for _ in range(360):
            w.Step(1 / 120.0, 8, 3)
            fall = max(fall, -ball.linearVelocity.y)           # speed just before it hits the floor
            if ball.linearVelocity.y > 0:                      # it has bounced: the impact happened
                break
        v = min(1.0, 0.62 + 0.34 * min(1.0, (fall / 4.0) / 3.2) + (0.06 if s else 0.0))
        out.append(round(v, 3))
        prev = h
    return out


def _b2_glide_time(interval_semitones: float, available: float) -> float:
    interval = abs(interval_semitones)
    if interval < 1:
        return 0.0
    m = 0.6 + 0.12 * interval
    w, bob = _spring_world(900.0, m, 1.0)                      # critically damped: no overshoot
    bob.position = (interval, 0)                               # displaced from rest by the interval; the joint pulls it home
    n = 0
    while abs(bob.position.x) > 0.04 * interval and n < 960:
        w.Step(DT, 8, 3)
        n += 1
    return round(min(n * DT, 0.30, available * 0.5), 3)


def _b2_drift_cents(n: int, seed: int, amount: float = 7.0) -> list[float]:
    rng = random.Random(seed ^ 0xD71F7)
    w, bob = _spring_world(30.0, 1.0, 0.36)
    out = []
    for _ in range(n):
        bob.ApplyLinearImpulse((rng.gauss(0, 0.9) * SCALE * 0.4, 0), bob.worldCenter, True)
        for _ in range(30):
            w.Step(1 / 120.0, 8, 3)
        out.append(max(-amount, min(amount, bob.position.x / SCALE * amount * 3 * 2.5)))
    return out


def rubato(*a, **k): return (_b2_rubato if _b2 else _py_rubato)(*a, **k)
def weights(*a, **k): return (_b2_weights if _b2 else _py_weights)(*a, **k)
def glide_time(*a, **k): return (_b2_glide_time if _b2 else _py_glide_time)(*a, **k)
def drift_cents(*a, **k): return (_b2_drift_cents if _b2 else _py_drift_cents)(*a, **k)
