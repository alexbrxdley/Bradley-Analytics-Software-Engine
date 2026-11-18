"""
stats_config.py

Stat categories, display names, and visualization groupings,
extracted programmatically from python/bradley_analytics.py to
guarantee an exact match with the main engine rather than a
manually retyped copy.
"""

COURT_GRAPHS = ['Shot Chart', 'Heat Map', 'Hex Shot Chart']

# Every season this app's data sources can meaningfully cover:
# 1996-97 is when the NBA's shot-location tracking (the foundation for
# every court-based visualization here) begins. From July 1 (the new
# league year) the list starts at the upcoming season, so 2026-27 is
# there to pick all off-season; every dropdown still STARTS on the most
# recent season that has actually had games (default_season(): 2025-26
# until the 2026-27 regular season tips off, then 2026-27), with nothing
# to update by hand. Descending (most recent first).
import datetime as _dt


def _season_opener(year):
    """The NBA regular season opens on the Tuesday falling between October 18 and 24 (2021: Oct 19, 2022: Oct 18,
    2023: Oct 24, 2024: Oct 22, 2025: Oct 21)."""
    d = _dt.date(year, 10, 18)
    return d + _dt.timedelta(days=(1 - d.weekday()) % 7)


def _today_eastern():
    try:
        from zoneinfo import ZoneInfo
        return _dt.datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:  # noqa: BLE001
        return _dt.date.today()


def current_season_start_year(today=None):
    """The start year of the most recent season with games played: this year's season counts from the day after its
    opening night (so there's a full night of games in the data)."""
    today = today or _today_eastern()
    return today.year if today > _season_opener(today.year) else today.year - 1


def current_season(today=None):
    y = current_season_start_year(today)
    return f"{y}-{str(y + 1)[-2:]}"


def upcoming_season_start_year(today=None):
    """The newest season any dropdown offers: from July 1 (the new league year -- free agency, the Bradley Ratings
    and Tendencies, new rosters) the next season is listed, even before it has had a game."""
    today = today or _today_eastern()
    return today.year if today.month >= 7 else today.year - 1


def default_season(today=None):
    """The season a dropdown starts on: the most recent one with games (2025-26 until the 2026-27 opener, then
    2026-27), even while the upcoming season is already listed above it."""
    return current_season(today)


def default_season_index(options, today=None):
    """Where default_season() sits in a list of seasons (0 if it isn't there)."""
    d = default_season(today)
    try:
        return list(options).index(d)
    except ValueError:
        return 0


def _season_list(today=None):
    top = max(current_season_start_year(today), upcoming_season_start_year(today))
    return [f"{y}-{str(y + 1)[-2:]}" for y in range(top, 1995, -1)]


ALL_SEASONS = _season_list()


def refresh_seasons():
    """Re-checks the date (app.py calls this every run), updating ALL_SEASONS IN PLACE so every module that imported
    it sees the new season the day it starts, even on a server that has been running for weeks."""
    fresh = _season_list()
    if fresh != ALL_SEASONS:
        ALL_SEASONS[:] = fresh
AXIS_GRAPHS = ['Bar Chart', 'Scatter Plot', 'Histogram', 'Dot Plot', 'Density Plot', 'Cumulative Distribution Plot']
ANIMATED_GRAPHS = ['Animated Shot Chart']
GAME_LOG_GRAPHS = ['Line / Trend Chart', 'Momentum Chart']
COMPARISON_GRAPHS = ['Slope Chart', 'Waterfall Chart', 'Combo Chart', 'Tornado Chart', 'Radar Chart', 'Calendar Heat Map', 'Shot Flow (Sankey)', 'Impact Clock', 'Passing Connections']
ALL_VISUALIZATIONS = ['Shot Chart', 'Heat Map', 'Hex Shot Chart', 'Bar Chart', 'Scatter Plot', 'Animated Shot Chart']

