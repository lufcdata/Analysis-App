from __future__ import annotations

from typing import Any

from PIL import Image, ImageDraw

from renderer import (
    WIDTH,
    HEIGHT,
    BG,
    PANEL,
    PANEL_SOFT,
    PANEL_DEEP,
    TEXT,
    MUTED,
    LINE,
    ACCENT,
    _font,
    _png_bytes,
    _paste_logo,
    _right_text,
    _center_text,
    _fit_font,
)

GOLD = (230, 185, 74)
SILVER = (191, 195, 204)
BRONZE = (199, 132, 83)


def _podium_card(draw, image, row: dict[str, Any], box, medal_color, ordinal: str):
    x1, y1, x2, y2 = box
    cx = (x1 + x2) / 2
    draw.rounded_rectangle(box, radius=26, fill=PANEL_SOFT, outline=medal_color, width=3)
    draw.rounded_rectangle((x1 + 18, y1 + 16, x1 + 82, y1 + 48), radius=14, fill=medal_color)
    draw.text((x1 + 31, y1 + 20), ordinal, font=_font(17, True), fill=BG)

    _paste_logo(image, row["team"], (int(cx - 46), y1 + 63), 92)
    name = row["name"].upper()
    name_font = _fit_font(draw, name, int(x2 - x1 - 34), 25, 17, True)
    _center_text(draw, cx, y1 + 168, name, name_font, TEXT)
    _center_text(draw, cx, y1 + 206, row["team"].upper(), _font(14, True), MUTED)
    _center_text(draw, cx, y1 + 242, row["display"], _font(39, True), medal_color)


def render_metric_leaders(match, metric_label: str, scope_label: str, rows: list[dict[str, Any]]) -> bytes:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    # Header
    draw.rounded_rectangle((54, 46, WIDTH - 54, 230), radius=34, fill=PANEL_SOFT)
    draw.rounded_rectangle((72, 66, 260, 92), radius=12, fill=ACCENT)
    draw.text((91, 68), "METRIC LEADERS", font=_font(16, True), fill=BG)

    metric_font = _fit_font(draw, metric_label.upper(), 720, 48, 30, True)
    draw.text((76, 112), metric_label.upper(), font=metric_font, fill=TEXT)
    draw.text((78, 176), scope_label, font=_font(22, True), fill=MUTED)
    match_text = f"{match.home_name} {match.home_score}–{match.away_score} {match.away_name}"
    _right_text(draw, WIDTH - 76, 177, match_text, _font(18), MUTED)

    if not rows:
        draw.rounded_rectangle((54, 258, WIDTH - 54, HEIGHT - 54), radius=34, fill=PANEL_SOFT)
        _center_text(draw, WIDTH / 2, 620, "NO PLAYER DATA AVAILABLE", _font(30, True), MUTED)
        return _png_bytes(image)

    # Podium — 2nd, 1st, 3rd for stronger visual balance
    podium_top = 268
    card_w = 292
    gap = 18
    positions = [
        (1, 54, podium_top + 54, SILVER, "2nd"),
        (0, 54 + card_w + gap, podium_top, GOLD, "1st"),
        (2, 54 + (card_w + gap) * 2, podium_top + 74, BRONZE, "3rd"),
    ]
    for row_idx, x, y, color, ordinal in positions:
        if len(rows) <= row_idx:
            continue
        height = 322 if row_idx == 0 else 286
        _podium_card(draw, image, rows[row_idx], (x, y, x + card_w, y + height), color, ordinal)

    # Remaining leaderboard
    list_top = 650
    draw.rounded_rectangle((54, list_top, WIDTH - 54, HEIGHT - 54), radius=34, fill=PANEL_SOFT)
    draw.text((82, list_top + 24), "RANK", font=_font(15, True), fill=MUTED)
    draw.text((154, list_top + 24), "PLAYER", font=_font(15, True), fill=MUTED)
    _right_text(draw, WIDTH - 84, list_top + 24, "VALUE", _font(15, True), MUTED)
    draw.line((82, list_top + 53, WIDTH - 82, list_top + 53), fill=LINE, width=2)

    y = list_top + 70
    for idx, row in enumerate(rows[3:11], start=4):
        if y > HEIGHT - 105:
            break
        if idx % 2 == 0:
            draw.rounded_rectangle((72, y - 5, WIDTH - 72, y + 57), radius=14, fill=PANEL)
        draw.text((88, y + 9), str(idx), font=_font(24, True), fill=MUTED)
        _paste_logo(image, row["team"], (142, y + 1), 50)
        draw.text((208, y + 4), row["name"], font=_font(23, True), fill=TEXT)
        draw.text((208, y + 34), row["team"], font=_font(14), fill=MUTED)
        _right_text(draw, WIDTH - 92, y + 11, row["display"], _font(28, True), TEXT)
        y += 67

    return _png_bytes(image)
