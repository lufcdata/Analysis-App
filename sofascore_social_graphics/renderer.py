from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any
import re

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1080, 1350
BG = (36, 34, 54)
PANEL = (46, 43, 68)
PANEL_SOFT = (42, 40, 62)
PANEL_DEEP = (31, 29, 47)
TEXT = (250, 250, 252)
MUTED = (178, 176, 195)
LINE = (72, 69, 98)
ACCENT = (72, 240, 202)
ASSET_ROOT = Path(__file__).parent / "assets"
ASSET_DIR = ASSET_ROOT / "clubs"
PLAYER_ASSET_DIR = ASSET_ROOT / "players"

CLUB_SLUGS = {
    "Brighton & Hove Albion": "brighton-hove-albion", "Leeds United": "leeds-united",
    "Manchester City": "manchester-city", "Manchester United": "manchester-united",
    "Newcastle United": "newcastle-united", "Nottingham Forest": "nottingham-forest",
    "Tottenham Hotspur": "tottenham-hotspur", "Tottenham": "tottenham-hotspur",
    "West Ham United": "west-ham-united", "Wolverhampton Wanderers": "wolverhampton-wanderers",
    "Wolves": "wolverhampton-wanderers",
}


def _slugify(name: str) -> str:
    if name in CLUB_SLUGS:
        return CLUB_SLUGS[name]
    value = name.lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


def _club_logo(name: str, size: int = 104):
    path = ASSET_DIR / f"{_slugify(name)}.png"
    if not path.exists(): return None
    try:
        logo = Image.open(path).convert("RGBA"); logo.thumbnail((size, size), Image.Resampling.LANCZOS); return logo
    except Exception: return None