# The top-level categories the visualization picker is organized
# into. Dot Plot and Density Plot are deliberately absent here -- they
# became display-mode toggles within Bar Chart and Histogram
# respectively rather than separate entries, and Momentum Chart became
# a mode within Line / Trend Chart, so none of the three appear as
# their own selectable visualization anymore.
VIZ_CATEGORY_COURT = ['Shot Chart', 'Heat Map', 'Hex Shot Chart', 'Passing Connections', 'Animated Shot Chart']
# Ordered per explicit request: Line/Trend Chart, Radar Chart, Impact
# Clock, Combo Chart, Waterfall Chart, then everything else left in
# the order it was already in. Passing Connections moved to Court /
# Geographical (under Hex Shot Chart).
VIZ_CATEGORY_ADVANCED = ['Line / Trend Chart', 'Radar Chart', 'Impact Clock', 'Combo Chart', 'Waterfall Chart',
                          'Tornado Chart', 'Calendar Heat Map',
                          'Shot Flow (Sankey)']
# Charts that compare every player/team in the league (leaderboards and distributions). The old "Player Comparison" /
# "Team Comparison" heading and its three charts (Head-to-Head, Shot Chart Comparison, Multi-Season Bump Chart) are gone
# from Search by Player / Search by Team, as is the "Lineup Network" shortcut beside them.
VIZ_CATEGORY_LEAGUE_COMPARISON = ['Bar Chart', 'Scatter Plot', 'Slope Chart', 'Histogram', 'Box Plot', 'Cumulative Distribution Plot']
VIZ_CATEGORIES = {
    "Court": VIZ_CATEGORY_COURT,
    "Advanced": VIZ_CATEGORY_ADVANCED,
    "League Comparison": VIZ_CATEGORY_LEAGUE_COMPARISON,
}

STAT_DISPLAY_NAMES = {'FGA': 'FGA', 'FGM': 'FGM', 'FG_PCT': 'FG%', 'FG3A': '3PA', 'FG3M': '3PM', 'FG3_PCT': '3P%', 'FTA': 'FTA', 'FTM': 'FTM', 'FT_PCT': 'FT%', 'PTS': 'points', 'PPS': 'points per shot', 'FT_RATE': 'FT rate', 'FG3A_RATE': '3PA rate', 'REB': 'rebounds', 'OREB': 'off rebounds', 'DREB': 'def rebounds', 'AST': 'assists', 'TOV': 'turnovers', 'STL': 'steals', 'BLK': 'blocks', 'BLKA': 'blocked attempts', 'PF': 'personal fouls', 'PFD': 'personal fouls drawn', 'MIN': 'minutes', 'PLUS_MINUS': '+/-', 'GP': 'games played', 'DD2': 'double doubles', 'TD3': 'triple doubles', 'AGE': 'age', 'W': 'wins', 'L': 'losses', 'W_PCT': 'win %', 'OFF_RATING': 'off rating', 'DEF_RATING': 'def rating', 'NET_RATING': 'net rating', 'TS_PCT': 'TS%', 'EFG_PCT': 'EFG%', 'USG_PCT': 'USG%', 'PACE': 'pace', 'PIE': 'PIE', 'AST_PCT': 'AST%', 'AST_TOV': 'AST/TO ratio', 'AST_RATIO': 'assist ratio', 'OREB_PCT': 'OREB%', 'DREB_PCT': 'DREB%', 'REB_PCT': 'REB%', 'TM_TOV_PCT': 'team TOV%', 'PLAYER_HEIGHT_INCHES': 'height (inches)', 'PLAYER_WEIGHT': 'weight (lbs)', 'DRAFT_YEAR': 'draft year', 'DRAFT_ROUND': 'draft round', 'DRAFT_NUMBER': 'draft pick', 'BRADLEY_3PT_RATING': 'Bradley 3 Rating'}

BRADLEY_RATING_DESCRIPTIONS = {'BRADLEY_3PT_RATING': "Blends 3P% (70%) and 3PA volume (30%), each ranked against that season's league. Combines the current season with the 2 before it (weighted ~70/20/10) - an old below-average season counts for less the further it falls below your recent form, on a sliding scale, not a hard cutoff. Being strong 3-4 years back too adds a small bonus that also scales smoothly with how strong. Needs 30+ total 3-point attempts this season to qualify."}

