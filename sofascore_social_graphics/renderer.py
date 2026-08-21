from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any
import re

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1080, 1350
BG = (36, 34, 54)          # #242236
PANEL = (46, 43, 68)
PANEL_SOFT = (42, 40, 62)
PANEL_DEEP = (31, 29, 47)
TEXT = (250, 250, 252)
MUTED = (178, 176, 195)
LINE = (72, 69, 98)
ACCENT = (207, 255, 70)
ASSET_DIR = Path(__file__).parent / "assets" / "clubs"

CLUB_SLUGS = {
    "Brighton & Hove Albion": "brighton-hove-albion",
    "Leeds United": "leeds-united",
    "Manchester City": "manchester-city",
    "Manchester United": "manchester-united",
    "Newcastle United": "newcastle-united",
    "Nottingham Forest": "nottingham-forest",
    "Tottenham Hotspur": "tottenham-hotspur",
    "Tottenham": "tottenham-hotspur",
    "West Ham United": "west-ham-united",
    "Wolverhampton Wanderers": "wolverhampton-wanderers",
    "Wolves": "wolverhampton-wanderers",
}


def _slugify(name: str) -> str:
    if name in CLUB_SLUGS:
        return CLUB_SLUGS[name]
    value = name.lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


def _club_logo(name: str, size: int = 104):
    path = ASSET_DIR / f"{_slugify(name)}.png"
    if not path.exists():
        return None
    try:
        logo = Image.open(path).convert("RGBA")
        logo.thumbnail((size, size), Image.Resampling.LANCZOS)
        return logo
    except Exception:
        return None