def _paste_logo(image: Image.Image, name: str, xy: tuple[int, int], size: int = 104):
    logo = _club_logo(name, size)
    if logo is None: return False
    x, y = xy; image.paste(logo, (x + (size-logo.width)//2, y + (size-logo.height)//2), logo); return True


def _normalise_player_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _player_image(name: str, max_size: tuple[int, int] = (260, 260)):
    if not PLAYER_ASSET_DIR.exists(): return None
    target = _normalise_player_name(name)
    for path in PLAYER_ASSET_DIR.iterdir():
        if not path.is_file() or path.suffix.lower() not in {".png", ".webp", ".jpg", ".jpeg"}: continue
        stem = re.sub(r"\s+icon$", "", path.stem, flags=re.I)
        if _normalise_player_name(stem) == target:
            try:
                pic = Image.open(path).convert("RGBA"); pic.thumbnail(max_size, Image.Resampling.LANCZOS); return pic
            except Exception: return None
    return None


def _font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists(): return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _png_bytes(image: Image.Image) -> bytes:
    output = BytesIO(); image.save(output, format="PNG", optimize=True); return output.getvalue()


def _right_text(draw, x_right, y, text, font, fill):
    bbox = draw.textbbox((0,0), str(text), font=font); draw.text((x_right-(bbox[2]-bbox[0]), y), str(text), font=font, fill=fill)


def _center_text(draw, cx, y, text, font, fill):
    bbox = draw.textbbox((0,0), str(text), font=font); draw.text((cx-(bbox[2]-bbox[0])/2, y), str(text), font=font, fill=fill)


def _fit_font(draw, text: str, max_width: int, start_size: int, min_size: int = 24, bold: bool = True):
    size = start_size
    while size > min_size:
        font = _font(size, bold); bbox = draw.textbbox((0,0), text, font=font)
        if bbox[2]-bbox[0] <= max_width: return font
        size -= 2
    return _font(min_size, bold)


def render_player_graphic(player_name: str, opponent: str, rows: list[dict[str, Any]], minutes: Any, team: str | None = None, match: Any | None = None) -> bytes:
    """Bolt-inspired Player Stats card with optional local player cut-out."""
    image = Image.new("RGB", (WIDTH, HEIGHT), BG); draw = ImageDraw.Draw(image)

    # Player hero: cut-out on the left, identity on the right. Falls back cleanly when no image exists.
    hero_bottom = 310
    draw.line((70, hero_bottom, WIDTH-70, hero_bottom), fill=LINE, width=1)
    pic = _player_image(player_name, (260, 260))
    if pic:
        px = 92 + (250-pic.width)//2; py = hero_bottom - pic.height
        image.paste(pic, (px, py), pic)
    else:
        draw.ellipse((128, 92, 300, 264), outline=(110,108,135), width=2, fill=PANEL_SOFT)
        _center_text(draw, 214, 148, player_name[:1].upper(), _font(64, True), TEXT)

    text_x = 390
    name_font = _fit_font(draw, player_name, 600, 54, 34, True)
    draw.text((text_x, 105), player_name, font=name_font, fill=TEXT)
    meta_parts = [f"v {opponent}"]
    if match is not None:
        if getattr(match, "date_text", None): meta_parts.append(str(match.date_text))
        if getattr(match, "tournament", None): meta_parts.append(str(match.tournament))
    draw.text((text_x, 178), "  |  ".join(meta_parts), font=_font(18, True), fill=MUTED)
    if team:
        _paste_logo(image, team, (text_x, 220), 54)
        draw.text((text_x+68, 236), team.upper(), font=_font(16, True), fill=ACCENT)

    visible = rows[:17]
    panel_top, panel_bottom = 332, HEIGHT-82
    max_numeric = max([float(r.get("value") or 0) for r in visible if isinstance(r.get("value"), (int,float))] or [1])
    row_h = min(54, max(44, (panel_bottom-panel_top-20)//max(1,len(visible))))
    y = panel_top
    for i, row in enumerate(visible):
        draw.rounded_rectangle((70, y, WIDTH-70, y+row_h-6), radius=10, fill=PANEL_SOFT, outline=(60,57,83))
        if team: _paste_logo(image, team, (84, y+7), 32)
        draw.text((142, y+13), str(row["label"]), font=_font(17, True), fill=MUTED)
        display = str(row["display"]); _right_text(draw, 680, y+9, display, _font(23, True), TEXT)
        raw = row.get("value")
        pct = (float(raw)/max_numeric) if isinstance(raw,(int,float)) and max_numeric else 0
        bx1, bx2, by = 720, 900, y+24
        draw.rounded_rectangle((bx1, by, bx2, by+5), radius=3, fill=(57,54,79))
        draw.rounded_rectangle((bx1, by, bx1+max(8,int((bx2-bx1)*pct)), by+5), radius=3, fill=ACCENT)
        # Minutes are useful context in place of Bolt's placeholder Upgrade button.
        badge = f"{minutes}'" if minutes is not None else "STAT"
        draw.rounded_rectangle((922, y+10, 994, y+38), radius=6, fill=ACCENT)
        _center_text(draw, 958, y+15, badge, _font(11, True), BG)
        y += row_h

    draw.text((70, HEIGHT-52), "LUFCDATA.LAB", font=_font(15, True), fill=MUTED)
    return _png_bytes(image)


def render_match_graphic(match, rows: list[dict[str, Any]]) -> bytes:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG); draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((54,46,WIDTH-54,326), radius=34, fill=PANEL_SOFT)
    draw.rounded_rectangle((72,66,260,92), radius=12, fill=ACCENT); draw.text((91,68), "MATCH STATISTICS", font=_font(16,True), fill=BG)
    home_cx, away_cx = 212, WIDTH-212; crest_y=112
    draw.ellipse((home_cx-58,crest_y,home_cx+58,crest_y+116), fill=PANEL_DEEP); draw.ellipse((away_cx-58,crest_y,away_cx+58,crest_y+116), fill=PANEL_DEEP)
    _paste_logo(image,match.home_name,(home_cx-49,crest_y+9),98); _paste_logo(image,match.away_name,(away_cx-49,crest_y+9),98)
    _center_text(draw,WIDTH/2,126,f"{match.home_score}  –  {match.away_score}",_font(56,True),TEXT)
    _center_text(draw,home_cx,244,match.home_name.upper(),_fit_font(draw,match.home_name.upper(),330,22,16,True),TEXT)
    _center_text(draw,away_cx,244,match.away_name.upper(),_fit_font(draw,match.away_name.upper(),330,22,16,True),TEXT)
    meta=" · ".join(part for part in (match.tournament,match.date_text) if part); _center_text(draw,WIDTH/2,286,meta,_font(20),MUTED)
    panel_top=350; draw.rounded_rectangle((54,panel_top,WIDTH-54,HEIGHT-54),radius=34,fill=PANEL_SOFT)
    draw.text((82,panel_top+24),"HOME",font=_font(16,True),fill=MUTED); _right_text(draw,WIDTH-82,panel_top+24,"AWAY",_font(16,True),MUTED); draw.line((82,panel_top+55,WIDTH-82,panel_top+55),fill=LINE,width=2)
    y=panel_top+72; current_group=None; shown=0
    for row in rows:
        if shown>=26 or y>HEIGHT-90: break
        group=row.get("group") or "Statistics"
        if group!=current_group:
            if current_group is not None: y+=3
            if y>HEIGHT-110: break
            gl=group.upper(); draw.rounded_rectangle((82,y,82+min(290,22+len(gl)*10),y+25),radius=12,fill=PANEL_DEEP); draw.text((94,y+4),gl,font=_font(14,True),fill=ACCENT); y+=31; current_group=group
        home="–" if row.get("home") is None else str(row.get("home")); away="–" if row.get("away") is None else str(row.get("away")); label=str(row.get("name", ""))
        if shown%2==0: draw.rounded_rectangle((74,y-2,WIDTH-74,y+29),radius=10,fill=PANEL)
        draw.text((88,y+2),home,font=_font(20,True),fill=TEXT); _center_text(draw,WIDTH/2,y+3,label,_font(17),MUTED); _right_text(draw,WIDTH-88,y+2,away,_font(20,True),TEXT); y+=32; shown+=1
    return _png_bytes(image)
