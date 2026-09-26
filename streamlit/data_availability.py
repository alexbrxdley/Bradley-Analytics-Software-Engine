"""
data_availability.py -- which seasons each kind of NBA data actually exists for.

Every picker in the dashboard is filtered through this, so a season (or player) is only offered if the visualization you
picked can really be drawn from it. Start years below are the FIRST season of each range:

  1996-97  shot locations (the earliest a shot chart can be made), season stat tables (incl. advanced, bio, clutch),
           game logs, rosters, quarter splits, head-to-head (player vs player)
  2007-08  lineup data (2-5 man lineup combinations -- the On/Off Lineup Network)
  2013-14  player tracking: passing, defensive tracking -- league-wide tracking began with the 2013-14 season
  2015-16  hustle stats and play types (Synergy)

The 1996-97 and 2013-14 lines are confirmed (1996-97 by the shot-chart endpoint; 2013-14 by the NBA's own announcement that
tracking was installed in every arena beginning with 2013-14). The others are the NBA's published start of each dataset.
If one is ever wrong, it is a one-number change here -- nothing else needs touching.

A team is also only offered for seasons its franchise existed under that team ID (the current Charlotte Hornets franchise
began in 2004-05; the 1990s Hornets are the New Orleans franchise in the NBA's data).
"""

import re

SOURCE_START = {
    "shots": 1996, "season_stats": 1996, "bio": 1996, "clutch": 1996, "game_log": 1996, "roster": 1996,
    "quarters": 1996, "vs_player": 1996,
    "lineups": 2007,
    "defense_tracking": 2013, "passing": 2013,
    "hustle": 2015, "playtype": 2015,
}
SOURCE_LABEL = {
    "shots": "shot-location", "season_stats": "season stat", "bio": "player bio", "clutch": "clutch", "game_log": "game-log",
    "roster": "roster", "quarters": "quarter-split", "vs_player": "head-to-head", "lineups": "lineup",
    "defense_tracking": "defensive-tracking", "passing": "passing-tracking", "hustle": "hustle-stat", "playtype": "play-type",
}
# what a stat's own "source" tag in stats_config means for availability
STAT_SOURCE_MAP = {"base": "season_stats", "calculated": "season_stats", "advanced": "season_stats", "bio": "bio",
                   "defense_tracking": "defense_tracking", "hustle": "hustle", "clutch": "clutch"}
ADV_CATEGORY_SOURCES = {"Offense": "season_stats", "Defense": "defense_tracking", "Hustle": "hustle", "Clutch": "clutch",
                        "Play-Type": "playtype", "Matchups": "vs_player"}
# first season (start year) each franchise exists under today's team ID, where it isn't 1996 or earlier
TEAM_FIRST_START = {1610612766: 2004}          # Charlotte Hornets (the Bobcats began 2004-05)
NBA_TEAM_NAMES = {1610612766: "Charlotte Hornets"}

_SEASON_RE = re.compile(r"^(\d{4})-\d{2}$")


def season_start(season: str):
    m = _SEASON_RE.match(str(season))
    return int(m.group(1)) if m else None


def season_label(year: int) -> str:
    return f"{year}-{str(year + 1)[-2:]}"


def is_season_list(options) -> bool:
    return isinstance(options, (list, tuple)) and len(options) > 0 and all(isinstance(o, str) and _SEASON_RE.match(o) for o in options)


def viz_sources(viz) -> set:
    """Which data a Search-by-Player / Search-by-Team visualization is drawn from (stat-based ones add their stats' own sources)."""
    v = str(viz or "").lower()
    if not v:
        return set()
    if "passing" in v:
        return {"passing"}
    if "impact clock" in v:
        return {"quarters"}
    if "calendar" in v or "trend" in v or "momentum" in v:
        return {"game_log"}
    if "shot chart" in v or "heat map" in v or "small multiples" in v or "sankey" in v or "shot flow" in v or "court" in v:
        return {"shots"}
    return {"season_stats"}


def required_sources(category=None, viz=None, adv_category=None, stat_sources=(), key=None) -> set:
    s = set(stat_sources or ())
    if key == "matchup_season":
        s.add("vs_player")
    if category == "On/Off Lineup Network":
        s.add("lineups")
    if category == "Advanced Stats" and adv_category:
        for prefix, src in ADV_CATEGORY_SOURCES.items():
            if str(adv_category).startswith(prefix):
                s.add(src)
    if category in ("Search by Player", "Search by Team"):
        s |= viz_sources(viz)
    return s or {"season_stats"}


def min_start_year(sources) -> int:
    return max([SOURCE_START.get(s, 1996) for s in (sources or ())] or [1996])


def binding_source(sources):
    """The source that sets the earliest season (used to explain a limit)."""
    return max(sources or {"season_stats"}, key=lambda s: SOURCE_START.get(s, 1996))


def filter_seasons(options, sources, team_ids=()) -> list:
    lo = min_start_year(sources)
    for tid in team_ids or ():
        lo = max(lo, TEAM_FIRST_START.get(int(tid), 0))
    return [o for o in options if (season_start(o) or 0) >= lo]


def explain_empty(sources, subject=None, team_ids=()) -> str:
    src = binding_source(sources)
    lo = min_start_year(sources)
    who = f" for {subject}" if subject else ""
    team_note = ""
    for tid in team_ids or ():
        if TEAM_FIRST_START.get(int(tid), 0) > SOURCE_START.get(src, 1996):
            team_note = f" ({NBA_TEAM_NAMES.get(int(tid), 'this team')} began in {season_label(TEAM_FIRST_START[int(tid)])})"
    return f"No seasons are available{who}: {SOURCE_LABEL.get(src, src)} data starts in {season_label(lo)}{team_note}."


def player_eligible(span, min_year, season_year=None) -> bool:
    """span = (first season start year, last season start year). Eligible if any part of the career is inside the data range."""
    if not span:
        return True                                    # no career information -> don't hide anyone on a guess
    first, last = span
    if last < min_year:
        return False
    if season_year is not None and not (first <= season_year <= last):
        return False
    return True
