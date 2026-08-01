"""
nba_data.py
-----------
Thin wrappers around nba_api for the Streamlit app: finding a player,
figuring out which seasons they were active, and pulling shot chart
data for a given season / season type.

NBA.com's stats API silently rejects requests that don't look like
they're coming from a real browser (no error, just an empty/failed
response), which is the most common reason "seasons never load" when
this kind of app runs on a cloud host. To fix that, every request
below goes out with real browser-style headers and a generous timeout,
and failures are returned as (None, error_message) instead of being
swallowed, so the UI can show *why* a lookup failed instead of just
"not found."
"""

import pandas as pd
import streamlit as st
from nba_api.stats.endpoints import commonplayerinfo, shotchartdetail
from nba_api.stats.library.http import NBAStatsHTTP
from nba_api.stats.static import players

from teams import ABBR_TO_LABEL

# NBA.com's stats endpoints block requests that don't look like a real
# browser hitting stats.nba.com directly. This mirrors what a browser
# actually sends and fixes the "request just hangs / silently fails"
# issue that shows up when this runs on a cloud host.
_BROWSER_HEADERS = {
    "Host": "stats.nba.com",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
    "Connection": "keep-alive",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
}
NBAStatsHTTP.headers = _BROWSER_HEADERS

_TIMEOUT = 60


@st.cache_data(show_spinner=False, ttl=3600)
def find_player(name: str):
    """
    Look up a player by full (or partial) name.

    Returns (player_dict, error). player_dict has at least "id" and
    "full_name"; it's None if nothing matched or the lookup failed,
    in which case error holds a human-readable reason.
    """
    try:
        matches = players.find_players_by_full_name(name)
    except Exception as exc:
        return None, f"Player lookup failed: {exc}"

    if not matches:
        return None, None  # no error, just genuinely not found

    return matches[0], None


@st.cache_data(show_spinner=False, ttl=3600)
def get_player_info(player_id: int):
    """
    Fetch career span and current team for a player.

    Returns (info_dict, error). info_dict is
    {"first_year", "last_year", "team_label"}, or None on failure.
    """
    try:
        info = commonplayerinfo.CommonPlayerInfo(
            player_id=player_id, timeout=_TIMEOUT
        )
        career = info.get_data_frames()[0]

        if career.empty:
            return None, "NBA.com returned no career data for this player."

        first_year = int(career["FROM_YEAR"][0])
        last_year = int(career["TO_YEAR"][0])
        team_abbr = career["TEAM_ABBREVIATION"][0]
    except Exception as exc:
        return None, (
            "Could not load season data from NBA.com "
            f"(this is usually a network/timeout issue, not a bug): {exc}"
        )

    return {
        "first_year": first_year,
        "last_year": last_year,
        "team_label": ABBR_TO_LABEL.get(team_abbr),
    }, None


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

    Returns (DataFrame, error). DataFrame is None if the request
    failed or no shots were found, with error explaining why.
    """
    try:
        response = shotchartdetail.ShotChartDetail(
            team_id=0,
            player_id=player_id,
            season_nullable=season,
            season_type_all_star=season_type,
            context_measure_simple="FGA",
            timeout=_TIMEOUT,
        )
        shots = response.get_data_frames()[0]
    except Exception as exc:
        return None, f"Could not download shot data from NBA.com: {exc}"

    if shots.empty:
        return None, None  # no error, just no shots for this selection

    shots["LOC_X"] = pd.to_numeric(shots["LOC_X"])
    shots["LOC_Y"] = pd.to_numeric(shots["LOC_Y"])

    return shots, None
