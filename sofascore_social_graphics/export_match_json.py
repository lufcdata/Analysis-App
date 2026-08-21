from __future__ import annotations

import json
from pathlib import Path

from sofascore_client import SofaScoreClient, extract_event_id


def main() -> None:
    print("\nMatchLab Local SofaScore Exporter")
    print("Paste a SofaScore match URL or event ID, then press Return.\n")
    source = input("SofaScore match: ").strip()
    if not source:
        raise SystemExit("No match URL or event ID supplied.")

    event_id = extract_event_id(source)
    client = SofaScoreClient(cache_dir=Path(__file__).resolve().parent / "data" / "cache")

    print(f"\nFetching event {event_id} from SofaScore…")
    match = client.fetch_match(event_id, refresh=True)

    bundle = {
        "event_id": str(event_id),
        "basic": match["basic"],
        "statistics": match["statistics"],
        "lineups": match["lineups"],
    }

    downloads = Path.home() / "Downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    output = downloads / f"MatchLab_{event_id}.json"
    output.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n✓ Match downloaded successfully")
    print(f"✓ MatchLab JSON saved to:\n  {output}")
    print("\nNext: open matchlab-web.vercel.app and click Upload Match JSON.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\n✗ Export failed: {exc}")
        raise
