"""
app.py
------
Bradley Analytics Software Engine -- Streamlit front end.

A browser-based version of the original CLI workflow in
python/bradley_analytics.py: pick a player, season, season type, and
team color, then generate a shot chart / heat map straight from
nba_api. Runs entirely in Python so it works on Streamlit Community
Cloud (no R runtime required).
"""

from pathlib import Path

import matplotlib.pyplot as plt
import streamlit as st
from PIL import Image

from nba_data import build_season_list, find_player, get_player_info, get_shot_data
from teams import TEAMS, resolve_team_color
from theme import build_css
from visuals import VISUALIZATION_BUILDERS

_FAVICON_PATH = Path(__file__).resolve().parent / "assets" / "favicon.png"
GITHUB_REPO_URL = "https://github.com/alexbrxdley/Bradley-Analytics-Software-Engine"

st.set_page_config(
    page_title="Bradley Analytics",
    page_icon=Image.open(_FAVICON_PATH),
    layout="centered",
)

if "mode" not in st.session_state:
    st.session_state.mode = "Player"
if "view" not in st.session_state:
    st.session_state.view = "Dashboard"

st.markdown(build_css(st.session_state.mode, st.session_state.view), unsafe_allow_html=True)
plt.rcParams["savefig.transparent"] = True

TEAM_LABELS = sorted(TEAMS.keys())
SEASON_TYPES = ["Regular Season", "Playoffs"]


def render_header():
    st.markdown('<div class="bradley-title">BRADLEY ANALYTICS</div>', unsafe_allow_html=True)


def render_footer():
    st.markdown(
        '<div class="bradley-footer">'
        "Bradley Analytics Software Engine created by Alex Bradley | "
        f'<a href="{GITHUB_REPO_URL}" target="_blank">GitHub</a> | MIT Licensed'
        "</div>",
        unsafe_allow_html=True,
    )


def show_error(message: str):
    """Surface a real failure reason instead of a silent dead end."""
    st.error("Something went wrong talking to NBA.com.")
    with st.expander("Details"):
        st.write(message)


def render_toggle() -> str:
    """
    Custom Player/Team segmented control. Deliberately NOT st.radio --
    reskinning Streamlit's native radio with CSS wasn't reliable. This
    is two real buttons, styled via theme.build_css() based on
    st.session_state.mode.
    """
    col1, col2 = st.columns(2)

    with col1:
        with st.container(key="toggle-player"):
            if st.button("Player", key="btn-player", use_container_width=True):
                if st.session_state.mode != "Player":
                    st.session_state.mode = "Player"
                    st.rerun()

    with col2:
        with st.container(key="toggle-team"):
            if st.button("Team", key="btn-team", use_container_width=True):
                if st.session_state.mode != "Team":
                    st.session_state.mode = "Team"
                    st.rerun()

    return st.session_state.mode


def render_view_switch() -> str:
    """Custom Dashboard / Select visualization / Custom dashboard control."""
    options = ["Dashboard", "Select visualization", "Custom dashboard"]
    keys = ["view-dashboard", "view-select", "view-custom"]
    cols = st.columns(3)

    for col, name, key in zip(cols, options, keys):
        with col:
            with st.container(key=key):
                if st.button(name, key=f"btn-{key}", use_container_width=True):
                    if st.session_state.view != name:
                        st.session_state.view = name
                        st.rerun()

    return st.session_state.view


def main():
    render_header()

    mode = render_toggle()

    if mode == "Team":
        st.info(
            "Team visualizations aren't available yet in the software engine. "
            "Select **Player** to generate a shot chart or heat map."
        )
        render_footer()
        return

    player_name = st.text_input(
        "Player name", placeholder="Enter player name",
        label_visibility="collapsed",
    )

    if not player_name:
        render_footer()
        return

    player, error = find_player(player_name)

    if error:
        show_error(error)
        render_footer()
        return

    if player is None:
        st.warning("Player not found. Check the spelling and try again.")
        render_footer()
        return

    info, error = get_player_info(player["id"])

    if error:
        show_error(error)
        render_footer()
        return

    if info is None:
        st.error("Could not load season data for this player. Please try again.")
        render_footer()
        return

    st.caption(f"Player found: **{player['full_name']}**")

    seasons = build_season_list(info["first_year"], info["last_year"])
    default_team_index = (
        TEAM_LABELS.index(info["team_label"])
        if info["team_label"] in TEAM_LABELS
        else 0
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        with st.container(key="season-select"):
            season = st.selectbox("Season year", seasons)
    with col2:
        season_type = st.selectbox("Season type", SEASON_TYPES)
    with col3:
        team_label = st.selectbox("Team color", TEAM_LABELS, index=default_team_index)

    team_color = resolve_team_color(team_label)
    st.markdown(
        f'<span class="summary-pill">{team_label}'
        f'<span class="team-swatch" style="background-color:{team_color};"></span></span>',
        unsafe_allow_html=True,
    )

    run_clicked = st.button("\u25B6 RUN")

    request_key = (player["id"], season, season_type, team_color)

    if run_clicked:
        st.session_state["request_key"] = request_key
        with st.spinner("Downloading data..."):
            shots, shot_error = get_shot_data(player["id"], season, season_type)
        st.session_state["shots"] = shots
        st.session_state["shot_error"] = shot_error

    if st.session_state.get("request_key") != request_key:
        # Selections changed since the last run -- don't show stale results.
        render_footer()
        return

    shots = st.session_state.get("shots")
    shot_error = st.session_state.get("shot_error")

    if shot_error:
        show_error(shot_error)
        render_footer()
        return

    if shots is None:
        if run_clicked:
            st.warning(
                f"No shot data found for {player['full_name']} "
                f"during {season} ({season_type})."
            )
        render_footer()
        return

    st.divider()

    view = render_view_switch()

    if view == "Dashboard":
        st.caption("Generating dashboard visualization...")
        cols = st.columns(2)
        for col, (name, builder) in zip(cols, VISUALIZATION_BUILDERS.items()):
            with col:
                st.markdown(f"**{name}**")
                st.pyplot(builder(shots, team_color), use_container_width=True)

    elif view == "Select visualization":
        choice = st.selectbox("Visualization", list(VISUALIZATION_BUILDERS.keys()))
        st.caption(f"Generating {choice.lower()}...")
        fig = VISUALIZATION_BUILDERS[choice](shots, team_color)
        st.pyplot(fig, use_container_width=True)

    else:  # Custom dashboard
        chosen = st.multiselect(
            "Include in dashboard",
            list(VISUALIZATION_BUILDERS.keys()),
            default=list(VISUALIZATION_BUILDERS.keys()),
        )
        if not chosen:
            st.info("Select at least one visualization to include.")
        else:
            st.caption("Generating custom dashboard...")
            cols = st.columns(len(chosen))
            for col, name in zip(cols, chosen):
                with col:
                    st.markdown(f"**{name}**")
                    st.pyplot(
                        VISUALIZATION_BUILDERS[name](shots, team_color),
                        use_container_width=True,
                    )

    render_footer()


if __name__ == "__main__":
    main()
