from __future__ import annotations

from typing import Any
from PIL import Image, ImageDraw
from renderer import WIDTH, HEIGHT, BG, PANEL_SOFT, PANEL_DEEP, TEXT, MUTED, LINE, ACCENT, _font, _png_bytes, _paste_logo, _right_text, _fit_font

GOLD=(230,185,74); SILVER=(191,195,204); BRONZE=(199,132,83)


def _rank_badge(draw, x:int, y:int, rank:int):
    if rank==1: fill,text,label=GOLD,BG,"1st"
    elif rank==2: fill,text,label=SILVER,BG,"2nd"
    elif rank==3: fill,text,label=BRONZE,BG,"3rd"
    else: fill,text,label=PANEL_DEEP,MUTED,str(rank)
    w=68 if rank<=3 else 52
    draw.rounded_rectangle((x,y,x+w,y+32),radius=6,fill=fill)
    f=_font(14 if rank<=3 else 16,True); b=draw.textbbox((0,0),label,font=f)
    draw.text((x+(w-(b[2]-b[0]))/2,y+7),label,font=f,fill=text)


def render_metric_leaders(match, metric_label:str, scope_label:str, rows:list[dict[str,Any]]) -> bytes:
    """Leaderboard using the same hero + compact row language as Player Stats."""
    image=Image.new("RGB",(WIDTH,HEIGHT),BG); draw=ImageDraw.Draw(image)
    draw.text((76,82),"METRIC LEADERS",font=_font(15,True),fill=ACCENT)
    metric_font=_fit_font(draw,metric_label.upper(),900,52,30,True)
    draw.text((76,116),metric_label.upper(),font=metric_font,fill=TEXT)
    match_text=f"{match.home_name} {match.home_score}–{match.away_score} {match.away_name}"
    draw.text((78,188),scope_label,font=_font(18,True),fill=MUTED)
    draw.text((78,222),"  |  ".join(x for x in (match_text,match.date_text,match.tournament) if x),font=_font(15,True),fill=MUTED)
    draw.line((70,278,WIDTH-70,278),fill=LINE,width=1)

    if not rows:
        draw.text((78,340),"No player data available for this metric.",font=_font(24),fill=MUTED); return _png_bytes(image)

    values=[float(r.get("value") or 0) for r in rows if isinstance(r.get("value"),(int,float))]
    max_value=max(values or [1]); y=312; row_h=86
    for idx,row in enumerate(rows[:10],start=1):
        if y+row_h>HEIGHT-72: break
        draw.rounded_rectangle((70,y,WIDTH-70,y+row_h-8),radius=10,fill=PANEL_SOFT,outline=(60,57,83))
        _rank_badge(draw,84,y+23,idx)
        team=str(row.get("team", "")); _paste_logo(image,team,(170,y+16),46)
        name=str(row.get("name", "")); draw.text((232,y+14),name,font=_fit_font(draw,name,350,23,17,True),fill=TEXT)
        draw.text((232,y+47),team,font=_fit_font(draw,team,350,15,12,False),fill=MUTED)
        display=str(row.get("display", "")); _right_text(draw,690,y+18,display,_font(28,True),TEXT)
        raw=row.get("value"); pct=(float(raw)/max_value) if isinstance(raw,(int,float)) and max_value else 0
        bx1,bx2,by=720,994,y+39; draw.rounded_rectangle((bx1,by,bx2,by+6),radius=3,fill=(57,54,79)); draw.rounded_rectangle((bx1,by,bx1+max(8,int((bx2-bx1)*pct)),by+6),radius=3,fill=ACCENT)
        y+=row_h

    draw.text((70,HEIGHT-52),f"{len(rows)} QUALIFYING PLAYERS",font=_font(14,True),fill=MUTED)
    _right_text(draw,WIDTH-70,HEIGHT-52,"LUFCDATA.LAB",_font(15,True),MUTED)
    return _png_bytes(image)
