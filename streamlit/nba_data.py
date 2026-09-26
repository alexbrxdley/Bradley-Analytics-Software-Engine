"""
nba_data.py

Fetches live NBA data for the Streamlit dashboard. Mirrors the
fetching logic in python/nba_data.py from the main engine, adapted
to return data directly (rather than writing to CSV) since Streamlit
calls these functions interactively instead of running as a
one-shot script.

PROXY: stats.nba.com blocks datacenter IP ranges, which includes
Streamlit Community Cloud's servers. NBA_PROXY_URL (an environment
variable / Streamlit secret) is passed through to nba_api's
underlying requests call when present. Locally, with no proxy set,
calls go through directly and still work fine -- the proxy is only
required once this is actually deployed to the cloud.
"""

import threading
import os
import pandas as pd
import streamlit as st
from nba_api.stats.endpoints import (ShotChartDetail, commonplayerinfo, leaguedashplayerstats, leaguedashteamstats,
                                      leaguedashptdefend, leaguehustlestatsplayer, leaguedashplayerclutch,
                                      synergyplaytypes, playervsplayer, playergamelog, playerdashptpass,
                                      playercareerstats, teamgamelog, playerdashboardbygeneralsplits,
                                      teamdashboardbygeneralsplits, commonallplayers, playergamelogs, teamgamelogs)
from nba_api.stats.static import players, teams


def _install_request_retries():
    """
    Every nba_api call (stats and live) goes through one shared requests.Session per endpoint family. Through a proxy,
    an idle pooled connection the proxy has already closed makes the NEXT call fail instantly with
    "ProxyError('Unable to connect to proxy', RemoteDisconnected(...))" -- the error the Passing Web showed. So a call
    that fails on the connection itself (not a timeout, not a bad response) is retried up to twice on a FRESH
    connection, a moment apart.
    """
    import time
    import requests
    from nba_api.library import http as _nba_http

    base = _nba_http.NBAHTTP
    if getattr(base, "_ba_retry_installed", False):
        return
    original = base.send_api_request
    retryable = (requests.exceptions.ProxyError, requests.exceptions.ConnectionError,
                 requests.exceptions.ChunkedEncodingError)

    def send_api_request(self, *args, **kwargs):
        for attempt in range(3):
            try:
                return original(self, *args, **kwargs)
            except requests.exceptions.Timeout:
                raise
            except retryable:
                if attempt == 2:
                    raise
                cls = type(self)
                try:
                    if getattr(cls, "_session", None) is not None:
                        cls._session.close()
                except Exception:  # noqa: BLE001
                    pass
                cls._session = None               # next attempt opens a brand-new connection
                time.sleep(0.8 * (attempt + 1))

    base.send_api_request = send_api_request
    base._ba_retry_installed = True


_install_request_retries()


def _get_proxy():
    """
    Reads the proxy URL from a Streamlit secret first, falling back to
    a plain environment variable. Returns None if neither is set, in
    which case nba_api calls go through directly (fine for local
    development).

    Checking st.secrets is essential, not optional: a value configured
    through Streamlit Community Cloud's own Secrets manager UI (the
    normal way to set this in production) populates st.secrets, not
    os.environ -- an earlier version of this function only ever
    checked os.environ, meaning a correctly-configured NBA_PROXY_URL
    secret was silently never actually read at all. The try/except
    around st.secrets specifically (matching the same pattern already
    used for GROQ_API_KEY elsewhere in this app) is needed because
    st.secrets raises if no secrets.toml exists at all, which is the
    normal case for local development without any secrets configured.

    Returns a plain string, not a dict -- nba_api's own
    send_api_request() wraps this into the {"http":..., "https":...}
    format requests expects internally. Passing a dict here (as an
    earlier version of this function did) causes requests to try to
    parse the dict itself as a URL string and crash.
    """
    try:
        proxy_url = st.secrets.get("NBA_PROXY_URL", None)
    except Exception:
        proxy_url = None
    if not proxy_url:
        proxy_url = os.environ.get("NBA_PROXY_URL")
    if not proxy_url:
        return None
    return proxy_url


