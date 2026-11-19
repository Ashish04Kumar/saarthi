"""Animation: a Pose for every Saarthi state at time t (seconds into the loop)."""

from __future__ import annotations

import math
from dataclasses import replace

from model import Pose

TAU = 2 * math.pi

# state: (frames, fps, loop)
STATES = {
    "idle": (24, 10, True),
    "typing_fast": (12, 12, True),
    "typing_slow": (20, 8, True),
    "scrolling": (16, 8, True),
    "watching": (24, 8, True),
    "afk": (16, 6, True),
    "sleeping": (18, 6, True),
    "waking": (14, 12, False),
    "happy": (16, 12, True),
    "stretch": (24, 8, True),
    "alert": (12, 8, True),
    "poked": (16, 10, False),
    "giggle": (12, 12, True),
    "break": (24, 6, True),
    "breathe": (48, 4, True),  # 12 s = one breath (in 4, hold 2, out 6)
    "walk": (16, 12, True),  # walking to the viewer's right; the app mirrors it for left
    "eat": (24, 8, True),  # lunch from a tiffin, spoon to mouth, chewing
    "think": (20, 6, True),  # hand on chin, looking up, thought bubble
}


def stand(bob=0.0) -> Pose:
    b = bob
    return Pose(hip=(0, 0.66 + b * 0.3, 0), chest=(0, 1.02 + b, 0), head=(0, 1.52 + b, 0),
                sh_a=(-0.31, 1.06 + b, 0), sh_b=(0.31, 1.06 + b, 0),
                el_a=(-0.40, 0.84 + b, 0.0), el_b=(0.40, 0.84 + b, 0.0),
                wr_a=(-0.44, 0.62 + b, 0.06), wr_b=(0.44, 0.62 + b, 0.06))


def sit(bob=0.0, lean=0.0) -> Pose:
    b = bob
    return Pose(
        hip=(0, 0.24, 0), chest=(0, 0.60 + b, -lean), head=(0, 1.10 + b, 0.02 - lean * 1.6),
        head_rot=(0.12, 0, 0),
        sh_a=(-0.31, 0.64 + b, -lean), sh_b=(0.31, 0.64 + b, -lean),
        el_a=(-0.36, 0.42, 0.14), el_b=(0.36, 0.42, 0.14),
        wr_a=(-0.13, 0.36, 0.30), wr_b=(0.13, 0.36, 0.30),
        hip_a=(-0.13, 0.20, 0.05), kn_a=(-0.38, 0.14, 0.25), an_a=(0.10, 0.09, 0.36),
        hip_b=(0.13, 0.20, 0.05), kn_b=(0.38, 0.14, 0.25), an_b=(-0.10, 0.09, 0.40),
        foot_dir_a=(1, 0, 0.2), foot_dir_b=(-1, 0, 0.2),
        props={"laptop": True, "glow": 0.35},
    )


def add(t3, dx=0.0, dy=0.0, dz=0.0):
    return (t3[0] + dx, t3[1] + dy, t3[2] + dz)


