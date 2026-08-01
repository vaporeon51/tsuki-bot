"""Rendering helpers for the personal bias wheel command."""

from __future__ import annotations

import io
import math
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

if TYPE_CHECKING:
    from src.db.bias_rater import LeaderboardEntry


WHEEL_SIZE = 800
_BACKGROUND = (29, 24, 49, 255)
_WEDGE_COLORS = (
    (255, 112, 143, 255),
    (255, 173, 94, 255),
    (255, 222, 104, 255),
    (114, 211, 153, 255),
    (102, 196, 255, 255),
    (154, 139, 255, 255),
    (222, 126, 255, 255),
    (255, 132, 193, 255),
)
_MAX_IMAGE_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class WheelResult:
    winner: LeaderboardEntry
    gif: io.BytesIO


def render_wheel(entries: list[LeaderboardEntry]) -> WheelResult:
    """Choose a winner and return a short, non-looping wheel animation."""
    if len(entries) < 2:
        raise ValueError("At least two ranked idols are needed to spin the wheel.")

    winner_index = random.randrange(len(entries))
    wheel = _draw_wheel(entries)
    gif = _animate_wheel(wheel, winner_index, len(entries))
    return WheelResult(winner=entries[winner_index], gif=gif)


def _draw_wheel(entries: list[LeaderboardEntry]) -> Image.Image:
    image = Image.new("RGBA", (WHEEL_SIZE, WHEEL_SIZE), _BACKGROUND)
    draw = ImageDraw.Draw(image)
    center = WHEEL_SIZE // 2
    radius = 330
    count = len(entries)
    step = 360 / count

    for index, entry in enumerate(entries):
        # Center the first entry under the 12 o'clock pointer before spinning.
        start = -90 - step / 2 + index * step
        end = start + step
        draw.pieslice(
            (center - radius, center - radius, center + radius, center + radius),
            start=start,
            end=end,
            fill=_WEDGE_COLORS[index % len(_WEDGE_COLORS)],
            outline=(255, 255, 255, 210),
            width=3,
        )

        angle = math.radians(start + step / 2)
        portrait_center = (
            int(center + math.cos(angle) * 205),
            int(center + math.sin(angle) * 205),
        )
        portrait = _load_portrait(entry.image_url, 82)
        image.alpha_composite(portrait, (portrait_center[0] - 41, portrait_center[1] - 41))
        _draw_name(image, entry.member_name, portrait_center[0], portrait_center[1] + 55)

    draw.ellipse(
        (center - 75, center - 75, center + 75, center + 75),
        fill=(53, 41, 88, 255),
        outline=(255, 255, 255, 230),
        width=5,
    )
    font = _font(30)
    label = "BIAS\nWHEEL"
    bbox = draw.multiline_textbbox((0, 0), label, font=font, align="center", spacing=0)
    draw.multiline_text(
        (center - (bbox[2] - bbox[0]) / 2, center - (bbox[3] - bbox[1]) / 2),
        label,
        fill="white",
        font=font,
        align="center",
        spacing=0,
    )
    return image


def _animate_wheel(wheel: Image.Image, winner_index: int, count: int) -> io.BytesIO:
    # The fixed pointer is at 12 o'clock. Land in the middle of the chosen wedge
    # after several full clockwise turns, with progressively smaller increments.
    step = 360 / count
    # Wedge 0 is already centered beneath the pointer. Rotating clockwise by one
    # wedge width moves each subsequent entry beneath it.
    total_rotation = 4 * 360 + winner_index * step
    fractions = (0.0, 0.13, 0.27, 0.43, 0.58, 0.71, 0.81, 0.89, 0.95, 0.985, 1.0)
    frames = []
    for fraction in fractions:
        rotation = total_rotation * (1 - (1 - fraction) ** 2.7)
        frame = Image.new("RGBA", (WHEEL_SIZE, WHEEL_SIZE), _BACKGROUND)
        spun = wheel.rotate(-rotation, resample=Image.Resampling.BICUBIC)
        frame.alpha_composite(spun)
        _draw_pointer(frame)
        frames.append(frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=128))

    output = io.BytesIO()
    frames[0].save(
        output,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=[70, 70, 75, 80, 95, 110, 140, 175, 230, 320, 1300],
        optimize=True,
        disposal=2,
    )
    output.seek(0)
    output.name = "bias-wheel.gif"
    return output


def _draw_pointer(image: Image.Image) -> None:
    draw = ImageDraw.Draw(image)
    center = WHEEL_SIZE // 2
    draw.polygon(
        [(center, 42), (center - 25, 4), (center + 25, 4)],
        fill=(255, 255, 255, 255),
        outline=(31, 23, 49, 255),
        width=4,
    )


def _load_portrait(url: str, size: int) -> Image.Image:
    try:
        response = requests.get(url, timeout=5, stream=True)
        response.raise_for_status()
        data = response.raw.read(_MAX_IMAGE_BYTES + 1)
        if len(data) > _MAX_IMAGE_BYTES:
            raise ValueError("source image is too large")
        portrait = Image.open(io.BytesIO(data)).convert("RGBA")
        portrait = ImageOps.fit(portrait, (size, size), method=Image.Resampling.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((1, 1, size - 2, size - 2), fill=255)
        portrait.putalpha(mask)
        return portrait
    except Exception:
        placeholder = Image.new("RGBA", (size, size), (72, 60, 104, 255))
        ImageDraw.Draw(placeholder).ellipse((1, 1, size - 2, size - 2), fill=(72, 60, 104, 255))
        return placeholder


def _draw_name(image: Image.Image, name: str, x: int, y: int) -> None:
    draw = ImageDraw.Draw(image)
    text = name if len(name) <= 15 else f"{name[:14]}…"
    font = _font(16)
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    draw.rounded_rectangle((x - width / 2 - 5, y - 2, x + width / 2 + 5, y + 20), radius=5, fill=(0, 0, 0, 145))
    draw.text((x - width / 2, y), text, font=font, fill="white")


def _font(size: int) -> ImageFont.ImageFont:
    for path in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()