# Each entry: (field, label, source, {modes})
# source is one of: base, advanced, bio, calculated, bradley_rating,
# defense_tracking, hustle, clutch
AXIS_GRAPH_STATS = [('Bradley Analytics Invented Stats', [('BRADLEY_3PT_RATING', 'BRADLEY 3PT RATING (Bradley 3-Point Shooting Rating)', 'bradley_rating', {'player'})]), ('Scoring', [('FGA', 'FGA (Field Goals Attempted)', 'base', {'team', 'player'}), ('FGM', 'FGM (Field Goals Made)', 'base', {'team', 'player'}), ('FG_PCT', 'FG% (Field Goal Percentage)', 'base', {'team', 'player'}), ('FG3A', '3PA (3-Point Attempts)', 'base', {'team', 'player'}), ('FG3M', '3PM (3-Point Makes)', 'base', {'team', 'player'}), ('FG3_PCT', '3P% (3-Point Percentage)', 'base', {'team', 'player'}), ('FTA', 'FTA (Free Throw Attempts)', 'base', {'team', 'player'}), ('FTM', 'FTM (Free Throws Made)', 'base', {'team', 'player'}), ('FT_PCT', 'FT% (Free Throw Percentage)', 'base', {'team', 'player'}), ('PTS', 'PTS (Points)', 'base', {'team', 'player'}), ('PPS', 'PPS (Points Per Shot)', 'calculated', {'team', 'player'}), ('FT_RATE', 'FT RATE (Free Throw Rate)', 'calculated', {'team', 'player'}), ('FG3A_RATE', '3PA RATE (3-Point Attempt Rate)', 'calculated', {'team', 'player'})]), ('Rebounding', [('REB', 'REB (Rebounds)', 'base', {'team', 'player'}), ('OREB', 'OREB (Offensive Rebounds)', 'base', {'team', 'player'}), ('DREB', 'DREB (Defensive Rebounds)', 'base', {'team', 'player'})]), ('Playmaking / Ball Security', [('AST', 'AST (Assists)', 'base', {'team', 'player'}), ('TOV', 'TOV (Turnovers)', 'base', {'team', 'player'})]), ('Defense', [('STL', 'STL (Steals)', 'base', {'team', 'player'}), ('BLK', 'BLK (Blocks)', 'base', {'team', 'player'}), ('BLKA', 'BLKA (Blocked Attempts)', 'base', {'player'}), ('PF', 'PF (Personal Fouls)', 'base', {'team', 'player'}), ('PFD', 'PFD (Personal Fouls Drawn)', 'base', {'team', 'player'})]), ('Advanced', [('OFF_RATING', 'OFF RTG (Offensive Rating)', 'advanced', {'team', 'player'}), ('DEF_RATING', 'DEF RTG (Defensive Rating)', 'advanced', {'team', 'player'}), ('NET_RATING', 'NET RTG (Net Rating)', 'advanced', {'team', 'player'}), ('TS_PCT', 'TS% (True Shooting Percentage)', 'advanced', {'team', 'player'}), ('EFG_PCT', 'EFG% (Effective FG Percentage)', 'advanced', {'team', 'player'}), ('USG_PCT', 'USG% (Usage Percentage)', 'advanced', {'team', 'player'}), ('PACE', 'PACE (Pace)', 'advanced', {'team', 'player'}), ('PIE', 'PIE (Player Impact Estimate)', 'advanced', {'team', 'player'}), ('AST_PCT', 'AST% (Assist Percentage)', 'advanced', {'team', 'player'}), ('AST_TOV', 'AST/TO (Assist to Turnover Ratio)', 'advanced', {'team', 'player'}), ('AST_RATIO', 'AST RATIO (Assist Ratio)', 'advanced', {'team', 'player'}), ('OREB_PCT', 'OREB% (Offensive Rebound Percentage)', 'advanced', {'team', 'player'}), ('DREB_PCT', 'DREB% (Defensive Rebound Percentage)', 'advanced', {'team', 'player'}), ('REB_PCT', 'REB% (Rebound Percentage)', 'advanced', {'team', 'player'}), ('TM_TOV_PCT', 'TOV% (Team Turnover Percentage)', 'advanced', {'team', 'player'})]), ('Overall', [('MIN', 'MIN (Minutes)', 'base', {'team', 'player'}), ('PLUS_MINUS', '+/- (Plus/Minus)', 'base', {'team', 'player'}), ('GP', 'GP (Games Played)', 'base', {'team', 'player'}), ('DD2', 'DD2 (Double-Doubles)', 'base', {'team', 'player'}), ('TD3', 'TD3 (Triple-Doubles)', 'base', {'team', 'player'}), ('AGE', 'AGE (Age)', 'base', {'player'}), ('W', 'W (Wins)', 'base', {'team'}), ('L', 'L (Losses)', 'base', {'team'}), ('W_PCT', 'W% (Win Percentage)', 'base', {'team'})]), ('Bio', [('PLAYER_HEIGHT_INCHES', 'HEIGHT (Height, Inches)', 'bio', {'player'}), ('PLAYER_WEIGHT', 'WEIGHT (Weight, Lbs)', 'bio', {'player'}), ('DRAFT_YEAR', 'DRAFT YR (Draft Year)', 'bio', {'player'}), ('DRAFT_ROUND', 'DRAFT RD (Draft Round)', 'bio', {'player'}), ('DRAFT_NUMBER', 'DRAFT PICK (Draft Number)', 'bio', {'player'})]), ('Defense Tracking (Real Shot Defense)', [('D_FG_PCT', 'OPP FG% (Opponent FG%, This Player Defending)', 'defense_tracking', {'player'}), ('NORMAL_FG_PCT', 'LEAGUE AVG FG% (Same Shots, League Average)', 'defense_tracking', {'player'}), ('PCT_PLUSMINUS', 'DEF IMPACT (Opponent FG% vs League Avg, Percentage Points)', 'defense_tracking', {'player'}), ('D_FGA', 'DEF FGA (Shots Defended)', 'defense_tracking', {'player'})]), ('Hustle (Effort Stats)', [('CONTESTED_SHOTS', 'CONTESTED SHOTS', 'hustle', {'player'}), ('DEFLECTIONS', 'DEFLECTIONS', 'hustle', {'player'}), ('CHARGES_DRAWN', 'CHARGES DRAWN', 'hustle', {'player'}), ('SCREEN_ASSISTS', 'SCREEN ASSISTS', 'hustle', {'player'}), ('LOOSE_BALLS_RECOVERED', 'LOOSE BALLS RECOVERED', 'hustle', {'player'}), ('BOX_OUTS', 'BOX OUTS', 'hustle', {'player'})]), ('Clutch (Last 5 Min, Close Games)', [('PTS', 'CLUTCH PTS (Points in Clutch Situations)', 'clutch', {'player'}), ('FG_PCT', 'CLUTCH FG% (Field Goal % in Clutch Situations)', 'clutch', {'player'}), ('FG3_PCT', 'CLUTCH 3P% (3-Point % in Clutch Situations)', 'clutch', {'player'}), ('AST', 'CLUTCH AST', 'clutch', {'player'}), ('REB', 'CLUTCH REB', 'clutch', {'player'}), ('PLUS_MINUS', 'CLUTCH +/-', 'clutch', {'player'})])]