def pose_for(state: str, t: float) -> Pose:
    frames, fps, loop = STATES[state]
    period = frames / fps
    ph = (t / period) % 1.0 if loop else min(t / period, 1.0)
    s = math.sin(TAU * ph)
    c = math.cos(TAU * ph)

    if state == "idle":
        p = stand(0.012 * s)
        look_cycle = (ph * 3) % 3
        lx = -0.7 if look_cycle < 1 else (0.7 if look_cycle < 2 else 0.0)
        p = replace(p, look=(lx, 0.1), head_rot=(0.0, lx * 0.15, 0.03 * s), mouth="smile")
        p.wr_b = add(p.wr_b, dz=0.02 * c)
        if 0.45 < ph < 0.5:
            p.eyes = "closed"
        return p

    if state == "typing_fast":
        p = sit(0.008 * math.sin(TAU * ph * 2))
        k = math.sin(TAU * ph * 3)
        p.wr_a = add(p.wr_a, dy=0.03 * max(k, 0))
        p.wr_b = add(p.wr_b, dy=0.03 * max(-k, 0))
        p.el_a = add(p.el_a, dy=0.015 * max(k, 0))
        p.el_b = add(p.el_b, dy=0.015 * max(-k, 0))
        p.look, p.mouth, p.brows = (0.0, -0.9), "grin", "determined"
        p.head_rot = (0.2, 0, 0)
        p.props["sweat"] = ph
        return p

    if state == "typing_slow":
        p = sit(0.006 * s)
        thinking = ph < 0.6
        if thinking:
            p.wr_b = (0.30, 0.86, 0.30)  # hand on chin-ish
            p.el_b = (0.40, 0.55, 0.22)
            p.look, p.brows, p.mouth = (0.6, 0.8), "one", "small"
            p.head_rot = (-0.05, 0.12, 0.08)
            p.props["thought"] = 1 + int(ph / 0.2)
        else:
            tap = math.sin(TAU * ph * 4)
            p.wr_a = add(p.wr_a, dy=0.025 * max(tap, 0))
            p.look, p.mouth = (0.0, -0.9), "flat"
            p.head_rot = (0.2, 0, 0)
        return p

    if state == "scrolling":
        p = sit(0.004 * s)
        p.wr_b = add(p.wr_b, dx=-0.08, dz=0.08 + 0.05 * s)
        p.el_b = add(p.el_b, dz=0.03 * s)
        p.wr_a = (-0.36, 0.30, 0.18)
        p.el_a = (-0.40, 0.42, 0.06)
        p.look = (0.1, -0.2 + 0.7 * s)
        p.mouth, p.brows = "flat", "neutral"
        p.head_rot = (0.12 - 0.06 * s, 0, 0)
        return p

    if state == "watching":
        p = sit(0.005 * s, lean=0.05)
        p.props.update(popcorn=True, glow=0.9)
        dip = max(0.0, math.sin(TAU * ph)) ** 2
        # right-side hand (b) goes bucket -> mouth -> back
        bucket = (0.58, 0.32, 0.22)
        mouth = (0.12, 0.98, 0.30)
        p.wr_b = tuple(bucket[i] + (mouth[i] - bucket[i]) * dip for i in range(3))
        p.el_b = (0.44, 0.50 + 0.15 * dip, 0.10)
        p.wr_a = (-0.36, 0.30, 0.18)
        p.el_a = (-0.40, 0.42, 0.06)
        p.look = (0.0, -0.3)
        p.mouth = "o" if dip > 0.8 else "smile"
        p.brows = "raised" if 0.3 < ph < 0.4 else "neutral"
        p.head_rot = (0.06, 0, 0)
        return p

    if state == "afk":
        p = sit(0.004 * s)
        nod = max(0.0, math.sin(TAU * ph)) ** 3
        p.head_rot = (0.15 + 0.25 * nod, 0, 0.05)
        p.wr_a = (-0.36, 0.30, 0.18)
        p.el_a = (-0.40, 0.42, 0.06)
        p.wr_b = (0.36, 0.30, 0.18)
        p.el_b = (0.40, 0.42, 0.06)
        p.eyes, p.brows, p.mouth = ("closed" if nod > 0.6 else "half"), "sleepy", "flat"
        p.props["glow"] = 0.15
        return p

    if state == "sleeping":
        p = sit(0.01 * s)
        p.head_rot = (0.35, 0.0, 0.35)
        p.head = add(p.head, dx=0.04, dy=-0.04)
        p.wr_a = (-0.36, 0.30, 0.18)
        p.el_a = (-0.40, 0.42, 0.06)
        p.wr_b = (0.36, 0.30, 0.18)
        p.el_b = (0.40, 0.42, 0.06)
        p.eyes, p.brows, p.mouth = "closed", "sleepy", "o"
        p.props.update(zzz=ph, glow=0.0)
        return p

    if state == "waking":
        hop = math.sin(math.pi * min(ph * 1.4, 1.0))
        p = stand()
        p.offset = (0, 0.10 * hop, 0)
        up = min(1.0, ph * 2)
        for side, sx in (("a", -1), ("b", 1)):
            setattr(p, f"el_{side}", (0.44 * sx, 0.84 + 0.35 * up, 0.02))
            setattr(p, f"wr_{side}", (0.50 * sx, 0.62 + 0.75 * up, 0.04))
        p.eyes, p.brows, p.mouth = "wide", "raised", "open"
        p.props["bang"] = ph > 0.15
        return p

    if state == "happy":
        hop = abs(math.sin(TAU * ph))
        p = stand()
        p.offset = (0, 0.05 * hop, 0)
        wave = math.sin(TAU * ph * 2)
        p.el_b = (0.54, 1.14, 0.12)
        p.wr_b = (0.66 + 0.09 * wave, 1.42, 0.16)
        p.eyes, p.mouth = "happy", "grin"
        p.head_rot = (0, 0.1, -0.06 * wave)
        return p

    if state == "stretch":
        k = (1 - math.cos(TAU * ph)) / 2  # 0 -> 1 -> 0
        p = stand(0.03 * k)
        for side, sx in (("a", -1), ("b", 1)):
            setattr(p, f"el_{side}", (0.40 * sx - 0.06 * sx * k, 0.84 + 0.62 * k, 0.0))
            setattr(p, f"wr_{side}", (0.44 * sx - 0.30 * sx * k, 0.62 + 1.30 * k, 0.04))
        p.head_rot = (-0.15 * k, 0, 0)
        p.eyes = "closed" if k > 0.4 else "open"
        p.mouth = "open" if k > 0.5 else "smile"
        return p

    if state == "alert":
        p = stand(0.01 * s)
        sway = 0.02 * s
        p.el_a = (-0.44, 1.30, 0.05)
        p.wr_a = (-0.32 + sway, 1.90, 0.08)
        p.el_b = (0.44, 1.30, 0.05)
        p.wr_b = (0.32 + sway, 1.90, 0.08)
        p.eyes, p.brows, p.mouth = "wide", "raised", "o"
        p.props["sign"] = True
        return p

    if state == "eat":
        p = sit(0.004 * s)
        p.props = {"glow": 0.0, "plate": True}
        bite = max(0.0, math.sin(TAU * ph)) ** 2
        plate_c, mouth_c = (0.10, 0.40, 0.36), (0.08, 0.93, 0.38)
        sp = tuple(plate_c[i] + (mouth_c[i] - plate_c[i]) * bite for i in range(3))
        p.wr_b = (sp[0] + 0.06, sp[1] - 0.03, sp[2] - 0.03)
        p.el_b = (0.40, 0.48 + 0.22 * bite, 0.12)
        p.wr_a = (-0.16, 0.40, 0.32)  # holding the plate
        p.el_a = (-0.38, 0.44, 0.12)
        p.props["spoon"] = sp
        chew = math.sin(TAU * ph * 4) > 0
        p.mouth = "o" if bite > 0.7 else ("small" if chew else "smile")
        p.eyes = "happy" if bite > 0.85 else "open"
        p.look = (0.0, -0.8 + 0.8 * bite)
        p.head_rot = (0.18 - 0.15 * bite, 0, 0)
        return p

    if state == "think":
        p = stand(0.01 * s)
        p.el_b = (0.36, 0.92, 0.22)
        p.wr_b = (0.14, 1.26, 0.34)  # hand on the chin
        p.el_a = (-0.30, 0.86, 0.20)
        p.wr_a = (0.06, 0.92, 0.28)  # arm across the belly
        p.head_rot = (-0.12, 0.15, 0.06 + 0.03 * s)
        p.look = (0.7, 0.8)
        p.eyes, p.brows, p.mouth = "open", "one", "small"
        p.props = {"thought": 1 + int(ph * 3) % 3}
        return p

    if state == "walk":
        sw = math.sin(TAU * ph)
        p = stand()
        p.body_yaw = math.radians(62)
        p.offset = (0, 0.025 * abs(math.sin(TAU * ph * 2)), 0)
        for side, sx, k in (("a", -1, sw), ("b", 1, -sw)):
            lift = max(0.0, math.cos(TAU * ph) * (1 if side == "a" else -1))
            setattr(p, f"kn_{side}", (0.13 * sx, 0.36 + 0.04 * lift, 0.04 + 0.12 * k))
            setattr(p, f"an_{side}", (0.13 * sx, 0.12 + 0.07 * lift, 0.20 * k))
            setattr(p, f"el_{side}", (0.40 * sx, 0.84, -0.10 * k))
            setattr(p, f"wr_{side}", (0.42 * sx, 0.64, -0.20 * k + 0.04))
        p.head_rot = (0.02, -0.35, 0.03 * sw)  # glance a bit towards the viewer
        p.look = (-0.6, 0.0)
        p.mouth = "smile"
        return p

    if state == "poked":
        k = math.exp(-3.0 * t) * math.sin(14 * t)  # recoil wobble
        p = stand()
        p.offset = (0, -0.02 * abs(k), 0)
        p.head_rot = (0.05, 0.0, 0.25 * k + 0.08)
        rub = 0.03 * math.sin(t * 22)
        p.el_b = (0.48, 1.28, 0.10)
        p.wr_b = (0.30 + rub, 1.84, 0.12)
        p.eyes, p.brows, p.mouth = ("closed" if t < 1.0 else "open"), "determined", "o"
        return p

    if state == "giggle":
        p = stand(0.01 * math.sin(TAU * ph * 4))
        p.offset = (0.025 * math.sin(TAU * ph * 3), 0.015 * abs(math.sin(TAU * ph * 3)), 0)
        p.el_a, p.wr_a = (-0.36, 0.90, 0.16), (-0.14, 0.84, 0.30)
        p.el_b, p.wr_b = (0.36, 0.90, 0.16), (0.14, 0.82, 0.30)
        p.head_rot = (-0.12, 0, 0.08 * math.sin(TAU * ph * 3))
        p.eyes, p.mouth = "happy", "grin"
        return p

    if state == "break":
        p = sit(0.006 * s, lean=0.04)
        p.props = {"glow": 0.0}
        sip = max(0.0, math.sin(TAU * ph)) ** 3
        rest_c, mouth_c = (0.26, 0.50, 0.36), (0.10, 0.92, 0.40)
        cup = tuple(rest_c[i] + (mouth_c[i] - rest_c[i]) * sip for i in range(3))
        p.wr_b = (cup[0] + 0.07, cup[1] - 0.02, cup[2] - 0.02)
        p.el_b = (0.42, 0.50 + 0.25 * sip, 0.10)
        p.wr_a = (-0.36, 0.30, 0.18)
        p.el_a = (-0.40, 0.42, 0.06)
        p.props.update(cup=cup, steam=ph * 2 % 1.0)
        p.eyes = "closed" if sip > 0.5 else "half"
        p.mouth = "small" if sip > 0.5 else "smile"
        p.brows = "sleepy"
        p.head_rot = (0.0 - 0.1 * sip, 0, 0.05)
        return p

    if state == "breathe":
        from_t = t % 12.0
        if from_t < 4:
            x = from_t / 4
            lvl = x * x * (3 - 2 * x)
        elif from_t < 6:
            lvl = 1.0
        else:
            x = (from_t - 6) / 6
            lvl = 1 - x * x * (3 - 2 * x)
        p = stand(0.03 * lvl)
        for side, sx in (("a", -1), ("b", 1)):
            setattr(p, f"el_{side}", (sx * (0.42 + 0.10 * lvl), 0.86 + 0.22 * lvl, 0.04))
            setattr(p, f"wr_{side}", (sx * (0.46 + 0.22 * lvl), 0.66 + 0.48 * lvl, 0.10))
        p.head_rot = (-0.10 * lvl, 0, 0)
        p.eyes = "closed"
        p.mouth = "o" if from_t >= 6 else "small"
        return p

    raise KeyError(state)
