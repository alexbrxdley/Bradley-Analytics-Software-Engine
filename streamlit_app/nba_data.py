"""
nba_data.py
-----------
Thin wrappers around nba_api for the Streamlit app: finding a player,
figuring out which seasons they were active, and pulling shot chart
data for a given season / season type. Mirrors the logic that used to
live in python/bradley_analytics.py and python/nba_data.py, but
returns data directly instead of writing CSVs to disk.
"""

import pandas as pd
import streamlit as st
from nba_api.stats.endpoints import commonplayerinfo, shotchartdetail
from nba_api.stats.static import players

from teams import ABBR_TO_LABEL


@st.cache_data(show_spinner=False, ttl=3600)
def find_player(name: str):
    """
    Look up a player by full (or partial) name.

    Returns the first match as a dict with at least "id" and
    "full_name", or None if nothing matched. Mirrors ERROR HANDLING #1
    in the original CLI: a network / NBA API failure is treated the
    same as "not found" here, and the caller decides what to show.
    """
    try:
        matches = players.find_players_by_full_name(name)
    except Exception:
        return None

    return matches[0] if matches else None


@st.cache_data(show_spinner=False, ttl=3600)
def get_player_info(player_id: int):
    """
    Fetch career span and current team for a player.

    Returns a dict: {"first_year", "last_year", "team_label"}, or None
    on failure (mirrors ERROR HANDLING #2 from the original CLI).
    """
    try:
        info = commonplayerinfo.CommonPlayerInfo(player_id=player_id)
        career = info.get_data_frames()[0]

        first_year = int(career["FROM_YEAR"][0])
        last_year = int(career["TO_YEAR"][0])
        team_abbr = career["TEAM_ABBREVIATION"][0]
    except Exception:
        return None

    return {
        "first_year": first_year,
        "last_year": last_year,
        "team_label": ABBR_TO_LABEL.get(team_abbr),
    }


def build_season_list(first_year: int, last_year: int):
    """Build ['2019-20', '2020-21', ...] style season strings, newest first."""
    seasons = [
        f"{year}-{str(year + 1)[2:]}"
        for year in range(first_year, last_year + 1)
    ]
    return list(reversed(seasons))


@st.cache_data(show_spinner=False, ttl=3600)
def get_shot_data(player_id: int, season: str, season_type: str):
    """
    Download shot chart data for a player/season/season-type.

    Returns a DataFrame of the player's shots, or None if the request
    failed or no shots were found (mirrors nba_data.py's behavior, but
    returns None instead of raising so the UI can show a clean message).
    """
    try:
        response = shotchartdetail.ShotChartDetail(
            team_id=0,
            player_id=player_id,
            season_nullable=season,
            season_type_all_star=season_type,
            context_measure_simple="FGA",
        )
        shots = response.get_data_frames()[0]
    except Exception:
        return None

    if shots.empty:
        return None

    shots["LOC_X"] = pd.to_numeric(shots["LOC_X"])
    shots["LOC_Y"] = pd.to_numeric(shots["LOC_Y"])

    return shots
