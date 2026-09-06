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

import os
import pandas as pd
import streamlit as st
from nba_api.stats.endpoints import (ShotChartDetail, commonplayerinfo, leaguedashplayerstats, leaguedashteamstats,
                                      leaguedashptdefend, leaguehustlestatsplayer, leaguedashplayerclutch,
                                      synergyplaytypes, playervsplayer, playergamelog, playerdashptpass,
                                      playercareerstats)
from nba_api.stats.static import players, teams


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
    return base.merge(advanced[advanced_only_cols], on="PLAYER_ID", how="left")


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
    return base.merge(advanced[advanced_only_cols], on="TEAM_ID", how="left")


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


@st.cache_data(ttl=3600)
def get_player_career_seasons(player_id: int):
    """
    Real per-player career-span lookup, matching
    _select_player_and_season()'s exact approach in the main engine:
    a single CommonPlayerInfo call returns the player's actual
    FROM_YEAR/TO_YEAR, which this expands into a full list of real
    season strings (most recent first). Returns None on any failure
    so the caller can fall back gracefully instead of crashing.
    """
    try:
        info = commonplayerinfo.CommonPlayerInfo(player_id=player_id, proxy=_get_proxy())
        career = info.get_data_frames()[0]
        first_year = int(career["FROM_YEAR"][0])
        last_year = int(career["TO_YEAR"][0])
    except Exception:
        return None

    return [f"{y}-{str(y+1)[2:]}" for y in range(last_year, first_year - 1, -1)]


@st.cache_data(ttl=3600)
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
        career = playercareerstats.PlayerCareerStats(player_id=player_id, proxy=_get_proxy())
        by_season = career.get_data_frames()[0]
        # Matches on the starting year number rather than requiring an
        # exact SEASON_ID string match -- robust to any minor format
        # difference between this endpoint's own SEASON_ID and this
        # app's "YYYY-YY" convention, which couldn't be verified
        # against a live call in this environment.
        target_start_year = season[:4]
        season_rows = by_season[by_season["SEASON_ID"].astype(str).str.startswith(target_start_year)]
        season_rows = season_rows[season_rows["TEAM_ABBREVIATION"] != "TOT"]
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
    wildcard), so this first looks the player's current team up via
    CommonPlayerInfo.
    """
    info = commonplayerinfo.CommonPlayerInfo(player_id=player_id, proxy=_get_proxy())
    player_info_df = info.get_data_frames()[0]
    team_id = int(player_info_df["TEAM_ID"][0])

    response = playerdashptpass.PlayerDashPtPass(
        team_id=team_id, player_id=player_id, season=season, proxy=_get_proxy(),
    )
    return response.get_data_frames()[0]  # "PassesMade"
