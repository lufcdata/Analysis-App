from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1080, 1350
# MatchLab brand palette
BG = (36, 34, 54)          # #242236
CARD = (47, 45, 68)
CARD_2 = (42, 40, 62)
TEXT = (250, 250, 252)
MUTED = (178, 176, 195)
LINE = (70, 67, 94)
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


def _right_text(draw, x_right, y, text, font, fill):
    bbox = draw.textbbox((0, 0), str(text), font=font)
    draw.text((x_right - (bbox[2] - bbox[0]), y), str(text), font=font, fill=fill)


def render_player_graphic(player_name: str, opponent: str, rows: list[dict[str, Any]], minutes: Any) -> bytes:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    # Premium compact header
    draw.rounded_rectangle((56, 50, WIDTH - 56, 254), radius=28, fill=CARD_2)
    draw.text((82, 76), "PLAYER STATS", font=_font(25, True), fill=ACCENT)
    draw.text((82, 116), player_name.upper(), font=_font(54, True), fill=TEXT)
    draw.text((82, 190), f"Performance Numbers v {opponent}", font=_font(25), fill=MUTED)

    # Stats panel
    panel_top = 278
    panel_bottom = HEIGHT - 166 if minutes is not None else HEIGHT - 62
    draw.rounded_rectangle((56, panel_top, WIDTH - 56, panel_bottom), radius=28, fill=CARD_2)

    max_rows = 17
    visible = rows[:max_rows]
    available_h = panel_bottom - panel_top - 42
    row_h = min(54, max(43, available_h // max(1, len(visible))))
    y = panel_top + 22
    label_font = _font(25)
    value_font = _font(27, True)

    for i, row in enumerate(visible):
        draw.text((82, y + 7), row["label"], font=label_font, fill=TEXT)
        _right_text(draw, WIDTH - 82, y + 5, row["display"], value_font, TEXT)
        if i != len(visible) - 1:
            draw.line((82, y + row_h - 2, WIDTH - 82, y + row_h - 2), fill=LINE, width=1)
        y += row_h

    if minutes is not None:
        footer_y = HEIGHT - 142
        draw.rounded_rectangle((56, footer_y, WIDTH - 56, HEIGHT - 56), radius=26, fill=CARD)
        draw.text((82, footer_y + 28), "MINUTES PLAYED", font=_font(23, True), fill=MUTED)
        _right_text(draw, WIDTH - 82, footer_y + 20, str(minutes), _font(36, True), TEXT)

    return _png_bytes(image)


def render_match_graphic(match, rows: list[dict[str, Any]]) -> bytes:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    # Header card
    draw.rounded_rectangle((56, 48, WIDTH - 56, 244), radius=28, fill=CARD_2)
    draw.text((82, 72), "MATCH STATISTICS", font=_font(25, True), fill=ACCENT)
    scoreline = f"{match.home_name}  {match.home_score}–{match.away_score}  {match.away_name}"
    draw.text((82, 116), scoreline, font=_font(35, True), fill=TEXT)
    meta = " · ".join(part for part in (match.tournament, match.date_text) if part)
    draw.text((82, 174), meta, font=_font(23), fill=MUTED)

    # Main statistics panel
    draw.rounded_rectangle((56, 268, WIDTH - 56, HEIGHT - 56), radius=28, fill=CARD_2)
    left_x, right_x = 82, WIDTH - 82
    header_y = 294
    draw.text((left_x, header_y), match.home_name.upper(), font=_font(20, True), fill=MUTED)
    _right_text(draw, right_x, header_y, match.away_name.upper(), _font(20, True), MUTED)
    draw.line((82, 332, WIDTH - 82, 332), fill=LINE, width=2)

    y = 352
    row_h = 40
    max_rows = 22
    current_group = None
    shown = 0
    for row in rows:
        if shown >= max_rows:
            break
        group = row.get("group") or "Statistics"
        if group != current_group:
            if current_group is not None:
                y += 5
            if y > HEIGHT - 105:
                break
            draw.text((82, y), group.upper(), font=_font(17, True), fill=ACCENT)
            y += 29
            current_group = group

        if shown >= max_rows or y > HEIGHT - 100:
            break

        home = "–" if row.get("home") is None else str(row.get("home"))
        away = "–" if row.get("away") is None else str(row.get("away"))
        label = str(row.get("name", ""))
        draw.text((82, y + 3), home, font=_font(21, True), fill=TEXT)
        label_font = _font(19)
        label_bbox = draw.textbbox((0, 0), label, font=label_font)
        draw.text(((WIDTH - (label_bbox[2] - label_bbox[0])) / 2, y + 4), label, font=label_font, fill=MUTED)
        _right_text(draw, WIDTH - 82, y + 3, away, _font(21, True), TEXT)
        draw.line((82, y + 33, WIDTH - 82, y + 33), fill=LINE, width=1)
        y += row_h
        shown += 1

    return _png_bytes(image)
