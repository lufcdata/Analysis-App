from __future__ import annotations

import streamlit as st

from leader_renderer import render_metric_leaders
from metrics import available_player_metrics
from parsers import available_match_periods, build_metric_leader_rows, build_player_stat_rows, extract_match_statistics, extract_players, parse_match_info
from renderer import render_match_graphic, render_player_graphic
from sofascore_client import SofaScoreClient, SofaScoreError, extract_event_id

st.set_page_config(page_title="MatchLab V2", page_icon="⚽", layout="wide")
st.markdown("""
<style>
.stApp { background-color:#242236; color:#fafafc; } [data-testid="stSidebar"] { background-color:#1e1c2e; border-right:1px solid #343149; }
[data-testid="stHeader"] { background:rgba(0,0,0,0); } .block-container { padding-top:2.1rem; max-width:1500px; } h1,h2,h3,p,label { color:#fafafc; } h1 { letter-spacing:-.04em; }
.stCaption,[data-testid="stCaptionContainer"] { color:#b2b0c3!important; } div[data-testid="stExpander"] { background:#2f2d44; border:1px solid #46435e; border-radius:16px; }
div[data-baseweb="select"]>div,.stTextInput input { background-color:#2f2d44!important; color:#fafafc!important; border-color:#46435e!important; }
.stButton>button[kind="primary"],.stDownloadButton>button[kind="primary"] { background:#cfff46; color:#242236; border:0; font-weight:800; border-radius:12px; }
div[role="radiogroup"] { gap:.7rem; } div[role="radiogroup"] label { background:#2f2d44; border:1px solid #46435e; padding:.45rem .75rem; border-radius:12px; }
</style>""", unsafe_allow_html=True)

st.title("MatchLab V2"); st.caption("Match statistics · Player performance · Metric leaders · 1080 × 1350")
client=SofaScoreClient()
with st.sidebar:
    st.header("Load match")
    match_input=st.text_input("SofaScore URL or Event ID",value="https://www.sofascore.com/football/match/arsenal-west-ham-united/MR#id:14023942,tab:lineups")
    refresh=st.checkbox("Refresh cached data",value=False); load_clicked=st.button("Load Match",type="primary",width="stretch")
    st.caption("Paste any SofaScore match URL. MatchLab extracts the event ID automatically.")
if load_clicked or "match_payload" not in st.session_state:
    try:
        event_id=extract_event_id(match_input)
        with st.spinner(f"Loading SofaScore event {event_id}…"):
            st.session_state.match_payload=client.fetch_match(event_id,refresh=refresh); st.session_state.event_id=event_id
    except (ValueError,SofaScoreError) as exc: st.error(str(exc)); st.stop()

payload=st.session_state.match_payload; match=parse_match_info(payload["basic"]); players=extract_players(payload["lineups"],match)
st.success(f"Loaded · {match.home_name} {match.home_score}–{match.away_score} {match.away_name}")
if match.tournament or match.date_text: st.caption(" · ".join(x for x in (match.tournament,match.date_text) if x))
graphic_type=st.radio("Graphic",["Match Statistics","Player Statistics","Metric Leaders"],horizontal=True)

if graphic_type=="Match Statistics":
    periods=available_match_periods(payload["statistics"])
    if not periods: st.warning("No period-specific match statistics were returned by SofaScore."); st.stop()
    period_map={label:key for key,label in periods}; period_label=st.radio("Period",list(period_map.keys()),horizontal=True); period_key=period_map[period_label]
    match_rows=extract_match_statistics(payload["statistics"],period=period_key)
    png=render_match_graphic(match,match_rows); preview_col,action_col=st.columns([2.15,.85],gap="large")
    with preview_col: st.image(png,caption=f"{period_label} · 1080 × 1350 preview",width=540)
    with action_col:
        st.subheader("Match Statistics"); st.caption(f"Real SofaScore {period_label.lower()} statistics. No full-match values are divided or estimated.")
        st.download_button("Download PNG",data=png,file_name=f"{match.event_id}_{period_key.lower()}_match_stats.png",mime="image/png",type="primary",width="stretch")
        with st.expander("View all statistics"): st.dataframe(match_rows,width="stretch",hide_index=True)

elif graphic_type=="Player Statistics":
    if not players: st.warning("No player statistics were returned in this match's lineups payload."); st.stop()
    st.radio("Period",["Full Match","1st Half","2nd Half"],horizontal=True,key="player_period",disabled=True)
    st.caption("Half-specific Player Stats will unlock only from event-derived player actions. MatchLab will not estimate them from full-match totals.")
    control_col,preview_col=st.columns([.9,2.1],gap="large")
    with control_col:
        st.subheader("Player"); teams=list(dict.fromkeys(p.team for p in players)); team=st.selectbox("Team",teams); team_players=[p for p in players if p.team==team]
        selected_name=st.selectbox("Player",[p.name for p in team_players]); player=next(p for p in team_players if p.name==selected_name); hide_zero=st.checkbox("Hide zero-value statistics",value=True)
        rows,minutes=build_player_stat_rows(player.stats,hide_zero=hide_zero); png=render_player_graphic(player.name,player.opponent,rows,minutes,team=player.team,match=match)
        st.download_button("Download Player PNG",data=png,file_name=f"{match.event_id}_{player.name.lower().replace(' ','_')}.png",mime="image/png",type="primary",width="stretch")
        with st.expander("Inspect player data"): st.dataframe(rows,width="stretch",hide_index=True); st.json(player.stats)
    with preview_col: st.image(png,caption="Full Match · 1080 × 1350 preview",width=540)

else:
    if not players: st.warning("No player statistics were returned in this match's lineups payload."); st.stop()
    st.radio("Period",["Full Match","1st Half","2nd Half"],horizontal=True,key="leaders_period",disabled=True)
    st.caption("Half-specific Metric Leaders will re-rank from event-derived player actions; they are deliberately disabled until that data is available.")
    metrics=available_player_metrics(players)
    if not metrics: st.warning("No MatchLab leaderboard metrics are available in this match's lineup data."); st.stop()
    control_col,preview_col=st.columns([.9,2.1],gap="large")
    with control_col:
        st.subheader("Metric Leaders")
        scope_options={"All Players":("all","ALL PLAYERS"),f"Team A · {match.home_name}":("home",f"TEAM A · {match.home_name.upper()}"),f"Team B · {match.away_name}":("away",f"TEAM B · {match.away_name.upper()}")}
        scope_choice=st.selectbox("Players",list(scope_options.keys())); scope,scope_label=scope_options[scope_choice]
        metric_labels=[m["label"] for m in metrics]; metric_label=st.selectbox("Metric",metric_labels); metric=next(m for m in metrics if m["label"]==metric_label)
        leaders=build_metric_leader_rows(players,metric,scope=scope); png=render_metric_leaders(match,metric_label,scope_label,leaders)
        st.caption(f"{len(leaders)} players ranked · highest value first")
        st.download_button("Download Leaders PNG",data=png,file_name=f"{match.event_id}_{metric_label.lower().replace(' ','_').replace('-','_')}_leaders.png",mime="image/png",type="primary",width="stretch")
        with st.expander("View leaderboard data"): st.dataframe(leaders,width="stretch",hide_index=True)
    with preview_col: st.image(png,caption="Full Match · 1080 × 1350 preview",width=540)
