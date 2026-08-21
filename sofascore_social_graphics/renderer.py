from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any
import re

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1080, 1350
BG = (36, 34, 54)          # #242236
CARD = (47, 45, 68)
CARD_2 = (42, 40, 62)
TEXT = (250, 250, 252)
MUTED = (178, 176, 195)
LINE = (70, 67, 94)
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
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value


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
        return
    x, y = xy
    image.paste(logo, (x + (size - logo.width)//2, y + (size - logo.height)//2), logo)


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


def render_player_graphic(player_name: str, opponent: str, rows: list[dict[str, Any]], minutes: Any, team: str | None = None) -> bytes:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((56, 50, WIDTH - 56, 254), radius=28, fill=CARD_2)
    if team:
        _paste_logo(image, team, (WIDTH - 184, 74), 92)
    draw.text((82, 76), "PLAYER STATS", font=_font(25, True), fill=ACCENT)
    name_font = _font(54 if len(player_name) < 21 else 44, True)
    draw.text((82, 116), player_name.upper(), font=name_font, fill=TEXT)
    draw.text((82, 190), f"Performance Numbers v {opponent}", font=_font(25), fill=MUTED)

    panel_top = 278
    panel_bottom = HEIGHT - 166 if minutes is not None else HEIGHT - 62
    draw.rounded_rectangle((56, panel_top, WIDTH - 56, panel_bottom), radius=28, fill=CARD_2)

    visible = rows[:17]
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

    draw.rounded_rectangle((56, 48, WIDTH - 56, 270), radius=28, fill=CARD_2)
    draw.text((82, 72), "MATCH STATISTICS", font=_font(25, True), fill=ACCENT)

    _paste_logo(image, match.home_name, (82, 124), 92)
    _paste_logo(image, match.away_name, (WIDTH - 174, 124), 92)

    score_font = _font(46, True)
    score = f"{match.home_score} – {match.away_score}"
    score_box = draw.textbbox((0, 0), score, font=score_font)
    draw.text(((WIDTH - (score_box[2]-score_box[0]))/2, 130), score, font=score_font, fill=TEXT)

    home_font = _font(21, True)
    away_font = _font(21, True)
    draw.text((184, 144), match.home_name.upper(), font=home_font, fill=TEXT)
    away_box = draw.textbbox((0,0), match.away_name.upper(), font=away_font)
    draw.text((WIDTH - 184 - (away_box[2]-away_box[0]), 144), match.away_name.upper(), font=away_font, fill=TEXT)

    meta = " · ".join(part for part in (match.tournament, match.date_text) if part)
    meta_font = _font(21)
    mb = draw.textbbox((0,0), meta, font=meta_font)
    draw.text(((WIDTH-(mb[2]-mb[0]))/2, 218), meta, font=meta_font, fill=MUTED)

    draw.rounded_rectangle((56, 292, WIDTH - 56, HEIGHT - 56), radius=28, fill=CARD_2)
    left_x, right_x = 82, WIDTH - 82
    header_y = 316
    draw.text((left_x, header_y), match.home_name.upper(), font=_font(20, True), fill=MUTED)
    _right_text(draw, right_x, header_y, match.away_name.upper(), _font(20, True), MUTED)
    draw.line((82, 354, WIDTH - 82, 354), fill=LINE, width=2)

    y = 374
    row_h = 39
    current_group = None
    shown = 0
    for row in rows:
        if shown >= 22:
            break
        group = row.get("group") or "Statistics"
        if group != current_group:
            if current_group is not None:
                y += 4
            if y > HEIGHT - 105:
                break
            draw.text((82, y), group.upper(), font=_font(17, True), fill=ACCENT)
            y += 28
            current_group = group
        if y > HEIGHT - 100:
            break
        home = "–" if row.get("home") is None else str(row.get("home"))
        away = "–" if row.get("away") is None else str(row.get("away"))
        label = str(row.get("name", ""))
        draw.text((82, y + 3), home, font=_font(21, True), fill=TEXT)
        label_font = _font(19)
        lb = draw.textbbox((0,0), label, font=label_font)
        draw.text(((WIDTH-(lb[2]-lb[0]))/2, y + 4), label, font=label_font, fill=MUTED)
        _right_text(draw, WIDTH - 82, y + 3, away, _font(21, True), TEXT)
        draw.line((82, y + 32, WIDTH - 82, y + 32), fill=LINE, width=1)
        y += row_h
        shown += 1

    return _png_bytes(image)
