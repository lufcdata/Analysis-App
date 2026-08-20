from __future__ import annotations

from urllib.parse import quote

LOGO_DIR = "assets/team_logos"

TEAM_LOGO_FILES: dict[str, str] = {
    "Arsenal": "Arsenal.png",
    "Aston Villa": "Aston Villa.png",
    "Bournemouth": "Bournemouth.png",
    "Brentford": "Brentford.png",
    "Brighton & Hove Albion": "Brighton.png",
    "Brighton and Hove Albion": "Brighton.png",
    "Brighton": "Brighton.png",
    "Burnley": "Burnley.png",
    "Chelsea": "Chelsea.png",
    "Crystal Palace": "Crystal Palace.png",
    "Everton": "Everton.png",
    "Fulham": "Fulham.png",
    "Leeds United": "Leeds.png",
    "Leeds": "Leeds.png",
    "Liverpool": "Liverpool.png",
    "Manchester City": "Manchester City.png",
    "Manchester United": "Manchester United.png",
    "Newcastle United": "Newcastle United.png",
    "Nottingham Forest": "Nottingham Forest.png",
    "Sunderland": "Sunderland.png",
    "Tottenham Hotspur": "Tottenham.png",
    "Tottenham": "Tottenham.png",
    "West Ham United": "West Ham.png",
    "West Ham": "West Ham.png",
    "Wolverhampton Wanderers": "Wolves.png",
    "Wolves": "Wolves.png",
    "Coventry City": "Coventry City.png",
    "Hull City": "Hull City.png",
    "Ipswich Town": "Ipswich Town.png",
}


def logo_filename(team_name: str | None) -> str | None:
    if not team_name:
        return None
    return TEAM_LOGO_FILES.get(str(team_name).strip())


def logo_path(team_name: str | None) -> str | None:
    filename = logo_filename(team_name)
    return f"{LOGO_DIR}/{filename}" if filename else None


def logo_url(team_name: str | None) -> str | None:
    path = logo_path(team_name)
    return "/" + quote(path, safe="/") if path else None
