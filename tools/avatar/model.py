"""The avatar: appearance (Look), skeleton pose (Pose) and the SDF scene built from them."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from engine import (
    Group,
    Material,
    Part,
    V,
    box,
    capsule,
    cylinder,
    ellipsoid,
    length,
    rot_x,
    rot_y,
    rot_z,
    smin,
    smin_all,
    sphere,
)

# material ids
SKIN, HAIR, BEARD, SHIRT, PANTS, SHOES, EYE, PUPIL, LIPS, MOUTH = range(1, 11)
LAPTOP, SCREEN, WHITE, BUCKET, POPCORN, RED, SIGN, WATER, ZZZ, BUTTON = range(11, 21)
IRIS, FADE, TEA, DIAL, STRAP = 21, 22, 23, 24, 25


@dataclass
class Look:
    """Edit these to make your own avatar."""

    skin: tuple = (0.77, 0.55, 0.41)
    hair: tuple = (0.08, 0.06, 0.05)
    beard: tuple = (0.14, 0.10, 0.08)
    shirt: tuple = (0.95, 0.90, 0.62)
    pants: tuple = (0.18, 0.21, 0.30)
    shoes: tuple = (0.30, 0.20, 0.14)
    has_beard: bool = True
    has_moustache: bool = True
    quiff: float = 0.4  # 0 = flat hair, 1 = tall styled quiff
    sleeves: str = "rolled"  # full / rolled / short
    slim: float = 1.0  # 0 = round chibi body, 1 = slim
    iris: tuple = (0.30, 0.18, 0.10)
    face_width: float = 0.90  # 1 = round, smaller = slimmer face
    watch: bool = True  # wristwatch on the left wrist
    beard_thickness: float = 0.016


def materials(look: Look) -> dict:
    def bucket(p):
        ang = np.arctan2(p[:, 2] - BUCKET_C[2], p[:, 0] - BUCKET_C[0])
        red = np.sin(ang * 7) > 0
        return np.where(red[:, None], np.array([0.90, 0.20, 0.24]), np.array([0.98, 0.97, 0.95]))

    return {
        SKIN: Material(look.skin, 0.06),
        HAIR: Material(look.hair, 0.35),
        BEARD: Material(look.beard, 0.08),
        SHIRT: Material(look.shirt, 0.05),
        PANTS: Material(look.pants, 0.05),
        SHOES: Material(look.shoes, 0.4),
        EYE: Material((0.97, 0.97, 0.96), 0.6),
        PUPIL: Material((0.09, 0.06, 0.05), 0.9),
        LIPS: Material((0.46, 0.29, 0.25), 0.15),
        MOUTH: Material((0.33, 0.07, 0.09), 0.1),
        LAPTOP: Material((0.42, 0.45, 0.52), 0.6),
        SCREEN: Material((0.55, 0.85, 1.0), 0, True),
        WHITE: Material((0.98, 0.98, 0.98), 0.1),
        BUCKET: Material(bucket, 0.2),
        POPCORN: Material((1.0, 0.93, 0.68), 0.05),
        RED: Material((0.95, 0.22, 0.26), 0.3),
        SIGN: Material((1.0, 0.83, 0.25), 0.2),
        WATER: Material((0.50, 0.80, 1.0), 0.9),
        ZZZ: Material((0.50, 0.55, 1.0), 0.3),
        BUTTON: Material((0.80, 0.72, 0.45), 0.5),
        IRIS: Material(look.iris, 0.9),
        TEA: Material((0.58, 0.34, 0.18), 0.3),
        DIAL: Material((0.86, 0.88, 0.92), 1.0),
        STRAP: Material((0.10, 0.09, 0.10), 0.4),
        FADE: Material(tuple(h * 0.78 + s * 0.22 for h, s in zip(look.hair, look.skin, strict=False)), 0.05),
    }


BUCKET_C = V(0.62, 0.13, 0.22)


@dataclass
class Pose:
    offset: tuple = (0.0, 0.0, 0.0)  # whole-body move (hops)
    body_yaw: float = 0.0  # turn the whole body (radians), e.g. to walk sideways
    hip: tuple = (0, 0.66, 0)
    chest: tuple = (0, 1.02, 0)
    head: tuple = (0, 1.52, 0)
    head_rot: tuple = (0.0, 0.0, 0.0)  # pitch (+ = look down), yaw, roll (radians)
    # a = character's right (viewer's left, -x), b = character's left (+x)
    sh_a: tuple = (-0.31, 1.06, 0)
    el_a: tuple = (-0.40, 0.84, 0.0)
    wr_a: tuple = (-0.44, 0.62, 0.06)
    sh_b: tuple = (0.31, 1.06, 0)
    el_b: tuple = (0.40, 0.84, 0.0)
    wr_b: tuple = (0.44, 0.62, 0.06)
    hip_a: tuple = (-0.13, 0.60, 0)
    kn_a: tuple = (-0.14, 0.35, 0.03)
    an_a: tuple = (-0.14, 0.12, 0)
    hip_b: tuple = (0.13, 0.60, 0)
    kn_b: tuple = (0.14, 0.35, 0.03)
    an_b: tuple = (0.14, 0.12, 0)
    foot_dir_a: tuple = (0, 0, 1)
    foot_dir_b: tuple = (0, 0, 1)
    eyes: str = "open"  # open / closed / half / wide / happy
    look: tuple = (0.0, 0.0)
    mouth: str = "smile"  # smile / flat / o / open / grin / small
    brows: str = "neutral"  # neutral / determined / raised / one / sleepy
    props: dict = field(default_factory=dict)


def _v(t, off):
    return V(*t) + off


# ---------------- head (built in head-local space, origin at head centre) ----------------

def head_parts(pose: Pose, look: Look):
    parts = []
    parts.append(Part(SKIN, lambda p: smin(
        smin(ellipsoid(p, V(0, 0, 0), V(0.40, 0.44, 0.38)),
             ellipsoid(p, V(0, -0.19, 0.07), V(0.28, 0.19, 0.28)), 0.08),
        smin(ellipsoid(p, V(-0.392, 0.0, -0.02), V(0.042, 0.078, 0.052)),
             ellipsoid(p, V(0.392, 0.0, -0.02), V(0.042, 0.078, 0.052)), 0.01), 0.03)))
    parts.append(Part(SKIN, lambda p: ellipsoid(p, V(0, -0.01, 0.385), V(0.055, 0.075, 0.06))))  # nose

    # hair: a cap with a hairline that sits higher at the front, plus a styled quiff
    q = look.quiff

    def hair(p):
        cap = ellipsoid(p, V(0, 0.01, -0.01), V(0.407, 0.455, 0.392))
        z, x = p[:, 2], np.abs(p[:, 0])
        line = 0.24 + 0.06 * np.clip(z / 0.4, 0, 1) - 0.04 * np.clip(-z / 0.4, 0, 1)
        line = line + 0.05 * np.clip((x - 0.25) / 0.12, 0, 1)
        cap = np.maximum(cap, line - p[:, 1])
        # volume on top: brushed up at the front, flowing back to the crown
        top = ellipsoid(p, V(0.0, 0.31 + 0.04 * q, 0.06), V(0.27, 0.10 + 0.04 * q, 0.30))
        front = ellipsoid(p, V(-0.02, 0.35 + 0.07 * q, 0.22), V(0.22, 0.08 + 0.05 * q, 0.13))
        flick = ellipsoid(p, V(0.05, 0.38 + 0.08 * q, 0.27), V(0.12, 0.05 + 0.03 * q, 0.08))
        return smin(smin(smin(cap, top, 0.10), front, 0.07), flick, 0.05)

    parts.append(Part(HAIR, hair))

    def fade(p):  # very short buzzed hair on the sides and back
        shell = ellipsoid(p, V(0, 0, -0.004), V(0.405, 0.446, 0.386))
        z, x = p[:, 2], np.abs(p[:, 0])
        region = np.maximum(-0.06 - p[:, 1], p[:, 1] - 0.32)  # band between temple and crown
        front_cut = np.where(x > 0.3, z - 0.12, z)  # keep it off the face
        return np.maximum(np.maximum(shell, region), front_cut)

    parts.append(Part(FADE, fade))

    if look.has_beard:
        def beard(p):
            T = look.beard_thickness
            b = smin(ellipsoid(p, V(0, 0, 0), V(0.40 + T, 0.44 + T, 0.38 + T)),
                     ellipsoid(p, V(0, -0.19, 0.075), V(0.28 + T, 0.19 + T * 1.8, 0.28 + T * 1.4)), 0.08)
            z = p[:, 2]
            # sideburn strip in front of the ear, then a diagonal cheek line down to the mouth corner
            cheek = -0.04 - 0.28 * np.clip(z - 0.06, 0.0, 0.26)
            top = np.where(z < 0.06, 0.06, cheek)
            b = np.maximum(b, p[:, 1] - top)
            # nothing behind the ear, except under the jaw
            behind = np.where(p[:, 1] < -0.30, -0.25 - z, -0.07 - z)
            return np.maximum(b, behind)

        parts.append(Part(BEARD, beard))
    if look.has_moustache:
        parts.append(Part(BEARD, lambda p: smin(
            capsule(p, V(0.0, -0.092, 0.396), V(-0.10, -0.125, 0.362), 0.024, 0.02),
            capsule(p, V(0.0, -0.092, 0.396), V(0.10, -0.125, 0.362), 0.024, 0.02), 0.02)))

    # mouth (sits on the beard)
    mz, my = 0.398, -0.168
    m = pose.mouth
    if m == "smile":
        parts.append(Part(LIPS, lambda p: smin_all([
            capsule(p, V(-0.08, my + 0.02, mz - 0.018), V(-0.03, my, mz), 0.013),
            capsule(p, V(-0.03, my, mz), V(0.03, my, mz), 0.014),
            capsule(p, V(0.03, my, mz), V(0.08, my + 0.02, mz - 0.018), 0.013)], 0.01)))
    elif m == "flat":
        parts.append(Part(LIPS, lambda p: capsule(p, V(-0.055, my + 0.005, mz - 0.005), V(0.055, my + 0.005, mz - 0.005),
                                                  0.012)))
    elif m == "small":
        parts.append(Part(LIPS, lambda p: capsule(p, V(-0.03, my, mz), V(0.03, my, mz), 0.013)))
    elif m == "o":
        parts.append(Part(MOUTH, lambda p: ellipsoid(p, V(0, my - 0.01, mz - 0.005), V(0.035, 0.045, 0.03))))
    elif m in ("open", "grin"):
        w = 0.085 if m == "grin" else 0.06
        h = 0.04 if m == "grin" else 0.055

        parts.append(Part(MOUTH, lambda p: np.maximum(ellipsoid(p, V(0, my - 0.02, mz - 0.01), V(w, h, 0.035)),
                                                      p[:, 1] - (my + 0.01))))
        parts.append(Part(WHITE, lambda p: np.maximum(ellipsoid(p, V(0, my - 0.005, mz - 0.006), V(w * 0.8, 0.018,
                                                                                                    0.03)),
                                                      p[:, 1] - (my + 0.012))))

    # eyes: almond shaped, brown iris, upper lash line
    lx, ly = pose.look
    for side in (-1, 1):
        ex, ey = 0.14 * side, 0.04
        e = pose.eyes
        if e in ("open", "wide", "half"):
            h = 0.058 if e == "wide" else 0.046
            c = V(ex, ey, 0.335)
            parts.append(Part(EYE, lambda p, c=c, h=h: ellipsoid(p, c, V(0.072, h, 0.04))))
            ic = c + V(lx * 0.022, ly * 0.012, 0.03)
            parts.append(Part(IRIS, lambda p, ic=ic: ellipsoid(p, ic, V(0.034, 0.036, 0.016))))
            parts.append(Part(PUPIL, lambda p, ic=ic: sphere(p, ic + V(0, 0, 0.008), 0.015)))
            lid_y = ey + h * 0.85
            parts.append(Part(HAIR, lambda p, ex=ex, ey=ey, ly_=lid_y: smin(
                capsule(p, V(ex - 0.078, ey + 0.002, 0.345), V(ex - 0.01, ly_, 0.372), 0.011),
                capsule(p, V(ex - 0.01, ly_, 0.372), V(ex + 0.078, ey + 0.012, 0.345), 0.011), 0.01)))
            if e == "half":
                parts.append(Part(SKIN, lambda p, c=c, h=h: np.maximum(ellipsoid(p, c, V(0.078, h + 0.01, 0.046)),
                                                                     (c[1] - 0.004) - p[:, 1])))
        elif e == "closed":
            parts.append(Part(HAIR, lambda p, ex=ex, ey=ey: smin(
                capsule(p, V(ex - 0.07, ey + 0.005, 0.35), V(ex, ey - 0.018, 0.372), 0.011),
                capsule(p, V(ex, ey - 0.018, 0.372), V(ex + 0.07, ey + 0.005, 0.35), 0.011), 0.01)))
        elif e == "happy":
            parts.append(Part(HAIR, lambda p, ex=ex, ey=ey: smin(
                capsule(p, V(ex - 0.07, ey - 0.015, 0.35), V(ex, ey + 0.022, 0.372), 0.012),
                capsule(p, V(ex, ey + 0.022, 0.372), V(ex + 0.07, ey - 0.015, 0.35), 0.012), 0.01)))

    # eyebrows (thick)
    b = pose.brows
    for side in (-1, 1):
        x_in, x_out = 0.06 * side, 0.23 * side
        y = 0.15
        yi, yo = y, y + 0.01
        if b == "determined":
            yi, yo = y - 0.035, y + 0.02
        elif b == "raised":
            yi, yo = y + 0.05, y + 0.045
        elif b == "one":
            if side > 0:
                yi, yo = y + 0.06, y + 0.04
        elif b == "sleepy":
            yi, yo = y - 0.01, y - 0.03
        a, c = V(x_in, yi, 0.372), V(x_out, yo, 0.325)
        parts.append(Part(HAIR, lambda p, a=a, c=c: capsule(p, a, c, 0.026, 0.017)))
    return parts


# ---------------- whole scene ----------------

def build(pose: Pose, look: Look):
    off = V(*pose.offset)
    J = {k: _v(getattr(pose, k), off) for k in (
        "hip", "chest", "head", "sh_a", "el_a", "wr_a", "sh_b", "el_b", "wr_b",
        "hip_a", "kn_a", "an_a", "hip_b", "kn_b", "an_b")}
    parts = []

    pitch, yaw, roll = pose.head_rot
    R = (rot_y(yaw) @ rot_x(pitch) @ rot_z(roll)).astype(np.float32)
    hc = J["head"]
    parts.append(Group(head_parts(pose, look), hc, 0.72, origin=hc, R=R, scale=(look.face_width, 1.0, 0.96)))

    neck_top = hc + R @ V(0, -0.30, -0.02)
    parts.append(Part(SKIN, lambda p: capsule(p, J["chest"] + V(0, 0.04, 0), neck_top, 0.10)))

    sleeve_end = {"full": 1.0, "rolled": 0.32, "short": -0.4}.get(look.sleeves, 1.0)
    k = look.slim
    tr = 0.25 - 0.04 * k  # torso radius
    sh_off = 0.0 - 0.02 * k

    def shirt(p):
        torso = smin(
            capsule(p, J["hip"] + V(-0.07, 0.02, 0), J["chest"] + V(-0.09, 0, 0), tr),
            capsule(p, J["hip"] + V(0.07, 0.02, 0), J["chest"] + V(0.09, 0, 0), tr), 0.08)
        torso = smin(torso, ellipsoid(p, J["chest"] + V(0, 0.0, 0.04), V(0.30 - 0.03 * k, 0.17, 0.22 - 0.03 * k)),
                     0.05)
        arms = []
        for s in ("a", "b"):
            sh, el, wr = J[f"sh_{s}"], J[f"el_{s}"], J[f"wr_{s}"]
            sh = sh + V(sh_off if s == "b" else -sh_off, 0, 0)
            arms.append(sphere(p, sh, 0.10 - 0.008 * k))
            if sleeve_end < 0:  # short sleeves end mid upper arm
                arms.append(capsule(p, sh, sh + (el - sh) * 0.6, 0.092, 0.088))
                continue
            arms.append(capsule(p, sh, el, 0.088 - 0.008 * k, 0.078 - 0.006 * k))
            fore_end = el + (wr - el) * sleeve_end
            arms.append(capsule(p, el, fore_end, 0.077 - 0.006 * k, 0.074 - 0.006 * k))
            if look.sleeves == "rolled":  # the rolled cuff
                a0 = el + (wr - el) * (sleeve_end - 0.12)
                arms.append(capsule(p, a0, fore_end, 0.084 - 0.004 * k))
        d = smin(torso, smin_all(arms, 0.03), 0.06)
        # collar
        nt = J["chest"] + V(0, 0.08, 0.0)
        for sx in (-1, 1):
            d = np.minimum(d, capsule(p, nt + V(0.03 * sx, 0.02, 0.15), nt + V(0.14 * sx, -0.04, 0.17), 0.04, 0.03))
        d = np.minimum(d, capsule(p, nt + V(-0.12, 0.03, -0.06), nt + V(0.12, 0.03, -0.06), 0.045))
        return d

    parts.append(Part(SHIRT, shirt))
    # buttons on the placket
    chest, hip = J["chest"], J["hip"]

    def buttons(p):
        d = np.full(len(p), 1e9, np.float32)
        for kk in (0.15, 0.45, 0.75):
            c = chest + (hip - chest) * kk
            d = np.minimum(d, sphere(p, c + V(0, 0, (0.255 if kk > 0.3 else 0.262) - 0.035 * look.slim), 0.015))
        return d

    parts.append(Part(BUTTON, buttons))

    # hands
    for s in ("a", "b"):
        el, wr = J[f"el_{s}"], J[f"wr_{s}"]
        dirv = (wr - el) / max(float(length(wr - el)), 1e-6)
        hand_c = wr + dirv * 0.055
        side = -1 if s == "a" else 1
        thumb_a = wr + dirv * 0.02
        thumb_b = thumb_a + V(0.0, 0.03, 0.06) + V(-0.03 * side, 0, 0)
        if look.sleeves != "full":
            parts.append(Part(SKIN, lambda p, el=el, wr=wr: capsule(p, el, wr, 0.06, 0.052)))
        parts.append(Part(SKIN, lambda p, hc=hand_c, ta=thumb_a, tb=thumb_b: smin(
            ellipsoid(p, hc, V(0.072, 0.082, 0.06)), capsule(p, ta, tb, 0.026), 0.02)))

    if look.watch:  # wristwatch on the character's left wrist ("b")
        el, wr = J["el_b"], J["wr_b"]
        d = (wr - el) / max(float(length(wr - el)), 1e-6)
        c = wr - d * 0.035
        out_dir = V(1.0, 0.0, 0.6)
        out_dir = out_dir - d * float(out_dir @ d)
        out_dir = out_dir / max(float(length(out_dir)), 1e-6)
        dial = c + out_dir * 0.058
        parts.append(Part(STRAP, lambda p, c=c, d=d: capsule(p, c - d * 0.016, c + d * 0.016, 0.066)))
        parts.append(Part(DIAL, lambda p, dial=dial: sphere(p, dial, 0.03)))

    def pants(p):
        hipline = capsule(p, J["hip_a"] + V(0.02, 0.03, 0), J["hip_b"] + V(-0.02, 0.03, 0), 0.17 - 0.025 * k)
        legs = []
        for s in ("a", "b"):
            legs.append(capsule(p, J[f"hip_{s}"], J[f"kn_{s}"], 0.12 - 0.015 * k, 0.105 - 0.012 * k))
            legs.append(capsule(p, J[f"kn_{s}"], J[f"an_{s}"], 0.105 - 0.012 * k, 0.09 - 0.008 * k))
        return smin(hipline, smin_all(legs, 0.03), 0.07)

    parts.append(Part(PANTS, pants))

    for s in ("a", "b"):
        an = J[f"an_{s}"]
        fd = V(*getattr(pose, f"foot_dir_{s}"))
        c = an + V(0, -0.045, 0) + fd * 0.07
        yaw_f = math.atan2(float(fd[0]), float(fd[2]))
        Rf = rot_y(yaw_f).astype(np.float32)
        parts.append(Part(SHOES, lambda p, c=c, Rf=Rf: ellipsoid((p - c) @ Rf, V(0, 0, 0), V(0.085, 0.06, 0.14))))

    parts += props(pose, J, R)
    if pose.body_yaw:
        return Group(parts, V(0, 1.2, 0), 50.0, origin=V(0, 0, 0), R=rot_y(pose.body_yaw).astype(np.float32))
    return Group(parts, V(0, 1.2, 0), 50.0)


def props(pose: Pose, J, R):
    pr = pose.props
    out = []
    hc = J["head"]
    if pr.get("laptop"):
        base_c = V(0, 0.30, 0.34)
        hinge = V(0, 0.315, 0.52)
        tilt = math.radians(14)
        lid_dir = V(0, math.cos(tilt), -math.sin(tilt))
        lid_c = hinge + lid_dir * 0.19
        Rl = rot_x(-tilt).astype(np.float32)
        out.append(Part(LAPTOP, lambda p: np.minimum(
            box(p, base_c, V(0.29, 0.012, 0.19), 0.008),
            box(p, lid_c, V(0.29, 0.185, 0.008), 0.008, Rl))))
        normal = Rl @ V(0, 0, -1)
        scr_c = lid_c + normal * 0.012
        out.append(Part(SCREEN, lambda p: box(p, scr_c, V(0.26, 0.16, 0.002), 0.002, Rl)))
        # a tiny logo on the back of the lid
        logo_c = lid_c - normal * 0.012
        out.append(Part(WHITE, lambda p: ellipsoid((p - logo_c) @ Rl, V(0, 0, 0), V(0.035, 0.035, 0.004))))
    if pr.get("cup") is not None:
        c = V(*pr["cup"])
        k = pr.get("steam", 0.0)
        items = [
            Part(WHITE, lambda p: np.minimum(
                cylinder(p, c, 0.072, 0.078, 0.012),
                np.minimum(capsule(p, c + V(0.065, 0.04, 0), c + V(0.11, 0.0, 0), 0.015),
                           capsule(p, c + V(0.11, 0.0, 0), c + V(0.065, -0.04, 0), 0.015)))),
            Part(TEA, lambda p: cylinder(p, c + V(0, 0.076, 0), 0.062, 0.005)),
        ]
        for i in range(3):
            kk = (k + i / 3) % 1.0
            sc = c + V(-0.02 + 0.02 * i + 0.015 * math.sin(kk * 6 + i), 0.10 + 0.22 * kk, 0)
            rr = 0.022 * (1 - kk) + 0.004
            items.append(Part(WHITE, lambda p, sc=sc, rr=rr: sphere(p, sc, rr)))
        out.append(Group(items, c + V(0, 0.12, 0), 0.32))
    if pr.get("plate"):
        pc = V(0.0, 0.33, 0.36)
        out.append(Group([
            Part(LAPTOP, lambda p: cylinder(p, pc, 0.20, 0.018, 0.01)),  # steel thali
            Part(POPCORN, lambda p: ellipsoid(p, pc + V(-0.06, 0.03, 0.0), V(0.09, 0.03, 0.08))),  # rice
            Part(TEA, lambda p: cylinder(p, pc + V(0.08, 0.02, -0.02), 0.06, 0.02, 0.008)),  # dal katori
            Part(SIGN, lambda p: ellipsoid(p, pc + V(0.02, 0.03, 0.10), V(0.07, 0.02, 0.035))),  # roti
        ], pc, 0.3))
    if pr.get("spoon") is not None:
        sc = V(*pr["spoon"])
        out.append(Part(LAPTOP, lambda p: np.minimum(capsule(p, sc, sc + V(0.10, -0.04, -0.03), 0.010),
                                                     ellipsoid(p, sc, V(0.028, 0.012, 0.02)))))
    if pr.get("popcorn"):
        out.append(Group([
            Part(BUCKET, lambda p: cylinder(p, BUCKET_C, 0.10, 0.12, 0.01)),
            Part(POPCORN, lambda p: np.minimum.reduce([
                sphere(p, BUCKET_C + V(dx, 0.13 + dy, dz), 0.045)
                for dx, dy, dz in ((-0.04, 0.0, 0.0), (0.04, 0.01, 0.02), (0.0, 0.03, -0.03), (0.0, 0.02, 0.05),
                                   (-0.05, 0.01, -0.04), (0.05, 0.0, -0.03))])),
        ], BUCKET_C + V(0, 0.05, 0), 0.25))
    if pr.get("sweat") is not None:
        k = pr["sweat"]
        c = hc + R @ V(0.37, 0.20 - 0.25 * k, 0.12)
        out.append(Part(WATER, lambda p: smin(sphere(p, c, 0.032), capsule(p, c, c + V(0, 0.06, 0), 0.032, 0.004),
                                               0.02)))
    if pr.get("thought") is not None:
        n = pr["thought"]
        base = hc + V(0.40, 0.42, 0.05)
        items = [Part(WHITE, lambda p: np.minimum.reduce([
            sphere(p, base, 0.035), sphere(p, base + V(0.08, 0.10, 0), 0.05),
            ellipsoid(p, base + V(0.25, 0.30, 0), V(0.22, 0.13, 0.07))]))]
        for i in range(n):
            dc = base + V(0.17 + i * 0.08, 0.30, 0.07)
            items.append(Part(PUPIL, lambda p, dc=dc: sphere(p, dc, 0.022)))
        out.append(Group(items, base + V(0.2, 0.25, 0), 0.5))
    if pr.get("zzz") is not None:
        k = pr["zzz"]
        letters = []
        for i in range(3):
            kk = (k + i / 3) % 1.0
            s = 0.07 + 0.05 * i + 0.03 * kk
            c = hc + V(0.30 + 0.12 * i + 0.1 * kk, 0.35 + 0.30 * kk + 0.1 * i, 0.05)
            if kk > 0.9:
                continue
            letters.append(Part(ZZZ, lambda p, c=c, s=s: np.minimum.reduce([
                capsule(p, c + V(-s / 2, s / 2, 0), c + V(s / 2, s / 2, 0), s * 0.13),
                capsule(p, c + V(s / 2, s / 2, 0), c + V(-s / 2, -s / 2, 0), s * 0.13),
                capsule(p, c + V(-s / 2, -s / 2, 0), c + V(s / 2, -s / 2, 0), s * 0.13)])))
        if letters:
            out.append(Group(letters, hc + V(0.45, 0.6, 0.05), 0.6))
    if pr.get("bang"):
        c = hc + V(0.42, 0.42, 0.05)
        out.append(Part(RED, lambda p: np.minimum(capsule(p, c + V(0, 0.06, 0), c + V(0, 0.24, 0), 0.04, 0.028),
                                                  sphere(p, c, 0.035))))
    if pr.get("sign"):
        sc = hc + V(0, 0.55, 0.05)
        out.append(Part(SIGN, lambda p: box(p, sc, V(0.40, 0.17, 0.025), 0.02)))
        out.append(Part(RED, lambda p: np.minimum(
            capsule(p, sc + V(0, -0.02, 0.05), sc + V(0, 0.10, 0.05), 0.03, 0.022),
            sphere(p, sc + V(0, -0.09, 0.05), 0.027))))
    return out


def shade_extra(pose: Pose):
    glow = pose.props.get("glow", 0.0)
    if not glow:
        return None
    src = V(0, 0.55, 0.45)

    def f(p, nrm, m, lit):
        tow = src - p
        dist = length(tow)
        facing = np.clip((nrm * (tow / dist[:, None])).sum(-1), 0, 1)
        amt = glow * facing * np.exp(-dist * 1.6)
        sel = np.isin(m, (SKIN, BEARD, SHIRT, HAIR, EYE))
        lit[sel] += (amt[sel, None] * np.array([0.25, 0.45, 0.65], np.float32))
        return lit

    return f
