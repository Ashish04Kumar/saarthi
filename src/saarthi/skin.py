"""Skins: how the character looks.

Two kinds:
* Built-in procedural skins (drawn with code), e.g. "builtin:bit".
* Sprite skins: a folder with skin.json + images. Anyone can make one.

skin.json example:
{
  "name": "My Buddy",
  "author": "you",
  "fps": 12,
  "states": {
    "idle":        {"frames": "idle/*.png"},
    "typing_fast": {"gif": "typing.gif"},
    "sleeping":    {"sheet": "sleep.png", "cols": 8, "rows": 1, "fps": 6},
    "waking":      {"frames": "wake/*.png", "loop": false}
  }
}
Missing states fall back automatically (see states.FALLBACK).
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImageReader, QPainter, QPixmap

from .states import State, resolve

BUNDLED_DIR = Path(__file__).parent / "skins"


class Skin(ABC):
    id: str = ""
    name: str = ""
    author: str = ""
    aspect: float = 1.0  # width / height
    accessory: str | None = None  # weather outfit: umbrella / scarf / shades (skins may ignore)

    @abstractmethod
    def states(self) -> set[State]: ...

    @abstractmethod
    def paint(self, p: QPainter, rect: QRectF, state: State, t: float, t_state: float) -> None:
        """Draw `state` into `rect`. t = seconds since app start, t_state = since state began."""


@dataclass
class Animation:
    frames: list[QPixmap]
    fps: float = 12.0
    loop: bool = True
    _cache: dict[tuple[int, int], list[QPixmap]] = field(default_factory=dict)

    def frame(self, t_state: float, w: int, h: int) -> QPixmap:
        key = (w, h)
        if key not in self._cache:
            self._cache[key] = [
                f.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                for f in self.frames
            ]
        frames = self._cache[key]
        i = int(t_state * self.fps)
        i = i % len(frames) if self.loop else min(i, len(frames) - 1)
        return frames[i]


def _load_frames(root: Path, spec: dict) -> tuple[list[QPixmap], float | None]:
    if "frames" in spec:
        pattern = spec["frames"]
        paths = sorted(root.glob(pattern)) if isinstance(pattern, str) else [root / p for p in pattern]
        return [QPixmap(str(p)) for p in paths], None
    if "gif" in spec:
        reader = QImageReader(str(root / spec["gif"]))
        frames, delays = [], []
        while True:
            img = reader.read()
            if img.isNull():
                break
            frames.append(QPixmap.fromImage(img))
            delays.append(max(reader.nextImageDelay(), 20))
        fps = 1000.0 / (sum(delays) / len(delays)) if delays else None
        return frames, fps
    if "sheet" in spec:
        sheet = QPixmap(str(root / spec["sheet"]))
        cols, rows = int(spec.get("cols", 1)), int(spec.get("rows", 1))
        count = int(spec.get("count", cols * rows))
        fw, fh = sheet.width() // cols, sheet.height() // rows
        return [sheet.copy((i % cols) * fw, (i // cols) * fh, fw, fh) for i in range(count)], None
    return [], None


class SpriteSkin(Skin):
    def __init__(self, folder: Path):
        meta = json.loads((folder / "skin.json").read_text(encoding="utf-8"))
        self.id = f"folder:{folder}"
        self.name = meta.get("name", folder.name)
        self.author = meta.get("author", "")
        default_fps = float(meta.get("fps", 12))
        self.anims: dict[State, Animation] = {}
        for key, spec in meta.get("states", {}).items():
            try:
                state = State(key)
            except ValueError:
                continue
            frames, gif_fps = _load_frames(folder, spec)
            frames = [f for f in frames if not f.isNull()]
            if frames:
                fps = float(spec.get("fps", gif_fps or default_fps))
                loop = bool(spec.get("loop", True))
                self.anims[state] = Animation(frames, fps, loop)
        if not self.anims:
            raise ValueError(f"Skin {folder} has no loadable states")
        first = next(iter(self.anims.values())).frames[0]
        self.aspect = first.width() / max(1, first.height())

    def states(self) -> set[State]:
        return set(self.anims)

    def paint(self, p, rect, state, t, t_state):
        anim = self.anims[resolve(state, self.states())]
        pix = anim.frame(t_state, int(rect.width()), int(rect.height()))
        x = rect.x() + (rect.width() - pix.width()) / 2
        y = rect.y() + rect.height() - pix.height()  # stand on the bottom edge
        p.drawPixmap(int(x), int(y), pix)


def skin_dirs(user_dir: Path) -> list[Path]:
    return [BUNDLED_DIR, user_dir / "skins"]


def discover(user_dir: Path) -> dict[str, str]:
    """Return {skin_id: display name}."""
    found = {"builtin:bit": "Bit (built-in)"}
    for base in skin_dirs(user_dir):
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            meta = d / "skin.json"
            if meta.is_file():
                try:
                    name = json.loads(meta.read_text(encoding="utf-8")).get("name", d.name)
                except ValueError:
                    continue
                found[f"folder:{d}"] = name
    return found


def load(skin_id: str) -> Skin:
    if skin_id.startswith("folder:"):
        try:
            return SpriteSkin(Path(skin_id[len("folder:") :]))
        except (OSError, ValueError) as e:
            print(f"[saarthi] could not load skin {skin_id}: {e}; using Bit")
    from .mascot import BitSkin

    return BitSkin()
