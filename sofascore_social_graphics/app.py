from __future__ import annotations

import streamlit as st

from parsers import build_player_stat_rows, extract_match_statistics, extract_players, parse_match_info
from renderer import render_match_graphic, render_player_graphic
from sofascore_client import SofaScoreClient, SofaScoreError, extract_event_id

st.set_page_config(page_title="MatchLab", page_icon="⚽", layout="wide")

st.markdown(
    """
    <style>
    .stApp { background-color: #242236; color: #fafafc; }
    [data-testid="stSidebar"] { background-color: #1e1c2e; }
    [data-testid="stHeader"] { background: rgba(0,0,0,0); }
    h1, h2, h3, p, label { color: #fafafc; }
    .stCaption, [data-testid="stCaptionContainer"] { color: #b2b0c3 !important; }
    div[data-testid="stMetric"], div[data-testid="stExpander"] {
        background: #2f2d44;
        border: 1px solid #46435e;
        border-radius: 14px;
    }
    .stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
        background: #cfff46;
        color: #242236;
        border: 0;
        font-weight: 700;
    }
    .stButton > button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover {
        background: #dcff78;
        color: #242236;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("MatchLab")
st.caption("SofaScore match and player performance graphics · 1080 × 1350")

client = SofaScoreClient()

with st.sidebar:
    st.header("Load match")
    match_input = st.text_input(
        "SofaScore URL or Event ID",
        value="https://www.sofascore.com/football/match/arsenal-west-ham-united/MR#id:14023942,tab:lineups",
    )
    refresh = st.checkbox("Refresh cached data", value=False)
    load_clicked = st.button("Load Match", type="primary", use_container_width=True)
    st.caption("Paste any SofaScore match URL. MatchLab extracts the event ID automatically.")

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

st.success(f"{match.home_name} {match.home_score}–{match.away_score} {match.away_name}")
if match.tournament or match.date_text:
    st.caption(" · ".join(x for x in (match.tournament, match.date_text) if x))

graphic_type = st.radio("Graphic", ["Match Statistics", "Player Statistics"], horizontal=True)

if graphic_type == "Match Statistics":
    png = render_match_graphic(match, match_rows)
    preview_col, action_col = st.columns([2, 1])
    with preview_col:
        st.image(png, caption="1080 × 1350 preview", width=540)
    with action_col:
        st.subheader("Match Statistics")
        st.caption("Full-time SofaScore performance numbers for both teams.")
        st.download_button(
            "Download PNG",
            data=png,
            file_name=f"{match.event_id}_match_stats.png",
            mime="image/png",
            type="primary",
            use_container_width=True,
        )
        with st.expander("View all statistics"):
            st.dataframe(match_rows, use_container_width=True, hide_index=True)

else:
    if not players:
        st.warning("No player statistics were returned in this match's lineups payload.")
        st.stop()

    control_col, preview_col = st.columns([1, 2])
    with control_col:
        st.subheader("Player")
        teams = list(dict.fromkeys(p.team for p in players))
        team = st.selectbox("Team", teams)
        team_players = [p for p in players if p.team == team]
        selected_name = st.selectbox("Player", [p.name for p in team_players])
        player = next(p for p in team_players if p.name == selected_name)
        hide_zero = st.checkbox("Hide zero-value statistics", value=True)
        rows, minutes = build_player_stat_rows(player.stats, hide_zero=hide_zero)

        png = render_player_graphic(player.name, player.opponent, rows, minutes, team=player.team)
        st.download_button(
            "Download Player PNG",
            data=png,
            file_name=f"{match.event_id}_{player.name.lower().replace(' ', '_')}.png",
            mime="image/png",
            type="primary",
            use_container_width=True,
        )
        with st.expander("Inspect player data"):
            st.dataframe(rows, use_container_width=True, hide_index=True)
            st.json(player.stats)

    with preview_col:
        st.image(png, caption="1080 × 1350 preview", width=540)
