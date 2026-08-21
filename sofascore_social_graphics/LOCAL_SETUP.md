# Run MatchLab locally on macOS

SofaScore currently blocks requests from Streamlit Community Cloud, but the SofaScore API is reachable from the user's Mac. Running MatchLab locally preserves the intended workflow: paste a SofaScore match URL, click Load Match, select a graphic/player, export PNG.

## First run

1. Download the `feature/sofascore-social-graphics-v1` branch as a ZIP from GitHub.
2. Unzip it.
3. Open the `sofascore_social_graphics` folder.
4. Double-click `Start MatchLab.command`.
5. macOS may ask for permission on the first launch. If Gatekeeper blocks it, right-click the file and choose **Open**.
6. The launcher creates a private `.venv`, installs the requirements, and starts MatchLab at `http://127.0.0.1:8501`.

## Normal use afterwards

Double-click `Start MatchLab.command`. Paste a SofaScore match URL and click **Load Match**.

## Test match

`https://www.sofascore.com/football/match/arsenal-west-ham-united/MR#id:14023942,tab:lineups`

The app caches downloaded match JSON locally so changing players does not re-fetch the match.
