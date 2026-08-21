from __future__ import annotations

import streamlit as st

from parsers import build_player_stat_rows, extract_match_statistics, extract_players, parse_match_info
from renderer import render_match_graphic, render_player_graphic
from sofascore_client import SofaScoreClient, SofaScoreError, extract_event_id

st.set_page_config(page_title="SofaScore Social Graphics", page_icon="⚽", layout="wide")

st.title("SofaScore Social Graphics")
st.caption("Paste a SofaScore match URL, select a graphic, and export a 1080 × 1350 PNG.")

client = SofaScoreClient()

with st.sidebar:
    st.header("Match")
    match_input = st.text_input(
        "SofaScore URL or Event ID",
        value="https://www.sofascore.com/football/match/arsenal-west-ham-united/MR#id:14023942,tab:lineups",
    )
    refresh = st.checkbox("Refresh cached data", value=False)
    load_clicked = st.button("Load Match", type="primary", use_container_width=True)

if load_clicked or "match_payload" not in st.session_state:
    try:
        event_id = extract_event_id(match_input)
        with st.spinner(f"Loading SofaScore event {event_id}…"):
            st.session_state.match_payload = client.fetch_match(event_id, refresh=refresh)
            st.session_state.event_id = event_id
    except (ValueError, SofaScoreError) as exc:
        st.error(str(exc))
        st.stop()

payload = st.session_state.match_payload
match = parse_match_info(payload["basic"])
match_rows = extract_match_statistics(payload["statistics"])
players = extract_players(payload["lineups"], match)

st.success(f"Loaded: {match.home_name} {match.home_score}–{match.away_score} {match.away_name}")
if match.tournament or match.date_text:
    st.caption(" · ".join(x for x in (match.tournament, match.date_text) if x))

graphic_type = st.radio("Graphic Type", ["Match Statistics", "Player Statistics"], horizontal=True)

if graphic_type == "Match Statistics":
    png = render_match_graphic(match, match_rows)
    st.image(png, caption="1080 × 1350 preview", width=540)
    st.download_button(
        "Download Match Statistics PNG",
        data=png,
        file_name=f"{match.event_id}_match_stats.png",
        mime="image/png",
        type="primary",
    )
    with st.expander("View all parsed match statistics"):
        st.dataframe(match_rows, use_container_width=True, hide_index=True)

else:
    if not players:
        st.warning("No player statistics were returned in this match's lineups payload.")
        st.stop()

    teams = list(dict.fromkeys(p.team for p in players))
    team = st.selectbox("Team", teams)
    team_players = [p for p in players if p.team == team]
    selected_name = st.selectbox("Player", [p.name for p in team_players])
    player = next(p for p in team_players if p.name == selected_name)

    hide_zero = st.checkbox("Hide zero-value statistics", value=True)
    rows, minutes = build_player_stat_rows(player.stats, hide_zero=hide_zero)

    png = render_player_graphic(player.name, player.opponent, rows, minutes)
    st.image(png, caption="1080 × 1350 preview", width=540)
    st.download_button(
        "Download Player Statistics PNG",
        data=png,
        file_name=f"{match.event_id}_{player.name.lower().replace(' ', '_')}.png",
        mime="image/png",
        type="primary",
    )

    with st.expander("View parsed player statistics"):
        st.dataframe(rows, use_container_width=True, hide_index=True)
        st.json(player.stats)
