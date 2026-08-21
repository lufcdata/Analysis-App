# SofaScore Social Graphics

Purpose-built Streamlit app for turning a SofaScore match into 1080 × 1350 social graphics.

## V1 workflow

1. Paste a SofaScore match URL or event ID.
2. Load the match.
3. Choose **Match Statistics** or **Player Statistics**.
4. For player graphics, select the team and player.
5. Preview the 1080 × 1350 output.
6. Download the PNG.

The default test event is `14023942` (West Ham United v Arsenal).

## Local run

```bash
cd sofascore_social_graphics
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud

When deploying this repository, set the main file path to:

```text
sofascore_social_graphics/app.py
```

The app fetches and caches these SofaScore slices for each event:

- `/event/{event_id}`
- `/event/{event_id}/statistics`
- `/event/{event_id}/lineups`

Cached responses are stored locally under `data/cache/<event_id>/` and should not be committed.

## V1 presentation rules

- Match statistics use the full-match `ALL` period where available.
- Player statistics hide zero-value rows by default.
- Paired stats such as accurate passes and long balls display as successful/attempted.
- Player rows sort by their successful/numeric value from highest to lowest.
- Minutes played is pinned separately at the bottom.
- PNG output is fixed at 1080 × 1350.
