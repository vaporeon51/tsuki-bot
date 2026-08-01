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

    # Shuffling makes each spin's wheel feel fresh while keeping every top-N idol
    # equally likely to win.
    entries = list(entries)
    random.shuffle(entries)
    winner_index = random.randrange(len(entries))
    wheel = _draw_wheel(entries)
    gif = _animate_wheel(wheel, winner_index, len(entries), entries[winner_index].member_name)
    return WheelResult(winner=entries[winner_index], gif=gif)


def _draw_wheel(entries: list[LeaderboardEntry]) -> Image.Image:
    image = Image.new("RGBA", (WHEEL_SIZE, WHEEL_SIZE), _BACKGROUND)
    draw = ImageDraw.Draw(image)
    center = WHEEL_SIZE // 2
    radius = 330
    count = len(entries)
    step = 360 / count
    portrait_size = max(82, min(138, 194 - count * 14))
    portrait_radius = 205 if count >= 7 else 215

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
            int(center + math.cos(angle) * portrait_radius),
            int(center + math.sin(angle) * portrait_radius),
        )
        portrait = _load_portrait(entry.image_url, portrait_size)
        half_portrait = portrait_size // 2
        image.alpha_composite(portrait, (portrait_center[0] - half_portrait, portrait_center[1] - half_portrait))
        _draw_name(image, entry.member_name, portrait_center[0], portrait_center[1] + half_portrait + 10)

    return image


def _animate_wheel(wheel: Image.Image, winner_index: int, count: int, winner_name: str) -> io.BytesIO:
    """Animate only the central pointer, preserving a clear static wheel."""
    step = 360 / count
    # Entry 0 is centered at 12 o'clock. The pointer starts there and makes six
    # full clockwise rotations, landing precisely on the selected entry.
    total_rotation = 6 * 360 + winner_index * step
    frame_count = 86
    frames = []
    for frame_index in range(frame_count):
        elapsed = frame_index / (frame_count - 1)
        rotation = total_rotation * _spin_progress(elapsed)
        frame = wheel.copy()
        _draw_pointer(frame, rotation)
        if frame_index == frame_count - 1:
            _draw_winner_celebration(frame, winner_name)
        frames.append(frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=128))

    output = io.BytesIO()
    frames[0].save(
        output,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        # 85 × 50ms spinning frames (20 FPS) plus an 850ms reveal ≈ 5.1 seconds.
        duration=[50] * (frame_count - 1) + [850],
        optimize=True,
        disposal=2,
    )
    output.seek(0)
    output.name = "bias-wheel.gif"
    return output


def _spin_progress(elapsed: float) -> float:
    """Acceleration → sustained fast spin → gradual deceleration."""
    if elapsed < 0.18:
        # Ease in: starts gently, then quickly reaches full speed.
        return 0.13 * (elapsed / 0.18) ** 2
    if elapsed < 0.60:
        # High-speed middle section.
        return 0.13 + 0.60 * ((elapsed - 0.18) / 0.42)
    # Ease out over the final third, so the destination is easy to follow.
    t = (elapsed - 0.60) / 0.40
    return 0.73 + 0.27 * (1 - (1 - t) ** 2)


def _draw_pointer(image: Image.Image, rotation: float) -> None:
    draw = ImageDraw.Draw(image)
    center = WHEEL_SIZE // 2
    length = 145
    angle = math.radians(-90 + rotation)
    tip = (int(center + math.cos(angle) * length), int(center + math.sin(angle) * length))
    perpendicular = math.pi / 2
    arrow_base = 20
    left = (
        int(center + math.cos(angle) * arrow_base + math.cos(angle + perpendicular) * 12),
        int(center + math.sin(angle) * arrow_base + math.sin(angle + perpendicular) * 12),
    )
    right = (
        int(center + math.cos(angle) * arrow_base + math.cos(angle - perpendicular) * 12),
        int(center + math.sin(angle) * arrow_base + math.sin(angle - perpendicular) * 12),
    )
    draw.polygon(
        [left, tip, right],
        fill=(235, 61, 76, 255),
    )
    draw.ellipse(
        (center - 26, center - 26, center + 26, center + 26),
        fill=(255, 255, 255, 255),
        outline=(255, 255, 255, 255),
        width=4,
    )


def _draw_winner_celebration(image: Image.Image, winner_name: str) -> None:
    draw = ImageDraw.Draw(image)
    text = f"{winner_name.upper()}!"
    font = _font(30)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    x = (WHEEL_SIZE - text_width) // 2
    y = 748
    draw.rounded_rectangle((x - 14, y - 6, x + text_width + 14, y + 40), radius=12, fill=(53, 41, 88, 240))
    draw.text((x, y), text, font=font, fill=(255, 234, 112, 255))
    # Draw confetti rather than relying on an emoji font being installed.
    for x1, y1, x2, y2, color in (
        (270, 746, 278, 730, (255, 112, 143, 255)),
        (300, 756, 286, 742, (102, 196, 255, 255)),
        (530, 746, 522, 730, (114, 211, 153, 255)),
        (500, 756, 514, 742, (255, 173, 94, 255)),
    ):
        draw.line((x1, y1, x2, y2), fill=color, width=5)


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
