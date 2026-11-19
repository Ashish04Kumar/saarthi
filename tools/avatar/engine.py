"""A tiny signed-distance-field raymarcher (numpy only).

Renders a 3D scene made of spheres, capsules, ellipsoids and boxes with toon shading,
ambient occlusion, rim light and outlines, on a transparent background.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

F = np.float32


def V(*a) -> np.ndarray:
    return np.array(a, dtype=F)


def length(v):
    return np.sqrt((v * v).sum(-1))


def normalize(v):
    return v / np.maximum(length(v)[..., None], 1e-9)


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], F)


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], F)


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], F)


# ---------------- primitives ----------------

def sphere(p, c, r):
    return length(p - c) - r


def ellipsoid(p, c, r):
    q = (p - c) / r
    k0 = length(q)
    k1 = length(q / r)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-6)


def capsule(p, a, b, r, rb=None):
    pa, ba = p - a, b - a
    h = np.clip((pa @ ba) / max(float(ba @ ba), 1e-9), 0.0, 1.0)
    rr = r if rb is None else r + (rb - r) * h
    return length(pa - h[:, None] * ba) - rr


def box(p, c, half, rad=0.0, R=None):
    q = p - c
    if R is not None:
        q = q @ R  # columns of R are the box's local axes
    q = np.abs(q) - half
    return length(np.maximum(q, 0.0)) + np.minimum(q.max(-1), 0.0) - rad


def cylinder(p, c, r, h, rad=0.0):
    q = p - c
    dx = np.sqrt(q[:, 0] ** 2 + q[:, 2] ** 2) - r + rad
    dy = np.abs(q[:, 1]) - h + rad
    return np.minimum(np.maximum(dx, dy), 0.0) + np.sqrt(np.maximum(dx, 0) ** 2 + np.maximum(dy, 0) ** 2) - rad


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1 - h)


def smin_all(ds, k):
    out = ds[0]
    for d in ds[1:]:
        out = smin(out, d, k)
    return out


# ---------------- scene graph ----------------

class Part:
    def __init__(self, mat: int, fn):
        self.mat, self.fn = mat, fn

    def eval(self, p):
        return self.fn(p), self.mat


class Group:
    """Parts inside a bounding sphere, optionally in a local (rotated) frame."""

    def __init__(self, parts, center, radius, origin=None, R=None, scale=None):
        self.parts, self.center, self.radius = parts, center, radius
        self.origin, self.R = origin, R
        self.scale = None if scale is None else np.asarray(scale, F)

    def eval(self, p):
        db = length(p - self.center) - self.radius
        d = db.astype(F)
        m = np.zeros(len(p), np.int16)
        idx = np.nonzero(db < 0.02)[0]
        if idx.size:
            q = p[idx]
            if self.origin is not None:
                q = (q - self.origin) @ self.R
            if self.scale is not None:  # non-uniform scale; keep the distance conservative
                q = q / self.scale
            dd, mm = combine(self.parts, q)
            if self.scale is not None:
                dd = dd * float(self.scale.min())
            d[idx] = dd
            m[idx] = mm
        return d, m


def combine(parts, p):
    d = np.full(len(p), 1e9, F)
    m = np.zeros(len(p), np.int16)
    for part in parts:
        di, mi = part.eval(p)
        u = di < d
        d = np.where(u, di, d)
        m = np.where(u, mi, m)
    return d, m


# ---------------- camera & render ----------------

@dataclass
class Camera:
    target: np.ndarray
    yaw: float  # degrees, + looks from the character's left side
    pitch: float  # degrees, + looks down
    half_size: float  # half of the visible square, in world units

    def basis(self):
        y, pch = math.radians(self.yaw), math.radians(self.pitch)
        eye_dir = V(math.sin(y) * math.cos(pch), math.sin(pch), math.cos(y) * math.cos(pch))
        fwd = -eye_dir
        right = normalize(np.cross(fwd, V(0, 1, 0)))
        up = np.cross(right, fwd)
        return fwd, right, up


@dataclass
class Material:
    color: tuple
    spec: float = 0.0
    emissive: bool = False


def render(scene, cam: Camera, size: int, materials: dict, shade_extra=None, ssaa: int = 2):
    """Return an RGBA uint8 array (size x size)."""
    n = size * ssaa
    fwd, right, up = cam.basis()
    s = cam.half_size
    u = np.linspace(-s, s, n, dtype=F)
    v = np.linspace(s, -s, n, dtype=F)
    uu, vv = np.meshgrid(u, v)
    origins = (cam.target - fwd * 6.0)[None, :] + uu.reshape(-1, 1) * right + vv.reshape(-1, 1) * up
    N = n * n
    t = np.full(N, 3.5, F)
    alive = np.ones(N, bool)
    hit = np.zeros(N, bool)
    for _ in range(160):
        idx = np.nonzero(alive)[0]
        if idx.size == 0:
            break
        p = origins[idx] + fwd * t[idx, None]
        d, _ = scene.eval(p)
        t[idx] += d * 0.85
        h = d < 0.0012
        hit[idx[h]] = True
        alive[idx[h | (t[idx] > 9.5)]] = False

    rgb = np.zeros((N, 3), F)
    hidx = np.nonzero(hit)[0]
    mats = np.zeros(N, np.int16)
    if hidx.size:
        p = origins[hidx] + fwd * t[hidx, None]
        _, m = scene.eval(p)
        mats[hidx] = m
        e = 0.0015
        k = [V(1, -1, -1), V(-1, -1, 1), V(-1, 1, -1), V(1, 1, 1)]
        nrm = sum(kk * scene.eval(p + kk * e)[0][:, None] for kk in k)
        nrm = normalize(nrm)
        # ambient occlusion
        ao = np.ones(len(p), F)
        for i, dist in enumerate((0.03, 0.07, 0.12, 0.18)):
            dd, _ = scene.eval(p + nrm * dist)
            ao -= (dist - np.minimum(dd, dist)) * (0.9 / (i + 1))
        ao = np.clip(ao, 0.55, 1.0)

        L = normalize(V(-0.45, 0.8, 0.6))
        ndl = nrm @ L
        cel = np.clip((ndl + 0.08) / 0.3, 0.0, 1.0)
        cel = cel * cel * (3 - 2 * cel)
        light = 0.58 + 0.42 * cel + 0.06 * ndl
        view = -fwd
        rim = np.clip(1.0 - nrm @ view, 0.0, 1.0) ** 3 * 0.28
        hvec = normalize(L + view)
        spec_term = np.clip(nrm @ hvec, 0.0, 1.0) ** 48

        base = np.zeros((len(p), 3), F)
        spec = np.zeros(len(p), F)
        emis = np.zeros(len(p), bool)
        for mid, mat in materials.items():
            sel = m == mid
            if not sel.any():
                continue
            col = mat.color(p[sel]) if callable(mat.color) else np.array(mat.color, F)
            base[sel] = col
            spec[sel] = mat.spec
            emis[sel] = mat.emissive
        lit = base * (light * ao)[:, None] + rim[:, None] * 0.55 + (spec * spec_term)[:, None]
        if shade_extra is not None:
            lit = shade_extra(p, nrm, m, lit)
        lit[emis] = base[emis]
        rgb[hidx] = np.clip(lit, 0, 1)

    img = rgb.reshape(n, n, 3)
    alpha = hit.reshape(n, n).astype(F)
    depth = np.where(hit, t, 99).reshape(n, n)

    # outlines: silhouette and depth discontinuities
    edge = np.zeros((n, n), bool)
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)):
        sd = np.roll(np.roll(depth, dy, 0), dx, 1)
        edge |= (alpha > 0) & (sd - depth > 0.08)
    line = np.array([0.12, 0.09, 0.10], F)
    img[edge] = img[edge] * 0.15 + line * 0.85

    # downsample with alpha-weighted averaging
    a = alpha.reshape(size, ssaa, size, ssaa).mean((1, 3))
    c = (img * alpha[..., None]).reshape(size, ssaa, size, ssaa, 3).sum((1, 3))
    c = c / np.maximum(alpha.reshape(size, ssaa, size, ssaa).sum((1, 3)), 1e-6)[..., None]
    out = np.zeros((size, size, 4), np.uint8)
    out[..., :3] = np.clip(c * 255, 0, 255).astype(np.uint8)
    out[..., 3] = np.clip(a * 255, 0, 255).astype(np.uint8)
    return out
