# MatchLab local SofaScore exporter on macOS

SofaScore blocks the hosted MatchLab/Render server, but the SofaScore API is reachable from the user's Mac. The recommended production workflow is therefore:

**SofaScore -> local Mac exporter -> MatchLab JSON -> matchlab-web.vercel.app**

The hosted MatchLab site then stores and renders the imported match without needing to scrape SofaScore again.

## Export a match locally

1. Open the `sofascore_social_graphics` folder on the Mac.
2. Double-click `Export Match JSON.command`.
3. Paste a SofaScore match URL or event ID into the Terminal window and press Return.
4. The exporter fetches the match details, statistics and lineups using the existing local `SofaScoreClient`.
5. A file named `MatchLab_<event_id>.json` is written to the Mac's Downloads folder.
6. The Downloads folder opens automatically when the export succeeds.

On the first run the launcher creates a private `.venv` and installs the local requirements. Later runs reuse that environment.

## Upload into the live MatchLab site

1. Open `https://matchlab-web.vercel.app`.
2. Click **Upload Match JSON** in the left sidebar.
3. Select the `MatchLab_<event_id>.json` file from Downloads.
4. The match is added to **Imported matches** and becomes available to Match Statistics, Player Statistics and Metric Leaders.

## JSON bundle format

The exporter creates the exact structure expected by the MatchLab API:

```json
{
  "event_id": "14023942",
  "basic": {},
  "statistics": {},
  "lineups": {}
}
```

## Test match

`https://www.sofascore.com/football/match/arsenal-west-ham-united/MR#id:14023942,tab:lineups`

## Existing full local MatchLab

The older full local Streamlit workflow is still available through `Start MatchLab.command` if needed. It caches downloaded match JSON locally so changing players does not re-fetch the match.
