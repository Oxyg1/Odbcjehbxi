"""Vault artwork: generate the two safe images once, then reuse Telegram file_ids.

Only two frames exist (locked / open) because the *dials live in the keyboard*,
not in the picture. That is what makes the interaction feel seamless: turning a
dial is an ``editMessageReplyMarkup`` call, which Telegram applies in place with
no media reload and no flash. The photo is re-sent exactly once, at the moment
the vault opens.

Uploading a photo costs a round trip and re-encodes the file. After the first
upload we cache the ``file_id`` Telegram hands back and send that string
instead, so every later vault is a pure metadata call.
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from pathlib import Path

from aiogram.types import FSInputFile
from PIL import Image, ImageDraw

log = logging.getLogger(__name__)

ASSET_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "generated"

SIZE = (800, 800)
BG = (18, 18, 22)
STEEL = (86, 92, 104)
STEEL_DARK = (54, 58, 68)
BRASS = (198, 158, 74)
GREEN = (72, 190, 116)
RED = (206, 84, 84)


class Frame(str, Enum):
    LOCKED = "locked"
    OPEN = "open"


def _draw_body(draw: ImageDraw.ImageDraw) -> None:
    """The safe's outer shell — shared by both frames so they line up exactly."""
    draw.rounded_rectangle((60, 60, 740, 740), radius=36, fill=STEEL_DARK)
    draw.rounded_rectangle((84, 84, 716, 716), radius=28, fill=(44, 47, 56))


def _draw_hinges(draw: ImageDraw.ImageDraw, x: int) -> None:
    for y in (210, 400, 590):
        draw.rounded_rectangle((x - 18, y - 30, x + 18, y + 30), radius=10, fill=BRASS)


def _draw_lamp(draw: ImageDraw.ImageDraw, x: int, y: int, color: tuple) -> None:
    draw.ellipse((x - 22, y - 22, x + 22, y + 22), fill=color, outline=BG, width=5)


def _render_locked(path: Path) -> None:
    img = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(img)
    _draw_body(draw)

    # Door: an inset panel, seated in the shell. Its outline is the door seam,
    # which is why nothing crosses the dial.
    draw.rounded_rectangle((120, 120, 690, 690), radius=22, fill=STEEL)
    draw.rounded_rectangle((120, 120, 690, 690), radius=22, outline=STEEL_DARK, width=5)
    _draw_hinges(draw, 120)

    # Central combination dial.
    draw.ellipse((310, 310, 490, 490), fill=STEEL_DARK, outline=BRASS, width=8)
    draw.ellipse((368, 368, 432, 432), fill=BRASS)
    draw.line((400, 400, 400, 330), fill=BG, width=10)

    # Handle, to the right of the dial.
    draw.rounded_rectangle((560, 380, 640, 420), radius=18, fill=BRASS)

    _draw_lamp(draw, 620, 180, RED)
    img.save(path, format="PNG", optimize=True)


def _render_open(path: Path) -> None:
    img = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(img)
    _draw_body(draw)

    # Cavity, now exposed, with three bars of something valuable inside.
    draw.rounded_rectangle((250, 175, 700, 690), radius=18, fill=(10, 10, 13))
    draw.rounded_rectangle((262, 187, 688, 678), radius=14, outline=STEEL_DARK, width=4)
    for top in (235, 370, 505):
        draw.rounded_rectangle((320, top, 630, top + 100), radius=10, fill=BRASS)
        draw.rounded_rectangle(
            (320, top, 630, top + 24), radius=10, fill=(226, 190, 112)
        )

    # Door, swung open past the shell on its hinges. The dark gap behind it and
    # the offset past the body edge are what make it read as open.
    draw.rounded_rectangle((150, 120, 250, 690), radius=12, fill=(8, 8, 10))
    draw.rounded_rectangle((30, 100, 195, 700), radius=20, fill=STEEL)
    draw.rounded_rectangle((30, 100, 195, 700), radius=20, outline=BRASS, width=5)
    draw.ellipse((72, 352, 152, 432), fill=STEEL_DARK, outline=BRASS, width=6)
    _draw_hinges(draw, 195)

    _draw_lamp(draw, 620, 128, GREEN)
    img.save(path, format="PNG", optimize=True)


_RENDERERS = {Frame.LOCKED: _render_locked, Frame.OPEN: _render_open}


class ArtworkProvider:
    """Renders the frames on first use and caches their Telegram file_ids."""

    def __init__(self, asset_dir: Path = ASSET_DIR) -> None:
        self._dir = asset_dir
        self._file_ids: dict[Frame, str] = {}
        self._lock = asyncio.Lock()

    def ensure_rendered(self) -> None:
        """Draw any missing PNGs. Cheap and idempotent; call once at startup."""
        self._dir.mkdir(parents=True, exist_ok=True)
        for frame, render in _RENDERERS.items():
            path = self._path(frame)
            if not path.exists():
                log.info("rendering vault artwork: %s", path.name)
                render(path)

    def _path(self, frame: Frame) -> Path:
        return self._dir / f"safe_{frame.value}.png"

    def input_for(self, frame: Frame) -> str | FSInputFile:
        """A cached file_id when we have one, otherwise the file to upload."""
        cached = self._file_ids.get(frame)
        if cached:
            return cached
        self.ensure_rendered()
        return FSInputFile(self._path(frame))

    def remember(self, frame: Frame, file_id: str) -> None:
        self._file_ids[frame] = file_id

    def forget(self, frame: Frame) -> None:
        """Drop a stale file_id (e.g. after a `wrong file identifier` error)."""
        self._file_ids.pop(frame, None)