def _paste_logo(image: Image.Image, name: str, xy: tuple[int, int], size: int = 104):
    logo = _club_logo(name, size)
    if logo is None:
        return False
    x, y = xy
    image.paste(logo, (x + (size - logo.width) // 2, y + (size - logo.height) // 2), logo)
    return True


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


def _center_text(draw, cx, y, text, font, fill):
    bbox = draw.textbbox((0, 0), str(text), font=font)
    draw.text((cx - (bbox[2] - bbox[0]) / 2, y), str(text), font=font, fill=fill)


def _fit_font(draw, text: str, max_width: int, start_size: int, min_size: int = 24, bold: bool = True):
    size = start_size
    while size > min_size:
        font = _font(size, bold)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
        size -= 2
    return _font(min_size, bold)


def render_player_graphic(
    player_name: str,
    opponent: str,
    rows: list[dict[str, Any]],
    minutes: Any,
    team: str | None = None,
) -> bytes:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    # Editorial header
    draw.rounded_rectangle((54, 48, WIDTH - 54, 292), radius=32, fill=PANEL_SOFT)
    draw.rounded_rectangle((72, 68, 230, 92), radius=12, fill=ACCENT)
    draw.text((91, 70), "PLAYER STATS", font=_font(16, True), fill=BG)

    if team:
        draw.ellipse((WIDTH - 188, 78, WIDTH - 76, 190), fill=PANEL_DEEP)
        _paste_logo(image, team, (WIDTH - 178, 88), 92)

    name_text = player_name.upper()
    name_font = _fit_font(draw, name_text, 770, 58, 38, True)
    draw.text((78, 116), name_text, font=name_font, fill=TEXT)
    draw.text((78, 200), f"Performance Numbers v {opponent}", font=_font(25), fill=MUTED)
    if team:
        draw.text((78, 244), team.upper(), font=_font(17, True), fill=ACCENT)

    # Stats card
    panel_top = 316
    panel_bottom = HEIGHT - 162 if minutes is not None else HEIGHT - 56
    draw.rounded_rectangle((54, panel_top, WIDTH - 54, panel_bottom), radius=32, fill=PANEL_SOFT)

    visible = rows[:17]
    available_h = panel_bottom - panel_top - 34
    row_h = min(53, max(42, available_h // max(1, len(visible))))
    y = panel_top + 17

    for i, row in enumerate(visible):
        if i % 2 == 0:
            draw.rounded_rectangle((70, y - 2, WIDTH - 70, y + row_h - 5), radius=12, fill=PANEL)
        draw.text((88, y + 7), row["label"], font=_font(24), fill=TEXT)
        value = str(row["display"])
        value_font = _font(27, True)
        vb = draw.textbbox((0, 0), value, font=value_font)
        pill_w = max(86, (vb[2] - vb[0]) + 34)
        pill_x = WIDTH - 86 - pill_w
        draw.rounded_rectangle((pill_x, y + 4, WIDTH - 86, y + 39), radius=17, fill=PANEL_DEEP)
        _right_text(draw, WIDTH - 101, y + 8, value, value_font, TEXT)
        y += row_h

    # Minutes footer remains deliberately separate
    if minutes is not None:
        footer_y = HEIGHT - 138
        draw.rounded_rectangle((54, footer_y, WIDTH - 54, HEIGHT - 54), radius=28, fill=PANEL_DEEP)
        draw.rectangle((54, footer_y, 66, HEIGHT - 54), fill=ACCENT)
        draw.text((84, footer_y + 25), "MINUTES PLAYED", font=_font(22, True), fill=MUTED)
        _right_text(draw, WIDTH - 84, footer_y + 16, str(minutes), _font(38, True), TEXT)

    return _png_bytes(image)


def render_match_graphic(match, rows: list[dict[str, Any]]) -> bytes:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    # Match header
    draw.rounded_rectangle((54, 46, WIDTH - 54, 326), radius=34, fill=PANEL_SOFT)
    draw.rounded_rectangle((72, 66, 260, 92), radius=12, fill=ACCENT)
    draw.text((91, 68), "MATCH STATISTICS", font=_font(16, True), fill=BG)

    home_cx, away_cx = 212, WIDTH - 212
    crest_y = 112
    draw.ellipse((home_cx - 58, crest_y, home_cx + 58, crest_y + 116), fill=PANEL_DEEP)
    draw.ellipse((away_cx - 58, crest_y, away_cx + 58, crest_y + 116), fill=PANEL_DEEP)
    _paste_logo(image, match.home_name, (home_cx - 49, crest_y + 9), 98)
    _paste_logo(image, match.away_name, (away_cx - 49, crest_y + 9), 98)

    score = f"{match.home_score}  –  {match.away_score}"
    _center_text(draw, WIDTH / 2, 126, score, _font(56, True), TEXT)

    home_font = _fit_font(draw, match.home_name.upper(), 330, 22, 16, True)
    away_font = _fit_font(draw, match.away_name.upper(), 330, 22, 16, True)
    _center_text(draw, home_cx, 244, match.home_name.upper(), home_font, TEXT)
    _center_text(draw, away_cx, 244, match.away_name.upper(), away_font, TEXT)

    meta = " · ".join(part for part in (match.tournament, match.date_text) if part)
    _center_text(draw, WIDTH / 2, 286, meta, _font(20), MUTED)

    # Statistics area
    panel_top = 350
    draw.rounded_rectangle((54, panel_top, WIDTH - 54, HEIGHT - 54), radius=34, fill=PANEL_SOFT)
    draw.text((82, panel_top + 24), "HOME", font=_font(16, True), fill=MUTED)
    _right_text(draw, WIDTH - 82, panel_top + 24, "AWAY", _font(16, True), MUTED)
    draw.line((82, panel_top + 55, WIDTH - 82, panel_top + 55), fill=LINE, width=2)

    y = panel_top + 72
    row_h = 32
    max_rows = 26
    current_group = None
    shown = 0

    for row in rows:
        if shown >= max_rows or y > HEIGHT - 90:
            break
        group = row.get("group") or "Statistics"
        if group != current_group:
            if current_group is not None:
                y += 3
            if y > HEIGHT - 110:
                break
            group_label = group.upper()
            draw.rounded_rectangle((82, y, 82 + min(290, 22 + len(group_label) * 10), y + 25), radius=12, fill=PANEL_DEEP)
            draw.text((94, y + 4), group_label, font=_font(14, True), fill=ACCENT)
            y += 31
            current_group = group

        home = "–" if row.get("home") is None else str(row.get("home"))
        away = "–" if row.get("away") is None else str(row.get("away"))
        label = str(row.get("name", ""))

        if shown % 2 == 0:
            draw.rounded_rectangle((74, y - 2, WIDTH - 74, y + 29), radius=10, fill=PANEL)

        draw.text((88, y + 2), home, font=_font(20, True), fill=TEXT)
        _center_text(draw, WIDTH / 2, y + 3, label, _font(17), MUTED)
        _right_text(draw, WIDTH - 88, y + 2, away, _font(20, True), TEXT)
        y += row_h
        shown += 1

    return _png_bytes(image)
