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
    _fit_font,
)

GOLD = (230, 185, 74)
SILVER = (191, 195, 204)
BRONZE = (199, 132, 83)


def _rank_badge(draw, x: int, y: int, rank: int):
    if rank == 1:
        fill, text, label = GOLD, BG, "1st"
    elif rank == 2:
        fill, text, label = SILVER, BG, "2nd"
    elif rank == 3:
        fill, text, label = BRONZE, BG, "3rd"
    else:
        fill, text, label = PANEL_DEEP, MUTED, str(rank)

    width = 62 if rank <= 3 else 48
    draw.rounded_rectangle((x, y, x + width, y + 36), radius=18, fill=fill)
    font = _font(16 if rank <= 3 else 18, True)
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    draw.text((x + (width - tw) / 2, y + 7), label, font=font, fill=text)


def render_metric_leaders(match, metric_label: str, scope_label: str, rows: list[dict[str, Any]]) -> bytes:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    # Header
    draw.rounded_rectangle((54, 46, WIDTH - 54, 242), radius=34, fill=PANEL_SOFT)
    draw.rounded_rectangle((72, 66, 260, 92), radius=12, fill=ACCENT)
    draw.text((91, 68), "METRIC LEADERS", font=_font(16, True), fill=BG)

    metric_font = _fit_font(draw, metric_label.upper(), 720, 48, 30, True)
    draw.text((76, 112), metric_label.upper(), font=metric_font, fill=TEXT)
    draw.text((78, 181), scope_label, font=_font(20, True), fill=MUTED)
    match_text = f"{match.home_name} {match.home_score}–{match.away_score} {match.away_name}"
    _right_text(draw, WIDTH - 76, 182, match_text, _font(17), MUTED)

    # Table container
    table_top = 274
    draw.rounded_rectangle((54, table_top, WIDTH - 54, HEIGHT - 54), radius=34, fill=PANEL_SOFT)

    # Column header strip
    header_y = table_top + 22
    draw.text((82, header_y), "#", font=_font(16, True), fill=MUTED)
    draw.text((156, header_y), "PLAYER", font=_font(16, True), fill=MUTED)
    draw.text((570, header_y), "TEAM", font=_font(16, True), fill=MUTED)
    _right_text(draw, WIDTH - 86, header_y, "VALUE", _font(16, True), MUTED)
    draw.line((82, header_y + 34, WIDTH - 82, header_y + 34), fill=LINE, width=2)

    if not rows:
        draw.text((82, header_y + 90), "No player data available for this metric.", font=_font(25), fill=MUTED)
        return _png_bytes(image)

    # Ranked rows — deliberately table-led rather than podium-led.
    y = header_y + 54
    row_h = 88
    for idx, row in enumerate(rows[:10], start=1):
        if y + row_h > HEIGHT - 76:
            break

        row_fill = PANEL if idx % 2 == 1 else PANEL_SOFT
        draw.rounded_rectangle((70, y, WIDTH - 70, y + row_h - 8), radius=14, fill=row_fill)

        _rank_badge(draw, 84, y + 22, idx)

        # Player name
        name = str(row.get("name", ""))
        name_font = _fit_font(draw, name, 360, 25, 19, True)
        draw.text((156, y + 17), name, font=name_font, fill=TEXT)

        # Team identity with crest
        team = str(row.get("team", ""))
        _paste_logo(image, team, (566, y + 14), 50)
        team_font = _fit_font(draw, team, 230, 21, 16, False)
        draw.text((628, y + 25), team, font=team_font, fill=TEXT)

        # Metric value
        _right_text(draw, WIDTH - 90, y + 18, str(row.get("display", "")), _font(30, True), TEXT)

        y += row_h

    # Small qualifying-player count helps sparse metrics like Goals feel intentional.
    count_text = f"{len(rows)} qualifying player{'s' if len(rows) != 1 else ''}"
    draw.text((82, HEIGHT - 91), count_text, font=_font(15), fill=MUTED)

    return _png_bytes(image)