def _add_calculated_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds the three "calculated" stats stats_config.py offers everywhere
    (PPS = PTS/FGA, FT_RATE = FTA/FGA, FG3A_RATE = FG3A/FGA), matching
    python/axis_data.py. Nothing in the dashboard ever computed them, so
    picking any of them in a chart or the Stat Formula Creator failed
    ("couldn't find PPS") or was skipped. Each is a ratio of two counts,
    so it comes out identical in Totals, PerGame, and Per36 mode. Rows
    with zero FGA get NaN rather than inf.
    """
    out = df.copy()
    if "FGA" in out.columns:
        fga = out["FGA"].where(out["FGA"] > 0)
        if "PTS" in out.columns:
            out["PPS"] = out["PTS"] / fga
        if "FTA" in out.columns:
            out["FT_RATE"] = out["FTA"] / fga
        if "FG3A" in out.columns:
            out["FG3A_RATE"] = out["FG3A"] / fga
    # The NBA's advanced tables have used both spellings for
    # assist-to-turnover; the app's stat list uses AST_TOV.
    if "AST_TO" in out.columns and "AST_TOV" not in out.columns:
        out["AST_TOV"] = out["AST_TO"]
    return out


@st.cache_data(ttl=3600)
def get_player_shots(player_id: int, season: str) -> pd.DataFrame:
    """
    Fetches shot chart data for a single player/season. Mirrors the
    player-mode branch of nba_data.py's ShotChartDetail call exactly
    (team_id=0 means "any team", context_measure_simple="FGA").
    """
    response = ShotChartDetail(
        team_id=0,
        player_id=player_id,
        season_nullable=season,
        context_measure_simple="FGA",
        proxy=_get_proxy(),
    )
    return response.get_data_frames()[0]


@st.cache_data(ttl=3600)
def get_team_shots(team_id: int, season: str) -> pd.DataFrame:
    """
    Fetches shot chart data for every player on a team/season.
    Mirrors the team-mode branch of nba_data.py (player_id=0 means
    "every player on this team").
    """
    response = ShotChartDetail(
        team_id=team_id,
        player_id=0,
        season_nullable=season,
        context_measure_simple="FGA",
        proxy=_get_proxy(),
    )
    return response.get_data_frames()[0]


@st.cache_data(ttl=3600)
def get_league_shots(season: str) -> pd.DataFrame:
    """
    Fetches league-wide shot data for a season -- used by the hex
    shot chart to compare a player's FG% against the league average
    from the same court location, matching nba_data.py's
    Hex-Shot-Chart-only comparison_shots.csv logic.
    """
    response = ShotChartDetail(
        team_id=0,
        player_id=0,
        season_nullable=season,
        context_measure_simple="FGA",
        proxy=_get_proxy(),
    )
    return response.get_data_frames()[0]


@st.cache_data(ttl=3600)
def get_player_stats(season: str, per_mode: str = "Totals") -> pd.DataFrame:
    """
    Fetches per-player season stats, base AND advanced merged into one
    table -- the two measure types are separate API calls
    (measure_type_detailed_defense="Base" vs "Advanced"), and this
    function's own docstring already claimed both were included before
    now, when in fact only Base was ever actually being fetched. Any
    advanced stat (OFF_RATING, TS_PCT, USG_PCT, and the rest listed in
    stats_config.py's AXIS_GRAPH_STATS) would silently fail with
    "Couldn't find X in the returned stats" the moment anyone picked it
    -- confirmed as a real, pre-existing gap, not a hypothetical one,
    while building the Advanced Stats Dashboard, which needs these same
    fields for real.

    per_mode: "Totals" (default, matches every existing call site),
    "PerGame", or "Per36" -- the exact strings nba_api's PerModeDetailed
    expects. Percentage/rate stats (FG%, TS%, ratings) are unaffected
    by this regardless of value; only counting stats (PTS, REB, etc.)
    actually change.
    """
    base = leaguedashplayerstats.LeagueDashPlayerStats(
        season=season,
        measure_type_detailed_defense="Base",
        per_mode_detailed=per_mode,
        proxy=_get_proxy(),
    ).get_data_frames()[0]
    advanced = leaguedashplayerstats.LeagueDashPlayerStats(
        season=season,
        measure_type_detailed_defense="Advanced",
        per_mode_detailed=per_mode,
        proxy=_get_proxy(),
    ).get_data_frames()[0]
    # Columns present in both (PLAYER_NAME, TEAM_ABBREVIATION, GP, etc.)
    # would otherwise collide on merge -- keep Base's copy of those and
    # only bring in the columns from Advanced that are genuinely new.
    advanced_only_cols = ["PLAYER_ID"] + [c for c in advanced.columns if c not in base.columns]
    return _add_calculated_stats(base.merge(advanced[advanced_only_cols], on="PLAYER_ID", how="left"))


@st.cache_data(ttl=3600)
def get_team_stats(season: str, per_mode: str = "Totals") -> pd.DataFrame:
    """
    Team-level season stats, base AND advanced merged -- the team
    equivalent of get_player_stats(), added for the Advanced Stats
    Dashboard's team mode (offensive/defensive rating, pace, and the
    other team-level advanced fields aren't meaningful at all for an
    individual player, so this needed its own function rather than
    reusing the player one).

    per_mode: same "Totals"/"PerGame"/"Per36" convention as
    get_player_stats() -- see that function's docstring.
    """
    base = leaguedashteamstats.LeagueDashTeamStats(
        season=season,
        measure_type_detailed_defense="Base",
        per_mode_detailed=per_mode,
        proxy=_get_proxy(),
    ).get_data_frames()[0]
    advanced = leaguedashteamstats.LeagueDashTeamStats(
        season=season,
        measure_type_detailed_defense="Advanced",
        per_mode_detailed=per_mode,
        proxy=_get_proxy(),
    ).get_data_frames()[0]
    advanced_only_cols = ["TEAM_ID"] + [c for c in advanced.columns if c not in base.columns]
    return _add_calculated_stats(base.merge(advanced[advanced_only_cols], on="TEAM_ID", how="left"))


@st.cache_data(ttl=3600)
def get_player_bio_stats(season: str) -> pd.DataFrame:
    """
    Bulk bio data (position, height, weight, age, experience) for every
    active player in one call -- used by Search by Criteria for real,
    server-provided position and height filtering rather than an
    expensive per-player commonplayerinfo lookup for the whole league.
    Includes columns: PLAYER_ID, PLAYER_NAME, TEAM_ABBREVIATION,
    PLAYER_HEIGHT, PLAYER_HEIGHT_INCHES, PLAYER_WEIGHT, AGE, POSITION,
    among others.
    """
    from nba_api.stats.endpoints import leaguedashplayerbiostats
    response = leaguedashplayerbiostats.LeagueDashPlayerBioStats(
        season=season,
        proxy=_get_proxy(),
    )
    df = response.get_data_frames()[0]
    if "PLAYER_HEIGHT" in df.columns and "PLAYER_HEIGHT_INCHES" not in df.columns:
        def _height_to_inches(h):
            try:
                feet, inches = str(h).split("-")
                return int(feet) * 12 + int(inches)
            except Exception:
                return None
        df["PLAYER_HEIGHT_INCHES"] = df["PLAYER_HEIGHT"].apply(_height_to_inches)
    return df


def search_players(name_query: str):
    """
    Looks up a player by name from the NBA's static player list.
    This list ships with nba_api itself and requires no network
    call, so it works identically locally and on Streamlit Cloud
    with no proxy needed.
    """
    return players.find_players_by_full_name(name_query)


def search_players_prefix(prefix: str):
    """
    Real "any word starts with" search, ranked by relevance -- an
    exact last-name match (e.g. "jordan" -> Michael Jordan) ranks
    above a last-name-starts-with match, which ranks above a
    first-name match. Without this ranking, a common first name like
    "Jordan Adams" would bury an exact last-name match like
    "Michael Jordan" 20+ results down an alphabetical list, which is
    the opposite of what someone searching a surname wants to see
    first.
    """
    if not prefix:
        return []
    prefix = prefix.lower().strip()

    def rank(full_name):
        words = full_name.lower().split()
        last_name = words[-1] if words else ""
        first_name = words[0] if words else ""
        if last_name == prefix:
            return 0
        if last_name.startswith(prefix):
            return 1
        if first_name.startswith(prefix):
            return 2
        return 3

    matches = [
        p for p in players.get_players()
        if any(word.startswith(prefix) for word in p["full_name"].lower().split())
    ]
    matches.sort(key=lambda p: (rank(p["full_name"]), p["full_name"]))
    return matches


def search_teams(name_query: str):
    """
    Same as search_players, but for teams -- also fully static,
    no network call required.
    """
    return [
        t for t in teams.get_teams()
        if name_query.lower() in t["full_name"].lower()
    ]


def search_teams_prefix(prefix: str):
    """
    Real "any word starts with" search for the team color box,
    ranked by relevance the same way search_players_prefix is --
    a match on the team's nickname (last word, e.g. "Celtics" in
    "Boston Celtics") ranks above a match on the city name.
    """
    if not prefix:
        return []
    prefix = prefix.lower().strip()

    def rank(full_name):
        words = full_name.lower().split()
        nickname = words[-1] if words else ""
        if nickname == prefix:
            return 0
        if nickname.startswith(prefix):
            return 1
        return 2

    matches = [
        t for t in teams.get_teams()
        if any(word.startswith(prefix) for word in t["full_name"].lower().split())
    ]
    matches.sort(key=lambda t: (rank(t["full_name"]), t["full_name"]))
    return matches


@st.cache_data(ttl=3600, show_spinner=False)
def _common_player_info(player_id: int) -> pd.DataFrame:
    """CommonPlayerInfo's main table. Raises on failure, so a failed call is never cached (a cached None used to
    stick for an hour after one momentary proxy hiccup)."""
    return commonplayerinfo.CommonPlayerInfo(player_id=player_id, proxy=_get_proxy()).get_data_frames()[0]


def get_player_career_seasons(player_id: int):
    """
    The seasons a player actually has regular-season games in, most recent first -- so a Season dropdown opens on the
    latest season with real data for him: 2025-26 for a player who played this season, 2024-25 for one who missed all
    of 2025-26 (e.g. injured), and the new season as soon as he has played in it. Never a season that hasn't started
    (the NBA's own career span, CommonPlayerInfo's TO_YEAR, already lists next season for every active player in the
    summer -- that is what made the dropdowns open on 2026-27). Returns None on any failure so the caller can fall
    back gracefully instead of crashing.
    """
    import re as _re
    import stats_config
    current = stats_config.current_season()
    try:
        rows = _player_career_frames(player_id)["season_totals_regular_season"]
        gp = pd.to_numeric(rows["GP"], errors="coerce").fillna(0) if "GP" in rows.columns else pd.Series(1, index=rows.index)
        played = {str(sid) for sid in rows.loc[gp > 0, "SEASON_ID"]}
        seasons = sorted((sid for sid in played if _re.match(r"^\d{4}-\d{2}$", sid) and sid <= current), reverse=True)
        if seasons:
            return seasons
    except Exception:  # noqa: BLE001 -- fall back to the career span below
        pass
    try:
        career = _common_player_info(player_id)
        first_year = int(career["FROM_YEAR"][0])
        last_year = min(int(career["TO_YEAR"][0]), stats_config.current_season_start_year())
    except Exception:
        return None
    return [f"{y}-{str(y+1)[2:]}" for y in range(last_year, first_year - 1, -1)] or None


@st.cache_data(ttl=3600)
def get_player_stats_by_quarter(player_id: int, season: str) -> pd.DataFrame:
    """
    A player's stats broken down by which quarter of the game they
    were produced in -- PlayerDashboardByGeneralSplits has no single
    "by period" result set that returns all 4 quarters together (its
    documented result sets split by days rest, location, month, etc.,
    not period), so this makes 4 separate calls, one per quarter
    (period=1..4), each pulling that call's own "OverallPlayerDashboard"
    result set (which reflects only that quarter's games once period is
    set) and combining them into one dataframe indexed by quarter
    number.

    Couldn't verify the exact column names/behavior of the period
    filter against a live call in this environment -- returns an empty
    DataFrame on any failure (a missing/unexpected column, a request
    error) so the caller can detect and handle that gracefully rather
    than crash on data whose shape wasn't confirmed firsthand.
    """
    quarter_rows = []
    try:
        for period in (1, 2, 3, 4):
            resp = playerdashboardbygeneralsplits.PlayerDashboardByGeneralSplits(
                player_id=player_id, season=season, period=str(period),
                per_mode_detailed="PerGame", proxy=_get_proxy(),
            )
            normalized = resp.get_normalized_dict()
            overall_rows = normalized.get("OverallPlayerDashboard", [])
            if not overall_rows:
                continue
            row = dict(overall_rows[0])
            row["QUARTER"] = period
            quarter_rows.append(row)
    except Exception:
        return pd.DataFrame()

    return pd.DataFrame(quarter_rows)


@st.cache_data(ttl=3600, show_spinner=False)
def get_quarter_game_logs(mode: str, subject_id: int, season: str) -> dict:
    """
    {quarter (1-4): DataFrame of every game that season, oldest first, with GAME_DATE / MATCHUP / WL / PTS scored in
    THAT quarter only} -- the per-game trend inside the Clutch Impact Clock's hover. PlayerGameLogs / TeamGameLogs
    (the plural endpoints) take a Period filter, so this is 4 calls, not one box score per game. A quarter whose call
    fails is simply missing from the dict (the hover then shows the season numbers without the trend line).
    """
    out = {}
    for period in (1, 2, 3, 4):
        try:
            if mode == "team":
                df = teamgamelogs.TeamGameLogs(team_id_nullable=subject_id, season_nullable=season,
                                               period_nullable=str(period), proxy=_get_proxy()).get_data_frames()[0]
            else:
                df = playergamelogs.PlayerGameLogs(player_id_nullable=subject_id, season_nullable=season,
                                                   period_nullable=str(period), proxy=_get_proxy()).get_data_frames()[0]
        except Exception:
            continue
        if df is None or df.empty or "PTS" not in df.columns or "GAME_DATE" not in df.columns:
            continue
        df = df.copy()
        df["_d"] = pd.to_datetime(df["GAME_DATE"], errors="coerce")
        df = df.dropna(subset=["_d"]).sort_values("_d")
        keep = [c for c in ("GAME_DATE", "MATCHUP", "WL", "PTS") if c in df.columns]
        out[period] = df[keep].reset_index(drop=True)
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def get_period_game_log(mode: str, subject_id: int, season: str, period: int) -> pd.DataFrame:
    """
    Every game of the season with the box-score stats from ONE quarter only (period 1-4; 5 = first overtime) -- e.g.
    a player's 4th-quarter points game by game. PlayerGameLogs / TeamGameLogs with their Period filter, all columns
    kept (PTS, REB, AST, FGM/FGA, FG3M, PLUS_MINUS ...), oldest game first. Raises if it can't be loaded.
    """
    if mode == "team":
        df = teamgamelogs.TeamGameLogs(team_id_nullable=subject_id, season_nullable=season,
                                       period_nullable=str(int(period)), proxy=_get_proxy()).get_data_frames()[0]
    else:
        df = playergamelogs.PlayerGameLogs(player_id_nullable=subject_id, season_nullable=season,
                                           period_nullable=str(int(period)), proxy=_get_proxy()).get_data_frames()[0]
    if df is None or df.empty or "GAME_DATE" not in df.columns:
        return pd.DataFrame()
    df = df.copy()
    df["_d"] = pd.to_datetime(df["GAME_DATE"], errors="coerce")
    return df.dropna(subset=["_d"]).sort_values("_d").drop(columns=["_d"]).reset_index(drop=True)


@st.cache_data(ttl=3600, show_spinner=False)
def get_zone_league_averages(season: str, player_id: int = 0, team_id: int = 0) -> pd.DataFrame:
    """
    League-average FGA/FGM/FG% for every shot zone (SHOT_ZONE_BASIC x SHOT_ZONE_AREA) that season -- ShotChartDetail's
    own second result set ("LeagueAverages"), which comes back with ANY shot-chart call. Asking with the same
    player/team as the chart keeps it a small request, instead of downloading every shot in the league (which is what
    get_league_shots() does for the Hex Shot Chart's per-hex comparison). Empty DataFrame on failure.
    """
    try:
        frames = ShotChartDetail(team_id=team_id, player_id=player_id, season_nullable=season,
                                 context_measure_simple="FGA", proxy=_get_proxy()).get_data_frames()
        return frames[1] if len(frames) > 1 else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def get_team_stats_by_quarter(team_id: int, season: str) -> pd.DataFrame:
    """
    The team-level equivalent of get_player_stats_by_quarter() -- same
    reasoning applies: TeamDashboardByGeneralSplits has no single "by
    period" result set covering all 4 quarters together, so this makes
    4 separate calls (period=1..4) and combines them, indexed by
    quarter number. Same "return empty on any failure" contract, since
    this couldn't be verified against a live call in this environment
    either.
    """
    quarter_rows = []
    try:
        for period in (1, 2, 3, 4):
            resp = teamdashboardbygeneralsplits.TeamDashboardByGeneralSplits(
                team_id=team_id, season=season, period=str(period),
                per_mode_detailed="PerGame", proxy=_get_proxy(),
            )
            normalized = resp.get_normalized_dict()
            overall_rows = normalized.get("OverallTeamDashboard", [])
            if not overall_rows:
                continue
            row = dict(overall_rows[0])
            row["QUARTER"] = period
            quarter_rows.append(row)
    except Exception:
        return pd.DataFrame()

    return pd.DataFrame(quarter_rows)


def get_player_current_team(player_id: int):
    """
    A player's actual current team, via CommonPlayerInfo -- the
    fallback for get_player_team_for_season() when the requested
    season hasn't started (or is still in progress) yet, since
    PlayerCareerStats has no season-ending row to look up in either
    case. "The team he finished the season with" isn't a meaningful
    question for a season that hasn't happened yet -- "the team he's
    currently on" is the closest sensible answer instead. Returns None
    on any failure.
    """
    try:
        return _common_player_info(player_id)["TEAM_ABBREVIATION"][0]
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def _player_career_frames(player_id: int, per_mode: str = "Totals") -> dict:
    """PlayerCareerStats' tables by name (season-by-season and career rows, regular season and playoffs). Raises on
    failure, so a failed call is never cached."""
    career = playercareerstats.PlayerCareerStats(player_id=player_id, per_mode36=per_mode, proxy=_get_proxy())
    frames = {}
    for name in ("season_totals_regular_season", "career_totals_regular_season",
                 "season_totals_post_season", "career_totals_post_season"):
        ds = getattr(career, name, None)
        if ds is not None:
            try:
                frames[name] = ds.get_data_frame()
            except Exception:  # noqa: BLE001
                pass
    if "season_totals_regular_season" not in frames:
        frames["season_totals_regular_season"] = career.get_data_frames()[0]
    return frames


def get_player_career_stats(player_id: int, per_mode: str = "PerGame") -> dict:
    """A player's season-by-season and career stats (regular season + playoffs), per_mode "PerGame", "Totals" or
    "Per36". Raises on failure."""
    return _player_career_frames(player_id, per_mode)


def _season_rows_for(player_id, season):
    by_season = _player_career_frames(player_id)["season_totals_regular_season"]
    target_start_year = season[:4]
    season_rows = by_season[by_season["SEASON_ID"].astype(str).str.startswith(target_start_year)]
    return season_rows[season_rows["TEAM_ABBREVIATION"] != "TOT"]


def get_player_team_id_for_season(player_id: int, season: str):
    """
    The numeric team_id a player finished a given season with -- same
    season-matching logic as get_player_team_for_season(), but
    returning the raw TEAM_ID PlayerDashPtPass and similar endpoints
    actually require, rather than the human-readable abbreviation.
    Returns None on any failure or if the player didn't play that
    season at all.
    """
    try:
        season_rows = _season_rows_for(player_id, season)
        if season_rows.empty:
            return None
        return int(season_rows.iloc[-1]["TEAM_ID"])
    except Exception:
        return None


def get_player_team_for_season(player_id: int, season: str):
    """
    Which team a player finished a given season with -- used to
    default the color picker to that player's actual team rather than
    a generic default. PlayerCareerStats returns one row per team a
    player played for that season (plus a combined "TOT" row if they
    were traded mid-season), in chronological order -- the last
    non-"TOT" row is specifically their final team of that season,
    which is what "finished the season with" means for a
    since-traded player. Returns None on any failure or if the player
    didn't play that season at all, so the caller can fall back to a
    generic default instead of crashing.
    """
    try:
        season_rows = _season_rows_for(player_id, season)
        if season_rows.empty:
            return None
        return season_rows.iloc[-1]["TEAM_ABBREVIATION"]
    except Exception:
        return None


@st.cache_data(ttl=3600)
def get_team_roster(team_id: int, season: str) -> pd.DataFrame:
    """
    A team's actual roster for a given season -- used by Trade Machine
    to populate the "which players are actually on this team" pickers,
    rather than letting someone pick a player who was never on that
    roster at all. Includes PLAYER_ID, PLAYER (name), POSITION, HEIGHT,
    WEIGHT, and AGE.
    """
    from nba_api.stats.endpoints import commonteamroster
    response = commonteamroster.CommonTeamRoster(
        team_id=team_id,
        season=season,
        proxy=_get_proxy(),
    )
    return response.get_data_frames()[0]


@st.cache_data(ttl=3600)
def get_team_lineup_combos(team_id: int, season: str, group_quantity: int = 2, measure_type: str = "Base") -> pd.DataFrame:
    """
    Real stats for every specific N-player combination that shared the
    court together for this team this season (group_quantity=2 for
    pairs, 3 for trios) -- used by On/off Court Stats to find how a
    specific group of teammates actually performed together, which is
    a genuinely different, more specific question than a single
    player's overall on/off splits. GROUP_NAME identifies which players
    are in each row, typically as their names joined together.

    measure_type: "Base" (MIN/PTS/REB/AST/etc, the default) or
    "Advanced" (OFF_RATING/DEF_RATING/etc) -- two separate API calls
    under the hood, same as get_player_stats/get_team_stats.
    """
    from nba_api.stats.endpoints import teamdashlineups
    response = teamdashlineups.TeamDashLineups(
        team_id=team_id,
        season=season,
        group_quantity=group_quantity,
        measure_type_detailed_defense=measure_type,
        proxy=_get_proxy(),
    )
    # This endpoint returns multiple tables; the lineup-level detail
    # (one row per combination) is consistently the second one.
    frames = response.get_data_frames()
    return frames[1] if len(frames) > 1 else frames[0]


@st.cache_data(ttl=3600)
def get_league_lineup_combos(season: str, group_quantity: int = 3, measure_type: str = "Advanced") -> pd.DataFrame:
    """
    The league-wide equivalent of get_team_lineup_combos() -- every
    N-player combination that shared the floor together this season,
    across ALL teams in one call, so a specific lineup's own number
    can be ranked against every other lineup in the league rather than
    just the ones on its own team.
    """
    from nba_api.stats.endpoints import leaguedashlineups
    response = leaguedashlineups.LeagueDashLineups(
        season=season,
        group_quantity=group_quantity,
        measure_type_detailed_defense=measure_type,
        proxy=_get_proxy(),
    )
    frames = response.get_data_frames()
    return frames[1] if len(frames) > 1 else frames[0]


@st.cache_data(ttl=3600)
def get_player_defense_stats(season: str) -> pd.DataFrame:
    """
    Real, tracked shot-defense data (opponent FG% when this player is
    the closest defender, broken out by shot distance range) -- the
    closest genuinely-tracked equivalent to a "perimeter defense"
    stat, unlike NBA2K's ratings which are 2K's own subjective,
    proprietary game-design values rather than measured facts.
    """
    return leaguedashptdefend.LeagueDashPtDefend(
        season=season, defense_category="Overall", proxy=_get_proxy(),
    ).get_data_frames()[0]


@st.cache_data(ttl=3600)
def get_player_hustle_stats(season: str) -> pd.DataFrame:
    """
    Screen assists, deflections, loose balls recovered, charges drawn,
    and contested shots -- the "effort" stats that don't show up in a
    standard box score.
    """
    return leaguehustlestatsplayer.LeagueHustleStatsPlayer(
        season=season, proxy=_get_proxy(),
    ).get_data_frames()[0]


@st.cache_data(ttl=3600)
def get_player_clutch_stats(season: str) -> pd.DataFrame:
    """
    Performance specifically in clutch situations -- last 5 minutes of
    a game with the score within 5 points, the NBA's own standard
    definition of "clutch time".
    """
    return leaguedashplayerclutch.LeagueDashPlayerClutch(
        season=season, proxy=_get_proxy(),
    ).get_data_frames()[0]


@st.cache_data(ttl=86400, show_spinner=False)
def get_player_positions(season: str) -> pd.DataFrame:
    """Every player's listed position that season (PlayerIndex: PERSON_ID, POSITION such as "G", "F-C"). The bio-stats
    table has no position column, so this is where position filters get it from. Raises on failure."""
    from nba_api.stats.endpoints import playerindex
    df = playerindex.PlayerIndex(season=season, proxy=_get_proxy()).get_data_frames()[0]
    return df[["PERSON_ID", "POSITION"]].rename(columns={"PERSON_ID": "PLAYER_ID"})


@st.cache_data(ttl=3600, show_spinner=False)
def get_player_vs_player_onoff(player_id: int, vs_player_id: int, season: str) -> pd.DataFrame:
    """A player's stats with a specific opponent ON the court vs OFF it (PlayerVsPlayer's "OnOffCourt" table: one
    row per COURT_STATUS). Raises on failure."""
    response = playervsplayer.PlayerVsPlayer(
        player_id=player_id, vs_player_id=vs_player_id, season=season, proxy=_get_proxy(),
    )
    return response.on_off_court.get_data_frame()


@st.cache_data(ttl=3600)
def get_player_playtype_stats(season: str, play_type: str = "") -> pd.DataFrame:
    """
    Play-type efficiency (isolation, pick-and-roll ball handler,
    post-up, spot-up, transition, etc) at the player level. Leaving
    play_type blank returns all play types in one combined table.
    """
    return synergyplaytypes.SynergyPlayTypes(
        season=season, player_or_team_abbreviation="P",
        play_type_nullable=play_type, proxy=_get_proxy(),
    ).get_data_frames()[0]


@st.cache_data(ttl=3600)
def get_player_vs_player(player_id: int, vs_player_id: int, season: str) -> pd.DataFrame:
    """
    Head-to-head stats for one player specifically against another --
    e.g. how a player has performed in games against a specific
    defender/opponent this season.
    """
    return playervsplayer.PlayerVsPlayer(
        player_id=player_id, vs_player_id=vs_player_id, season=season, proxy=_get_proxy(),
    ).get_data_frames()[0]



@st.cache_data(ttl=3600)
def get_player_game_log(player_id: int, season: str) -> pd.DataFrame:
    """
    Every game a player played in a season, in order -- the data source
    for game-by-game trend charts (PTS/AST/REB by game, rolling
    averages, cumulative running totals), which a season-level snapshot
    like get_player_stats() can't provide since it only has one row per
    player per season, not one row per game.
    """
    return playergamelog.PlayerGameLog(
        player_id=player_id, season=season, proxy=_get_proxy(),
    ).get_data_frames()[0]


@st.cache_data(ttl=3600)
def get_team_game_log(team_id: int, season: str) -> pd.DataFrame:
    """
    Every game a team played in a season, in order -- the team-level
    equivalent of get_player_game_log(), needed to bring Combo Chart,
    Line/Trend Chart, and Calendar Heat Map to Search by Team, none of
    which had any team-level game-by-game data source available
    before this (get_team_stats() only has one row per team per
    season, the same one-row-per-season limitation
    get_player_game_log()'s docstring notes for players).
    """
    return teamgamelog.TeamGameLog(
        team_id=team_id, season=season, proxy=_get_proxy(),
    ).get_data_frames()[0]


@st.cache_data(ttl=3600)
def get_player_passes(player_id: int, season: str) -> pd.DataFrame:
    """
    Passer-to-receiver assist network data for one player -- who they
    passed to, how often, and how many of those passes became made
    shots. The real data source for a court "connection" map when true
    spatial pass-origin tracking (not available from this API) isn't
    an option: PASS_TO identifies the receiving teammate, FREQUENCY/
    PASS/AST/FGM/FGA quantify how much offense actually ran through
    that specific connection. PlayerDashPtPass requires a team_id
    (unlike some other endpoints, it has no team_id=0 "any team"
    wildcard), so this looks up the team the player actually played
    for DURING THE REQUESTED SEASON specifically -- confirmed as a
    real, not hypothetical, bug: using the player's current team
    instead (via a plain CommonPlayerInfo call, with no season
    awareness) silently returns empty data for any traded player
    queried on a season with a different team than their current one.
    """
    team_id = get_player_team_id_for_season(player_id, season)
    if team_id is None:
        # Falls back to the player's current team only if the
        # season-specific lookup itself fails for some reason, rather
        # than crashing outright -- still better than always using the
        # current team unconditionally, which was the confirmed bug.
        team_id = int(_common_player_info(player_id)["TEAM_ID"][0])

    response = playerdashptpass.PlayerDashPtPass(
        team_id=team_id, player_id=player_id, season=season, proxy=_get_proxy(),
    )
    return response.get_data_frames()[0]  # "PassesMade"


# ---------------------------------------------------------------- shots that came straight off one passer's passes
# The NBA's play-by-play names the passer on every ASSISTED basket, with the shot's court position -- the only public
# record that ties a specific pass to a specific shot location (a missed shot never names who passed). Used by the
# Passing Web to place each receiver where he actually shoots off this passer's passes.

_ASSISTED_COLUMNS = ["GAME_ID", "PLAYER_ID", "PERIOD", "CLOCK_SEC", "X_LEGACY", "Y_LEGACY", "SHOT_VALUE", "ACTION_NUMBER"]


def _clock_seconds(clock):
    """'PT10M53.00S' (live feed) or '10:53' -> seconds left in the period; None if unreadable."""
    import re
    s = str(clock or "")
    m = re.match(r"PT(\d+)M([\d.]+)S", s)
    if m:
        return int(m.group(1)) * 60 + float(m.group(2))
    m = re.match(r"(\d+):(\d+(?:\.\d+)?)", s)
    if m:
        return int(m.group(1)) * 60 + float(m.group(2))
    return None


def _assisted_row(action, game_id, shooter_id):
    def _num(v):
        try:
            return float(v) if v is not None and v != "" else None
        except (TypeError, ValueError):
            return None
    return {
        "GAME_ID": str(game_id), "PLAYER_ID": int(shooter_id), "PERIOD": int(action.get("period") or 0),
        "CLOCK_SEC": _clock_seconds(action.get("clock")), "X_LEGACY": _num(action.get("xLegacy")),
        "Y_LEGACY": _num(action.get("yLegacy")),
        "SHOT_VALUE": 3 if str(action.get("actionType", "")).lower().startswith("3")
                           or "3PT" in str(action.get("description", "")) else 2,
        "ACTION_NUMBER": action.get("actionNumber"),
    }


def _assisted_makes_live(actions, passer_id, game_id):
    """Made field goals whose assist is credited to passer_id, from the live-feed play-by-play."""
    rows = []
    for a in actions or []:
        if not a.get("isFieldGoal") or str(a.get("shotResult", "")).lower() != "made":
            continue
        try:
            if int(a.get("assistPersonId") or 0) != int(passer_id):
                continue
            shooter = int(a.get("personId") or 0)
        except (TypeError, ValueError):
            continue
        if shooter:
            rows.append(_assisted_row(a, game_id, shooter))
    return rows


def _assisted_makes_v3(actions, passer_last_name, game_id):
    """Same rows from stats.nba.com's PlayByPlayV3, which has no assist id: the assist is read from the description,
    e.g. '... (3 PTS) (J. Tatum 5 AST)'."""
    import re
    import unicodedata

    def _fold(s):
        return "".join(c for c in unicodedata.normalize("NFKD", str(s)) if not unicodedata.combining(c)).lower().strip()

    target = _fold(passer_last_name)
    rows = []
    for a in actions or []:
        if not a.get("isFieldGoal") or str(a.get("shotResult", "")).lower() != "made":
            continue
        m = re.search(r"\(([^()]*?)\s+\d+\s+AST\)", str(a.get("description", "")))
        if not m or not target or not _fold(m.group(1)).endswith(target):
            continue
        try:
            shooter = int(a.get("personId") or 0)
        except (TypeError, ValueError):
            continue
        if shooter:
            rows.append(_assisted_row(a, game_id, shooter))
    return rows


def _live_actions(game_id):
    """One game's live-feed play-by-play actions, straight from cdn.nba.com. Always a DIRECT call -- the CDN doesn't
    block cloud servers the way stats.nba.com does, and sending a whole season of these (tens of MB) through the
    stats proxy could use up its bandwidth and take every other chart down with it."""
    from nba_api.live.nba.endpoints import playbyplay
    data = playbyplay.PlayByPlay(game_id, proxy=False, timeout=12).get_dict()
    return (data.get("game") or {}).get("actions") or []


def _assisted_shots_uncached(passer_id, game_ids):
    from concurrent.futures import ThreadPoolExecutor

    def _one(gid):
        try:
            return gid, _assisted_makes_live(_live_actions(gid), passer_id, gid)
        except Exception:  # noqa: BLE001
            return gid, None

    game_ids = [str(g) for g in game_ids if g]
    if not game_ids:
        return pd.DataFrame(columns=_ASSISTED_COLUMNS)
    # A quick probe first: if the play-by-play feed can't be reached at all right now, don't fire a season's worth
    # of requests at it.
    first = _one(game_ids[0])
    if first[1] is None:
        second = _one(game_ids[-1])
        if second[1] is None:
            raise RuntimeError("NBA play-by-play feed unreachable")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = dict(pool.map(_one, game_ids))
    if sum(1 for r in results.values() if r is not None) < max(3, len(game_ids) // 3):
        raise RuntimeError("NBA play-by-play feed mostly unreachable")
    rows = [row for r in results.values() if r for row in r]
    return pd.DataFrame(rows, columns=_ASSISTED_COLUMNS)


@st.cache_data(ttl=86400, show_spinner=False)
def get_passer_assisted_shots_v3(passer_id: int, season: str, game_ids: tuple, passer_last_name: str) -> pd.DataFrame:
    """The same as get_passer_assisted_shots(), from stats.nba.com's PlayByPlayV3 through the stats proxy -- the
    fallback when the live feed (cdn.nba.com) can't be reached from the server. A handful of requests at a time, so the
    proxy isn't flooded; games that fail are skipped. Raises (nothing cached) if most games can't be read."""
    from concurrent.futures import ThreadPoolExecutor
    from nba_api.stats.endpoints import playbyplayv3

    proxy = _get_proxy()
    game_ids = [str(g) for g in game_ids if g]

    def _one(gid):
        try:
            df = playbyplayv3.PlayByPlayV3(game_id=gid, proxy=proxy, timeout=25).get_data_frames()[0]
            return gid, _assisted_makes_v3(df.to_dict("records"), passer_last_name, gid)
        except Exception:  # noqa: BLE001
            return gid, None

    if not game_ids:
        return pd.DataFrame(columns=_ASSISTED_COLUMNS)
    probe = _one(game_ids[0])
    if probe[1] is None:
        raise RuntimeError("NBA stats play-by-play unreachable")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = dict(pool.map(_one, game_ids[1:]))
    results[probe[0]] = probe[1]
    if sum(1 for r in results.values() if r is not None) < max(3, len(game_ids) // 2):
        raise RuntimeError("NBA stats play-by-play mostly unreachable")
    rows = [row for r in results.values() if r for row in r]
    return pd.DataFrame(rows, columns=_ASSISTED_COLUMNS)


@st.cache_data(ttl=86400, show_spinner=False)
def get_passer_assisted_shots(passer_id: int, season: str, game_ids: tuple, passer_last_name: str = "") -> pd.DataFrame:
    """
    Every made basket this passer assisted in the given games (the games he played), with the shooter and the shot's
    court position: one row per basket, columns _ASSISTED_COLUMNS. X_LEGACY/Y_LEGACY are the play-by-play's own shot
    coordinates (the same 1/10-foot grid ShotChartDetail uses); PERIOD + CLOCK_SEC let a caller match each basket to
    the shooter's own ShotChartDetail row. Raises (so nothing is cached) if the play-by-play can't be read.
    """
    return _assisted_shots_uncached(int(passer_id), tuple(game_ids))


# ---------------------------------------------------------------- pbpstats.com (public, no key, reachable from the cloud)
# pbpstats.com keeps a shot log built from the NBA's own play-by-play + shot charts: every shot with its court position
# (x, y in the same 1/10-foot grid, and sign, as ShotChartDetail's LOC_X / LOC_Y) and, on a made basket, who assisted it.
# One small request per receiver answers "where were the baskets this passer assisted to him shot?" -- no stats-site
# proxy, no season of play-by-play downloads.

PBPSTATS_API = "https://api.pbpstats.com"
_PBPSTATS_HEADERS = {"User-Agent": "Mozilla/5.0 (Bradley Analytics dashboard)", "Accept": "application/json"}
ASSISTED_XY_COLUMNS = ["GAME_ID", "PERIOD", "X", "Y", "SHOT_VALUE", "SHOT_TYPE"]
PBPSTATS_SHOT_TYPES = ("AtRim", "ShortMidRange", "LongMidRange", "Corner3", "Arc3")


# pbpstats.com only lets one address make a short burst of requests (about 6) and then roughly one every 4 seconds --
# anything faster is refused. Every pbpstats request this app makes (all visitors share one server) therefore waits
# its turn here instead of being refused: a burst of 5, then one every 4.5 seconds.
_PBP_BURST, _PBP_EVERY = 5.0, 4.5
_pbp_bucket = {"tokens": _PBP_BURST, "at": None}
_pbp_lock = threading.Lock()


def _pbpstats_wait_turn(max_wait=240.0):
    import time
    waited = 0.0
    while True:
        with _pbp_lock:
            now = time.monotonic()
            if _pbp_bucket["at"] is not None:
                _pbp_bucket["tokens"] = min(_PBP_BURST, _pbp_bucket["tokens"] + (now - _pbp_bucket["at"]) / _PBP_EVERY)
            _pbp_bucket["at"] = now
            if _pbp_bucket["tokens"] >= 1.0:
                _pbp_bucket["tokens"] -= 1.0
                return
            pause = (1.0 - _pbp_bucket["tokens"]) * _PBP_EVERY
        if waited >= max_wait:
            raise TimeoutError("pbpstats.com is busy -- too many requests queued")
        time.sleep(min(pause, 5.0))
        waited += min(pause, 5.0)


def _pbpstats_get(path, params, read_timeout=60):
    """GET one pbpstats endpoint as JSON, politely (see _pbpstats_wait_turn). A dropped connection, a timeout or a
    "too many requests" answer is retried a few times after a pause. Raises on failure."""
    import time
    import requests
    last = None
    for attempt in range(4):
        _pbpstats_wait_turn()
        try:
            r = requests.get(f"{PBPSTATS_API}/{path}", params=params, headers=_PBPSTATS_HEADERS,
                             timeout=(10, read_timeout))
            if r.status_code in (429, 503, 502, 520, 522, 524):
                try:
                    pause = float(r.headers.get("Retry-After") or 0)
                except ValueError:
                    pause = 0
                last = requests.exceptions.HTTPError(f"pbpstats.com answered {r.status_code}", response=r)
                with _pbp_lock:                           # everyone else waits too: the limit is for the whole server
                    _pbp_bucket["tokens"] = min(_pbp_bucket["tokens"], 0.0)
                time.sleep(max(pause, _PBP_EVERY + 1.0))
                continue
            r.raise_for_status()
            return r.json()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
                requests.exceptions.ChunkedEncodingError) as e:
            last = e
            time.sleep(1.5 + attempt)
    raise last


def _assisted_xy_uncached(receiver_id, passer_id, season, season_type):
    data = _pbpstats_get("get-shots/nba", {
        "Season": season, "SeasonType": season_type, "EntityType": "Player", "EntityId": str(int(receiver_id)),
        "AssistPlayerId": str(int(passer_id)),
    }, read_timeout=75)
    rows = []
    for r in (data or {}).get("results") or []:
        if not r.get("made"):
            continue
        try:
            if r.get("assist_player_id") is not None and int(r["assist_player_id"]) != int(passer_id):
                continue
            x, y = float(r["x"]), float(r["y"])
        except (KeyError, TypeError, ValueError):
            continue
        shot_type = str(r.get("shot_type") or "")
        try:
            value = int(r.get("shot_value") or 0)
        except (TypeError, ValueError):
            value = 0
        if value not in (2, 3):
            value = 3 if shot_type.endswith("3") else 2
        rows.append({"GAME_ID": str(r.get("gid") or ""), "PERIOD": r.get("period"), "X": x, "Y": y,
                     "SHOT_VALUE": value, "SHOT_TYPE": shot_type})
    return pd.DataFrame(rows, columns=ASSISTED_XY_COLUMNS)


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def get_assisted_shots_between(receiver_id: int, passer_id: int, season: str,
                               season_type: str = "Regular Season") -> pd.DataFrame:
    """Every basket passer_id assisted to receiver_id in the season: one row per made basket, columns
    ASSISTED_XY_COLUMNS, X/Y in shot-chart coordinates. Raises (nothing cached) if pbpstats.com can't be read."""
    return _assisted_xy_uncached(receiver_id, passer_id, season, season_type)


def get_assisted_shots_for_receivers(passer_id: int, receiver_ids: tuple, season: str,
                                     season_type: str = "Regular Season") -> dict:
    """
    {receiver_id: DataFrame (see get_assisted_shots_between) or None if that receiver couldn't be read}, fetched in
    parallel. Each receiver is cached on its own, so one failed request never leaves a half-empty answer cached.
    """
    from concurrent.futures import ThreadPoolExecutor
    try:
        from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
        ctx = get_script_run_ctx()
    except Exception:  # noqa: BLE001
        add_script_run_ctx, ctx = None, None

    def _one(rid):
        if add_script_run_ctx and ctx is not None:
            import threading
            add_script_run_ctx(threading.current_thread(), ctx)
        try:
            return int(rid), get_assisted_shots_between(int(rid), int(passer_id), season, season_type)
        except Exception:  # noqa: BLE001
            return int(rid), None

    ids = [int(r) for r in receiver_ids if r]
    if not ids:
        return {}
    # pbpstats.com answers slowly when hit with many requests at once, so only a few go out together
    with ThreadPoolExecutor(max_workers=min(3, len(ids))) as pool:
        return dict(pool.map(_one, ids))


def _assist_network_uncached(team_id, season, season_type):
    data = _pbpstats_get("get-assist-networks/nba", {
        "Season": season, "SeasonType": season_type, "EntityType": "Team", "EntityId": str(int(team_id))},
        read_timeout=45)
    res = (data or {}).get("results") or {}
    names = {str(n.get("id")): n.get("name") for n in res.get("nodes") or []}
    rows = []
    for link in res.get("links") or []:
        row = {"TEAM_ID": int(team_id), "PASSER_ID": int(link.get("source") or 0), "RECEIVER_ID": int(link.get("target") or 0),
               "PASSER": names.get(str(link.get("source")), ""), "RECEIVER": names.get(str(link.get("target")), ""),
               "AST": int(link.get("value") or 0), "AST_PTS": int(link.get("AssistPts") or 0)}
        for t in PBPSTATS_SHOT_TYPES:
            row[t] = int(link.get(t) or 0)
        rows.append(row)
    return pd.DataFrame(rows, columns=["TEAM_ID", "PASSER_ID", "RECEIVER_ID", "PASSER", "RECEIVER", "AST", "AST_PTS",
                                       *PBPSTATS_SHOT_TYPES])


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def get_team_assist_network(team_id: int, season: str, season_type: str = "Regular Season") -> pd.DataFrame:
    """Every passer -> receiver pair on one team: assisted baskets (AST), assist points, and those baskets by shot type
    (AtRim / ShortMidRange / LongMidRange / Corner3 / Arc3). From pbpstats.com's assist network."""
    return _assist_network_uncached(team_id, season, season_type)


def _num0(v):
    try:
        f = float(v)
        return 0.0 if f != f else f
    except (TypeError, ValueError):
        return 0.0


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def get_league_passing_totals(season: str, season_type: str = "Regular Season") -> pd.DataFrame:
    """
    Every player's assist numbers by kind of shot, league-wide, in ONE pbpstats.com request (its season totals: the
    500 players with the most minutes -- everyone else played under ~100 minutes). One row per player:
      AST                 his assists (all shots)
      <type>_AST          baskets he assisted, by shot type (AtRim / ShortMidRange / LongMidRange / Corner3 / Arc3)
      <type>_ASTD         his own made baskets of that type that were assisted
      <type>_FGM / _FGA   his own shooting there
    Raises if pbpstats can't be read (nothing is cached then).
    """
    data = _pbpstats_get("get-totals/nba", {"Season": season, "SeasonType": season_type, "Type": "Player"},
                         read_timeout=90)
    rows = []
    for r in (data or {}).get("multi_row_table_data") or []:
        try:
            pid = int(r.get("EntityId"))
        except (TypeError, ValueError):
            continue
        rec = {"PLAYER_ID": pid, "NAME": r.get("Name") or "", "TEAM_ID": int(_num0(r.get("TeamId"))),
               "TEAM": r.get("TeamAbbreviation") or "", "AST": _num0(r.get("Assists"))}
        for t in PBPSTATS_SHOT_TYPES:
            fgm = _num0(r.get(f"{t}FGM"))
            rec[f"{t}_AST"] = _num0(r.get(f"{t}Assists"))
            rec[f"{t}_FGM"], rec[f"{t}_FGA"] = fgm, _num0(r.get(f"{t}FGA"))
            rec[f"{t}_ASTD"] = float(round(fgm * _num0(r.get(f"{t}PctAssisted"))))
        rows.append(rec)
    if not rows:
        raise RuntimeError("pbpstats.com returned no player totals")
    return pd.DataFrame(rows)


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def get_league_assist_networks(season: str, season_type: str = "Regular Season") -> pd.DataFrame:
    """get_team_assist_network() for all 30 teams, stacked (a traded player appears once per team). A few teams are
    fetched at a time. Raises (nothing cached) if more than a few teams can't be read."""
    from concurrent.futures import ThreadPoolExecutor

    def _one(tid):
        try:
            return _assist_network_uncached(tid, season, season_type)
        except Exception:  # noqa: BLE001
            return None

    team_ids = [t["id"] for t in teams.get_teams()]
    with ThreadPoolExecutor(max_workers=3) as pool:
        frames = list(pool.map(_one, team_ids))
    good = [f for f in frames if f is not None]
    if len(good) < len(team_ids) - 3:
        raise RuntimeError("pbpstats.com assist networks unreachable")
    return pd.concat(good, ignore_index=True) if good else pd.DataFrame()


@st.cache_data(ttl=86400, show_spinner=False)
def get_player_spans() -> dict:
    """
    {player_id: (first season's start year, last season's start year)} for every player in NBA history, from ONE
    CommonAllPlayers call. Used to keep a picker's player list to people who have data for the chosen visualization/season.
    Returns {} if the call fails (nobody is hidden on a guess).
    """
    try:
        df = commonallplayers.CommonAllPlayers(is_only_current_season=0, league_id="00", proxy=_get_proxy()).get_data_frames()[0]
        out = {}
        for pid, a, b in zip(df["PERSON_ID"], df["FROM_YEAR"], df["TO_YEAR"]):
            try:
                out[int(pid)] = (int(a), int(b))
            except (TypeError, ValueError):
                continue
        return out
    except Exception:
        return {}


@st.cache_data(ttl=3600)
def get_game_context_lookup(mode: str, subject_id: int, season: str) -> dict:
    """
    Real per-game context (win/loss, final score both sides, opponent)
    for every game in `season`, keyed by a normalized "YYYY-MM-DD" date
    string built with pd.to_datetime() rather than assumed to already
    match -- ShotChartDetail, PlayerGameLog, and TeamGameLog are three
    separate endpoints and their raw GAME_DATE string formats aren't
    pinned down against a live call in this environment, so this joins
    on the parsed calendar date instead of hoping the raw strings are
    identical.

    Team mode reads straight off get_team_game_log(): PTS is the
    team's own score, and PLUS_MINUS on a TEAM row is that game's real
    point margin, so PTS - PLUS_MINUS gives the opponent's score.

    Player mode needs the player's own TEAM's game log for a real
    final score, since PLUS_MINUS on a PLAYER row is that player's own
    on-court margin, not the game's -- get_player_team_id_for_season()
    finds that team, and get_team_game_log() gives its scores, joined
    by date to the player's own game log (which supplies WL/opponent
    directly, and is what decides which dates exist at all). If the
    team lookup fails, games still get their real WL/opponent, just
    without a score line, rather than a guessed one.

    Returns {} if the player/team has no game log for this season
    (falls back gracefully wherever it's used, same as this file's
    other lookups).
    """
    def _iso(date_val):
        try:
            return pd.to_datetime(date_val).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            return None

    out = {}
    if mode == "team":
        log = get_team_game_log(subject_id, season)
        if log.empty:
            return out
        for _, row in log.iterrows():
            date_key = _iso(row.get("GAME_DATE"))
            if not date_key:
                continue
            try:
                team_pts = float(row["PTS"])
                opp_pts = team_pts - float(row["PLUS_MINUS"])
                opponent = str(row["MATCHUP"]).split(" ")[-1]
                out[date_key] = {
                    "win": row["WL"] == "W", "team_pts": team_pts,
                    "opp_pts": opp_pts, "opponent": opponent,
                }
            except (KeyError, ValueError, TypeError):
                continue
        return out

    # player mode
    player_log = get_player_game_log(subject_id, season)
    if player_log.empty:
        return out

    team_by_date = {}
    try:
        team_id = get_player_team_id_for_season(subject_id, season)
        team_log = get_team_game_log(team_id, season) if team_id else pd.DataFrame()
        for _, row in team_log.iterrows():
            date_key = _iso(row.get("GAME_DATE"))
            if not date_key:
                continue
            try:
                team_pts = float(row["PTS"])
                team_by_date[date_key] = (team_pts, team_pts - float(row["PLUS_MINUS"]))
            except (KeyError, ValueError, TypeError):
                continue
    except Exception:
        pass  # score/opponent context is a bonus -- WL below still works without it

    for _, row in player_log.iterrows():
        date_key = _iso(row.get("GAME_DATE"))
        if not date_key:
            continue
        try:
            opponent = str(row["MATCHUP"]).split(" ")[-1]
            team_pts, opp_pts = team_by_date.get(date_key, (None, None))
            out[date_key] = {
                "win": row["WL"] == "W", "team_pts": team_pts,
                "opp_pts": opp_pts, "opponent": opponent,
            }
        except (KeyError, ValueError, TypeError):
            continue
    return out


def game_context_date_key(date_val):
    """Same normalization get_game_context_lookup() keys itself with --
    callers building hotspots for GAME_DATE values from a DIFFERENT
    dataframe (e.g. ShotChartDetail's shots_df) use this to look up the
    same game, since a raw string equality check can't be trusted to
    match across endpoints whose date formats aren't confirmed identical."""
    try:
        return pd.to_datetime(date_val).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None