# Salary: each player's cap hit (a team's: its whole payroll) from the salary spreadsheet, in $ millions -- a
# season-level number, so it's offered where a chart ranks or compares season values (Bar Chart, Scatter Plot,
# Histogram/Density, Cumulative Distribution, Box Plot) and in Stat Formula Creator, not in game-by-game charts.
SALARY_STAT = ("SALARY", "SALARY (Salary, $M)", "salary", {"team", "player"})
_bio_at = next((i for i, (c, _s) in enumerate(AXIS_GRAPH_STATS) if c == "Bio"), len(AXIS_GRAPH_STATS) - 1)
AXIS_GRAPH_STATS.insert(_bio_at + 1, ("Salary", [SALARY_STAT]))


def get_stats_for_mode(mode, exclude_bradley_rating=False, include_salary=False):
    """
    Returns AXIS_GRAPH_STATS filtered to the given mode, grouped by
    category -- mirrors _select_axis_stat()'s filtering logic exactly.

    exclude_bradley_rating=True additionally drops any stat whose
    source is "bradley_rating" -- those require the full multi-season
    rating model (bradley_ratings.py), which isn't ported to the
    dashboard yet, so they shouldn't be offered as a selectable
    option in the first place.
    """
    result = []
    for category, stats in AXIS_GRAPH_STATS:
        matching = [s for s in stats if mode in s[3]]
        if not include_salary:
            matching = [s for s in matching if s[2] != "salary"]
        if exclude_bradley_rating:
            matching = [s for s in matching if s[2] != "bradley_rating"]
        if matching:
            result.append((category, matching))
    return result


