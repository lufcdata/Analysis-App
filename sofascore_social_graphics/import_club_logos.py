from __future__ import annotations

import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

SOURCE_MAP = {
    "Arsenal": "Arsenal.png",
    "Aston Villa": "Aston Villa.png",
    "Bournemouth": "Bournemouth.png",
    "Brentford": "Brentford.png",
    "Brighton & Hove Albion": "Brighton & Hove Albion.png",
    "Burnley": "Burnley.png",
    "Chelsea": "Chelsea.png",
    "Crystal Palace": "Crystal Palace.png",
    "Everton": "Everton.png",
    "Fulham": "Fulham.png",
    "Leeds United": "leeds png.png",
    "Liverpool": "Liverpool.png",
    "Manchester City": "Manchester City.png",
    "Manchester United": "Manchester United.png",
    "Newcastle United": "Newcastle United.png",
    "Nottingham Forest": "Nottingham Forest.png",
    "Sunderland": "Sunderland.png",
    "Tottenham Hotspur": "Tottenham.png",
    "West Ham United": "West Ham.png",
    "Wolverhampton Wanderers": "Wolves.png",
}

DEST_MAP = {
    "Arsenal": "arsenal.png",
    "Aston Villa": "aston-villa.png",
    "Bournemouth": "bournemouth.png",
    "Brentford": "brentford.png",
    "Brighton & Hove Albion": "brighton-hove-albion.png",
    "Burnley": "burnley.png",
    "Chelsea": "chelsea.png",
    "Crystal Palace": "crystal-palace.png",
    "Everton": "everton.png",
    "Fulham": "fulham.png",
    "Leeds United": "leeds-united.png",
    "Liverpool": "liverpool.png",
    "Manchester City": "manchester-city.png",
    "Manchester United": "manchester-united.png",
    "Newcastle United": "newcastle-united.png",
    "Nottingham Forest": "nottingham-forest.png",
    "Sunderland": "sunderland.png",
    "Tottenham Hotspur": "tottenham-hotspur.png",
    "West Ham United": "west-ham-united.png",
    "Wolverhampton Wanderers": "wolverhampton-wanderers.png",
}


def find_file(root: Path, filename: str) -> Path | None:
    matches = list(root.rglob(filename))
    return matches[0] if matches else None


def main():
    if len(sys.argv) < 2:
        print('Usage: python import_club_logos.py "/path/to/CLUB APP LOGOS.zip"')
        raise SystemExit(2)

    zip_path = Path(sys.argv[1]).expanduser().resolve()
    if not zip_path.exists():
        print(f"ZIP not found: {zip_path}")
        raise SystemExit(1)

    dest = Path(__file__).parent / "assets" / "clubs"
    dest.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp_root)

        copied = 0
        missing = []
        for team, source_name in SOURCE_MAP.items():
            src = find_file(tmp_root, source_name)
            if src is None:
                missing.append(f"{team} ({source_name})")
                continue
            shutil.copy2(src, dest / DEST_MAP[team])
            copied += 1
            print(f"✓ {team}")

    print(f"\nImported {copied} club logos to {dest}")
    if missing:
        print("Missing:")
        for item in missing:
            print(f"- {item}")


if __name__ == "__main__":
    main()
