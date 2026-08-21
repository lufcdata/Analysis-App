from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1080, 1350
BG = (12, 15, 19)
CARD = (22, 26, 32)
TEXT = (245, 247, 250)
MUTED = (160, 168, 178)
LINE = (53, 59, 68)
ACCENT = (207, 255, 70)


def _font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _png_bytes(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def render_player_graphic(player_name: str, opponent: str, rows: list[dict[str, Any]], minutes: Any) -> bytes:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    draw.text((72, 64), "PLAYER STATS", font=_font(30, True), fill=ACCENT)
    draw.text((72, 116), player_name.upper(), font=_font(64, True), fill=TEXT)
    draw.text((72, 198), f"Performance Numbers v {opponent}", font=_font(27), fill=MUTED)
    draw.line((72, 254, WIDTH - 72, 254), fill=LINE, width=2)

    max_rows = 17
    visible = rows[:max_rows]
    y = 292
    row_h = 52
    label_font = _font(27)
    value_font = _font(29, True)

    for row in visible:
        draw.text((72, y), row["label"], font=label_font, fill=TEXT)
        value = row["display"]
        bbox = draw.textbbox((0, 0), value, font=value_font)
        value_w = bbox[2] - bbox[0]
        draw.text((WIDTH - 72 - value_w, y), value, font=value_font, fill=TEXT)
        draw.line((72, y + 42, WIDTH - 72, y + 42), fill=LINE, width=1)
        y += row_h

    if minutes is not None:
        footer_y = HEIGHT - 140
        draw.rounded_rectangle((72, footer_y, WIDTH - 72, HEIGHT - 64), radius=18, fill=CARD)
        draw.text((100, footer_y + 27), "Minutes played", font=_font(28), fill=MUTED)
        value = str(minutes)
        bbox = draw.textbbox((0, 0), value, font=_font(34, True))
        draw.text((WIDTH - 100 - (bbox[2] - bbox[0]), footer_y + 21), value, font=_font(34, True), fill=TEXT)

    return _png_bytes(image)


def render_match_graphic(match, rows: list[dict[str, Any]]) -> bytes:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    draw.text((72, 58), "MATCH STATISTICS", font=_font(30, True), fill=ACCENT)
    draw.text((72, 108), f"{match.home_name}  {match.home_score}–{match.away_score}  {match.away_name}", font=_font(38, True), fill=TEXT)
    meta = " · ".join(part for part in (match.tournament, match.date_text) if part)
    draw.text((72, 164), meta, font=_font(24), fill=MUTED)

    left_x, right_x = 72, WIDTH - 72
    header_y = 226
    draw.text((left_x, header_y), match.home_name.upper(), font=_font(22, True), fill=MUTED)
    away_bbox = draw.textbbox((0, 0), match.away_name.upper(), font=_font(22, True))
    draw.text((right_x - (away_bbox[2] - away_bbox[0]), header_y), match.away_name.upper(), font=_font(22, True), fill=MUTED)
    draw.line((72, 266, WIDTH - 72, 266), fill=LINE, width=2)

    y = 292
    row_h = 43
    max_rows = 22
    current_group = None
    shown = 0
    for row in rows:
        if shown >= max_rows:
            break
        group = row.get("group") or "Statistics"
        if group != current_group:
            if current_group is not None:
                y += 8
            draw.text((72, y), group.upper(), font=_font(18, True), fill=ACCENT)
            y += 31
            current_group = group
        if shown >= max_rows or y > HEIGHT - 70:
            break

        home = "–" if row.get("home") is None else str(row.get("home"))
        away = "–" if row.get("away") is None else str(row.get("away"))
        label = str(row.get("name", ""))
        draw.text((72, y), home, font=_font(23, True), fill=TEXT)
        label_bbox = draw.textbbox((0, 0), label, font=_font(21))
        label_w = label_bbox[2] - label_bbox[0]
        draw.text(((WIDTH - label_w) / 2, y), label, font=_font(21), fill=MUTED)
        away_bbox = draw.textbbox((0, 0), away, font=_font(23, True))
        draw.text((WIDTH - 72 - (away_bbox[2] - away_bbox[0]), y), away, font=_font(23, True), fill=TEXT)
        draw.line((72, y + 34, WIDTH - 72, y + 34), fill=LINE, width=1)
        y += row_h
        shown += 1

    return _png_bytes(image)