# Stats where a LOWER value is objectively the better outcome --
# explicitly requested, since "Top 10" previously always meant
# highest value regardless of the stat, which is backwards for these:
# a lower Defensive Rating means fewer points allowed per 100
# possessions (better defense), fewer turnovers/personal
# fouls/blocked-attempts/losses/team-turnover-% are all self-evidently
# better, and a lower opponent FG% while a specific player is
# defending means that defender is doing their job. Used to set the
# smart default direction for every "Highest/Lowest N" control across
# the app -- the user can still flip it manually per stat.
LOWER_IS_BETTER_STATS = {"TOV", "PF", "DEF_RATING", "BLKA", "L", "D_FG_PCT", "TM_TOV_PCT"}


# ---------------------------------------------------------------- stat menu sections
# Every stat menu in the dashboard lists its stats under five section headings, in this order (stat_menus.py draws
# the headings and the thin lines between them). The specialty groups are spread into them: clutch scoring and
# shooting under Offense, screen assists and clutch assists under Playmaking, box outs and clutch rebounds under
# Rebounding, shot-defense tracking and the defensive hustle stats under Defense, and everything that isn't about one
# side of the ball (net rating, minutes, games, record, bio, salary...) under Overall. Within a section the stats keep
# the order listed here. A stat is named by its field, or "source:field" for the clutch / hustle / shot-defense ones.
STAT_SECTIONS = ("Offense", "Playmaking", "Rebounding", "Defense", "Overall")
_SECTION_ORDER = {
    "Offense": ["PTS", "OFF_RATING", "TS_PCT", "EFG_PCT", "USG_PCT", "FGM", "FGA", "FG_PCT", "FG3M", "FG3A", "FG3_PCT",
                "FTM", "FTA", "FT_PCT", "PPS", "FT_RATE", "FG3A_RATE", "BRADLEY_3PT_RATING", "PFD", "BLKA",
                "clutch:PTS", "clutch:FG_PCT", "clutch:FG3_PCT"],
    "Playmaking": ["AST", "TOV", "AST_PCT", "AST_TOV", "AST_RATIO", "TM_TOV_PCT", "hustle:SCREEN_ASSISTS", "clutch:AST"],
    "Rebounding": ["REB", "OREB", "DREB", "REB_PCT", "OREB_PCT", "DREB_PCT", "hustle:BOX_OUTS", "clutch:REB"],
    "Defense": ["DEF_RATING", "STL", "BLK", "PF", "defense_tracking:D_FG_PCT", "defense_tracking:NORMAL_FG_PCT",
                "defense_tracking:PCT_PLUSMINUS", "defense_tracking:D_FGA", "hustle:CONTESTED_SHOTS",
                "hustle:DEFLECTIONS", "hustle:CHARGES_DRAWN", "hustle:LOOSE_BALLS_RECOVERED"],
    "Overall": ["NET_RATING", "PIE", "PLUS_MINUS", "MIN", "GP", "PACE", "DD2", "TD3", "W", "L", "W_PCT", "SALARY",
                "AGE", "PLAYER_HEIGHT_INCHES", "PLAYER_WEIGHT", "DRAFT_YEAR", "DRAFT_ROUND", "DRAFT_NUMBER",
                "clutch:PLUS_MINUS"],
}
_SPECIAL_SOURCES = ("clutch", "hustle", "defense_tracking")
_STAT_PLACE = {name: (sec, i) for sec, names in _SECTION_ORDER.items() for i, name in enumerate(names)}


def _stat_key(field, source=None):
    return f"{source}:{field}" if source in _SPECIAL_SOURCES else field


def stat_section(field, source=None):
    """Which of STAT_SECTIONS a stat belongs to (Overall for anything not listed)."""
    return _STAT_PLACE.get(_stat_key(field, source), ("Overall", 999))[0]


def get_stat_sections(mode, exclude_bradley_rating=False, include_salary=False):
    """The same stats as get_stats_for_mode(), regrouped into [(section, [(field, label, source, modes), ...]), ...]
    in STAT_SECTIONS order (empty sections left out)."""
    flat = [s for _cat, stats in get_stats_for_mode(mode, exclude_bradley_rating, include_salary) for s in stats]
    out = []
    for sec in STAT_SECTIONS:
        items = [s for s in flat if stat_section(s[0], s[2]) == sec]
        items.sort(key=lambda s: _STAT_PLACE.get(_stat_key(s[0], s[2]), (sec, 999))[1])
        if items:
            out.append((sec, items))
    return out
