"""Render every state to PNG frames and write a Saarthi skin folder.

    python tools/avatar/build_skin.py OUT_DIR [--name "My Avatar"] [--size 256] [--only idle,happy]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

# One BLAS thread per worker; otherwise 12 workers x 12 threads thrash the CPU.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
sys.path.insert(0, os.path.dirname(__file__))

from engine import Camera, V, render  # noqa: E402
from model import Look, build, materials, shade_extra  # noqa: E402
from poses import STATES, pose_for  # noqa: E402

CAMERA = Camera(V(0, 1.16, 0), yaw=24, pitch=10, half_size=1.3)


def _job(args):
    state, i, size, out, look_kw = args
    frames, fps, loop = STATES[state]
    path = Path(out) / state / f"{i:03d}.png"
    if path.exists() and os.environ.get("SAARTHI_FORCE") != "1":
        return state, i
    look = Look(**look_kw)
    pose = pose_for(state, i / fps)
    img = render(build(pose, look), CAMERA, size, materials(look), shade_extra(pose))
    path.parent.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QImage

    QImage(img.tobytes(), size, size, size * 4, QImage.Format.Format_RGBA8888).save(str(path))
    return state, i


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--name", default="My Avatar")
    ap.add_argument("--size", type=int, default=256)
    ap.add_argument("--only", default="")
    ap.add_argument("--look", default="{}", help='JSON overrides for Look, e.g. {"shirt": [0.2,0.4,0.9]}')
    args = ap.parse_args()
    look_kw = json.loads(args.look)
    states = [s for s in STATES if not args.only or s in args.only.split(",")]
    jobs = [(s, i, args.size, args.out, look_kw) for s in states for i in range(STATES[s][0])]
    t0 = time.time()
    with ProcessPoolExecutor() as ex:
        for n, _ in enumerate(ex.map(_job, jobs, chunksize=1), 1):
            if n % 20 == 0 or n == len(jobs):
                print(f"{n}/{len(jobs)} frames  ({time.time() - t0:.0f}s)", flush=True)
    meta = {
        "name": args.name,
        "author": "Saarthi avatar maker",
        "fps": 10,
        "states": {s: {"frames": f"{s}/*.png", "fps": STATES[s][1], "loop": STATES[s][2]} for s in STATES},
    }
    Path(args.out, "skin.json").write_text(json.dumps(meta, indent=2))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
