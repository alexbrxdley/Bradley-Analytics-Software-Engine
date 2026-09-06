"""
Bradley Analytics Software Engine
----------------------------------
Main command-line entry point.

Walks the user through searching by player or team, choosing a
visualization (court-based shot charts, or stat-driven bar charts,
scatter plots, and Bradley Analytics' own invented ratings), then
hands off to the matching Python data-fetching script and R rendering
script to produce the final image.

Launch the Bradley Analytics Software Engine:
For Windows run:
.\bradley.bat
For Mac run:
python3 python/bradley_analytics.py
"""

from pathlib import Path
import json
import shutil
import subprocess
import sys

import pandas as pd
from nba_api.stats.static import players
from nba_api.stats.endpoints import commonplayerinfo


# Project folders
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
VISUALIZATIONS_DIR = BASE_DIR / "visualizations"

DATA_DIR.mkdir(exist_ok=True)
VISUALIZATIONS_DIR.mkdir(exist_ok=True)


# All customizable settings live in settings.json at the project root
# -- shared by every Python and R file, so there's one place to edit
# instead of a separate block in each file.
with open(BASE_DIR / "settings.json") as f:
    SETTINGS = json.load(f)

COURT_GRAPH_WIDTH = SETTINGS["dimensions"]["court_graph_width"]
COURT_GRAPH_HEIGHT = SETTINGS["dimensions"]["court_graph_height"]
AXIS_GRAPH_WIDTH = SETTINGS["dimensions"]["axis_graph_width"]
AXIS_GRAPH_HEIGHT = SETTINGS["dimensions"]["axis_graph_height"]
DEFAULT_COLOR = SETTINGS["colors"]["default_color"]


# NBA team colors used for visualization accents
TEAM_COLORS = {
    "hawks": "#E03A3E",
    "celtics": "#007A33",
    "nets": "#000000",
    "hornets": "#1D1160",
    "bulls": "#CE1141",
    "cavaliers": "#860038",
    "mavericks": "#00538C",
    "nuggets": "#0E2240",
    "pistons": "#C8102E",
    "warriors": "#1D428A",
    "rockets": "#CE1141",
    "pacers": "#002D62",
    "clippers": "#C8102E",
    "lakers": "#552583",
    "grizzlies": "#5D76A9",
    "heat": "#98002E",
    "bucks": "#00471B",
    "timberwolves": "#0C2340",
    "pelicans": "#0C2340",
    "knicks": "#006BB6",
    "thunder": "#007AC1",
    "magic": "#0077C0",
    "76ers": "#006BB6",
    "sixers": "#006BB6",
    "suns": "#1D1160",
    "trail blazers": "#E03A3E",
    "blazers": "#E03A3E",
    "kings": "#5A2D81",
    "spurs": "#C4CED4",
    "raptors": "#CE1141",
    "jazz": "#002B5C",
    "wizards": "#002B5C",
}


def resolve_team_color(team: str) -> str:
    """
    Match a user-entered team name to that team's brand color.

    Checks for an exact match first (e.g. "celtics"), then falls back to
    a partial match so something like "boston celtics" still resolves.
    If nothing matches, returns DEFAULT_COLOR rather than raising an
    error, since the team color is only a visual accent and shouldn't
    stop the whole run.
    """
    team = team.lower().strip()

    if team in TEAM_COLORS:
        return TEAM_COLORS[team]

    for name, color in TEAM_COLORS.items():
        if name in team:
            return color

    return DEFAULT_COLOR


def resolve_color(color_input: str) -> str:
    """
    Accepts either a team name (resolved via resolve_team_color) or a
    raw hex color code (e.g. "#FF5733" or "FF5733"), and returns a
    valid hex color string either way.
    """
    hex_candidate = color_input.strip().lstrip("#")

    is_hex_code = (
        len(hex_candidate) == 6
        and all(c in "0123456789abcdefABCDEF" for c in hex_candidate)
    )

    if is_hex_code:
        return f"#{hex_candidate.upper()}"

    return resolve_team_color(color_input)


# NBA team IDs, used to query team-wide shot data. Keyed the same way
# as TEAM_COLORS so the two dicts stay in sync and resolve_team_id can
# mirror resolve_team_color's matching logic exactly.
TEAM_IDS = {
    "hawks": 1610612737,
    "celtics": 1610612738,
    "nets": 1610612751,
    "hornets": 1610612766,
    "bulls": 1610612741,
    "cavaliers": 1610612739,
    "mavericks": 1610612742,
    "nuggets": 1610612743,
    "pistons": 1610612765,
    "warriors": 1610612744,
    "rockets": 1610612745,
    "pacers": 1610612754,
    "clippers": 1610612746,
    "lakers": 1610612747,
    "grizzlies": 1610612763,
    "heat": 1610612748,
    "bucks": 1610612749,
    "timberwolves": 1610612750,
    "pelicans": 1610612740,
    "knicks": 1610612752,
    "thunder": 1610612760,
    "magic": 1610612753,
    "76ers": 1610612755,
    "sixers": 1610612755,
    "suns": 1610612756,
    "trail blazers": 1610612757,
    "blazers": 1610612757,
    "kings": 1610612758,
    "spurs": 1610612759,
    "raptors": 1610612761,
    "jazz": 1610612762,
    "wizards": 1610612764,
}


def resolve_team_id(team: str):
    """
    Match a user-entered team name to that team's NBA team ID.

    Same exact-then-partial matching as resolve_team_color. Unlike the
    color lookup, there's no sensible default here -- returns None if
    nothing matches, since a team-data request can't proceed without a
    real team ID.
    """
    team = team.lower().strip()

    if team in TEAM_IDS:
        return TEAM_IDS[team]

    for name, team_id in TEAM_IDS.items():
        if name in team:
            return team_id

    return None


# Available visualizations
COURT_GRAPHS = [
    "Shot Chart",
    "Heat Map",
    "Hex Shot Chart",
]
ANIMATED_GRAPHS = [
    "Animated Shot Chart",
]
AXIS_GRAPHS = [
    "Bar Chart",
    "Scatter Plot",
]

ALL_VISUALIZATIONS = COURT_GRAPHS + AXIS_GRAPHS + ANIMATED_GRAPHS

SCRIPTS = {
    "Shot Chart": "shot_chart.R",
    "Heat Map": "heat_map.R",
    "Hex Shot Chart": "hex_shot_chart.R",
    "Animated Shot Chart": "animated_shot_chart.R",
    "Bar Chart": "bar_chart.R",
    "Scatter Plot": "scatter_plot.R",
}

# Animated Shot Chart saves a .gif instead of a .png -- everything
# else in this project outputs .png.
GIF_VISUALIZATIONS = {"Animated Shot Chart"}

# Stats available for axis graphs: (API field name, display label,
# source, modes). source tells axis_data.py which endpoint/formula to
# use: "base" (LeagueDashPlayerStats/TeamStats, Base measure type --
# already used), "advanced" (same endpoints, Advanced measure type),
# "bio" (LeagueDashPlayerBioStats, player mode only), "calculated"
# (not a raw field anywhere, computed from Base fields in axis_data.py),
# or "bradley_rating" (Bradley Analytics' own invented multi-season
# composite ratings, computed in bradley_ratings.py -- see
# BRADLEY_RATING_DESCRIPTIONS below for the glossary text shown above
# each one in the terminal).
# modes is which of {"player", "team"} the stat applies to -- the
# stat picker below filters to only what's valid for the current mode.

# Printed above its stat in the terminal picker -- keep this in sync
# with each rating's actual formula in bradley_ratings.py/settings.json.
BRADLEY_RATING_DESCRIPTIONS = {
    "BRADLEY_3PT_RATING": (
        "Blends 3P% (70%) and 3PA volume (30%), each ranked against "
        "that season's league. Combines the current season with the 2 "
        "before it (weighted ~70/20/10) -- an old below-average season "
        "counts for less the further it falls below your recent form, "
        "on a sliding scale, not a hard cutoff. Being strong 3-4 years "
        "back too adds a small bonus that also scales smoothly with "
        "how strong. Needs 30+ total 3-point attempts this season to "
        "qualify."
    ),
}

# Y-axis title wording for each stat. Common short acronyms/rate stats
# (FGA, FGM, TS%, etc.) stay as their abbreviation since spelling them
# out reads worse, not better. Everything else uses its natural name.
# Bradley Analytics' own stats get Title Case, matching a named
# product rather than a raw stat. Edit any individual entry freely --
# this is the only place that controls how a stat's name reads on the
# chart.
STAT_DISPLAY_NAMES = {
    # Scoring
    "FGA": "FGA",
    "FGM": "FGM",
    "FG_PCT": "FG%",
    "FG3A": "3PA",
    "FG3M": "3PM",
    "FG3_PCT": "3P%",
    "FTA": "FTA",
    "FTM": "FTM",
    "FT_PCT": "FT%",
    "PTS": "points",
    "PPS": "points per shot",
    "FT_RATE": "FT rate",
    "FG3A_RATE": "3PA rate",
    # Rebounding
    "REB": "rebounds",
    "OREB": "off rebounds",
    "DREB": "def rebounds",
    # Playmaking / Ball Security
    "AST": "assists",
    "TOV": "turnovers",
    # Defense
    "STL": "steals",
    "BLK": "blocks",
    "BLKA": "blocked attempts",
    "PF": "personal fouls",
    "PFD": "personal fouls drawn",
    # Overall
    "MIN": "minutes",
    "PLUS_MINUS": "+/-",
    "GP": "games played",
    "DD2": "double doubles",
    "TD3": "triple doubles",
    "AGE": "age",
    "W": "wins",
    "L": "losses",
    "W_PCT": "win %",
    # Advanced
    "OFF_RATING": "off rating",
    "DEF_RATING": "def rating",
    "NET_RATING": "net rating",
    "TS_PCT": "TS%",
    "EFG_PCT": "EFG%",
    "USG_PCT": "USG%",
    "PACE": "pace",
    "PIE": "PIE",
    "AST_PCT": "AST%",
    "AST_TOV": "AST/TO ratio",
    "AST_RATIO": "assist ratio",
    "OREB_PCT": "OREB%",
    "DREB_PCT": "DREB%",
    "REB_PCT": "REB%",
    "TM_TOV_PCT": "team TOV%",
    # Bio
    "PLAYER_HEIGHT_INCHES": "height (inches)",
    "PLAYER_WEIGHT": "weight (lbs)",
    "DRAFT_YEAR": "draft year",
    "DRAFT_ROUND": "draft round",
    "DRAFT_NUMBER": "draft pick",
    # Bradley Analytics Invented Stats -- Title Case
    "BRADLEY_3PT_RATING": "Bradley 3 Rating",
}

AXIS_GRAPH_STATS = [
    ("Bradley Analytics Invented Stats", [
        ("BRADLEY_3PT_RATING", "BRADLEY 3PT RATING (Bradley 3-Point Shooting Rating)", "bradley_rating", {"player"}),
    ]),
    ("Scoring", [
        ("FGA", "FGA (Field Goals Attempted)", "base", {"player", "team"}),
        ("FGM", "FGM (Field Goals Made)", "base", {"player", "team"}),
        ("FG_PCT", "FG% (Field Goal Percentage)", "base", {"player", "team"}),
        ("FG3A", "3PA (3-Point Attempts)", "base", {"player", "team"}),
        ("FG3M", "3PM (3-Point Makes)", "base", {"player", "team"}),
        ("FG3_PCT", "3P% (3-Point Percentage)", "base", {"player", "team"}),
        ("FTA", "FTA (Free Throw Attempts)", "base", {"player", "team"}),
        ("FTM", "FTM (Free Throws Made)", "base", {"player", "team"}),
        ("FT_PCT", "FT% (Free Throw Percentage)", "base", {"player", "team"}),
        ("PTS", "PTS (Points)", "base", {"player", "team"}),
        ("PPS", "PPS (Points Per Shot)", "calculated", {"player", "team"}),
        ("FT_RATE", "FT RATE (Free Throw Rate)", "calculated", {"player", "team"}),
        ("FG3A_RATE", "3PA RATE (3-Point Attempt Rate)", "calculated", {"player", "team"}),
    ]),
    ("Rebounding", [
        ("REB", "REB (Rebounds)", "base", {"player", "team"}),
        ("OREB", "OREB (Offensive Rebounds)", "base", {"player", "team"}),
        ("DREB", "DREB (Defensive Rebounds)", "base", {"player", "team"}),
    ]),
    ("Playmaking / Ball Security", [
        ("AST", "AST (Assists)", "base", {"player", "team"}),
        ("TOV", "TOV (Turnovers)", "base", {"player", "team"}),
    ]),
    ("Defense", [
        ("STL", "STL (Steals)", "base", {"player", "team"}),
        ("BLK", "BLK (Blocks)", "base", {"player", "team"}),
        ("BLKA", "BLKA (Blocked Attempts)", "base", {"player"}),
        ("PF", "PF (Personal Fouls)", "base", {"player", "team"}),
        ("PFD", "PFD (Personal Fouls Drawn)", "base", {"player", "team"}),
    ]),
    ("Advanced", [
        ("OFF_RATING", "OFF RTG (Offensive Rating)", "advanced", {"player", "team"}),
        ("DEF_RATING", "DEF RTG (Defensive Rating)", "advanced", {"player", "team"}),
        ("NET_RATING", "NET RTG (Net Rating)", "advanced", {"player", "team"}),
        ("TS_PCT", "TS% (True Shooting Percentage)", "advanced", {"player", "team"}),
        ("EFG_PCT", "EFG% (Effective FG Percentage)", "advanced", {"player", "team"}),
        ("USG_PCT", "USG% (Usage Percentage)", "advanced", {"player", "team"}),
        ("PACE", "PACE (Pace)", "advanced", {"player", "team"}),
        ("PIE", "PIE (Player Impact Estimate)", "advanced", {"player", "team"}),
        ("AST_PCT", "AST% (Assist Percentage)", "advanced", {"player", "team"}),
        ("AST_TOV", "AST/TO (Assist to Turnover Ratio)", "advanced", {"player", "team"}),
        ("AST_RATIO", "AST RATIO (Assist Ratio)", "advanced", {"player", "team"}),
        ("OREB_PCT", "OREB% (Offensive Rebound Percentage)", "advanced", {"player", "team"}),
        ("DREB_PCT", "DREB% (Defensive Rebound Percentage)", "advanced", {"player", "team"}),
        ("REB_PCT", "REB% (Rebound Percentage)", "advanced", {"player", "team"}),
        ("TM_TOV_PCT", "TOV% (Team Turnover Percentage)", "advanced", {"player", "team"}),
    ]),
    ("Overall", [
        ("MIN", "MIN (Minutes)", "base", {"player", "team"}),
        ("PLUS_MINUS", "+/- (Plus/Minus)", "base", {"player", "team"}),
        ("GP", "GP (Games Played)", "base", {"player", "team"}),
        ("DD2", "DD2 (Double-Doubles)", "base", {"player", "team"}),
        ("TD3", "TD3 (Triple-Doubles)", "base", {"player", "team"}),
        ("AGE", "AGE (Age)", "base", {"player"}),
        ("W", "W (Wins)", "base", {"team"}),
        ("L", "L (Losses)", "base", {"team"}),
        ("W_PCT", "W% (Win Percentage)", "base", {"team"}),
    ]),
    ("Bio", [
        ("PLAYER_HEIGHT_INCHES", "HEIGHT (Height, Inches)", "bio", {"player"}),
        ("PLAYER_WEIGHT", "WEIGHT (Weight, Lbs)", "bio", {"player"}),
        ("DRAFT_YEAR", "DRAFT YR (Draft Year)", "bio", {"player"}),
        ("DRAFT_ROUND", "DRAFT RD (Draft Round)", "bio", {"player"}),
        ("DRAFT_NUMBER", "DRAFT PICK (Draft Number)", "bio", {"player"}),
    ]),
]


def prompt_int(message: str, valid_range: range) -> int:
    """
    Ask the user for a number, re-prompting until they enter one that is
    both numeric and inside valid_range. Never raises on bad input --
    it just keeps asking.
    """
    while True:
        choice = input(message).strip()

        if choice.isdigit() and int(choice) in valid_range:
            return int(choice)

        print("Invalid selection. Try again.")


def _select_player_and_season():
    """
    Player mode: search for a player, pick a season from their career,
    then ask separately for a team name (used only for accent color).
    Returns (player_full_name, player_id, season). Accent color is
    asked separately later, after visualization selection.
    """

    # Select player
    while True:
        player_name = input("\nEnter player name: ").strip()

        # ERROR HANDLING #1
        # The NBA API lookup can fail if there's no internet connection
        # or NBA.com is temporarily unavailable. Customize the message
        # printed below.
        try:
            matches = players.find_players_by_full_name(player_name)
        except Exception:
            print("\nCould not reach the NBA API. Check your internet connection and try again.\n")
            continue

        if matches:
            player = matches[0]
            player_id = player["id"]

            break

        print("\nPlayer not found. Try again.")


    # Find available seasons
    # ERROR HANDLING #2
    # This can fail for the same reasons as ERROR HANDLING #1 (network
    # issues), or if the NBA API returns unexpected data for this
    # player. Customize the message printed below.
    try:
        info = commonplayerinfo.CommonPlayerInfo(
            player_id=player_id
        )

        career = info.get_data_frames()[0]

        first_year = int(career["FROM_YEAR"][0])
        last_year = int(career["TO_YEAR"][0])
    except Exception:
        print("\nCould not load season data for this player. Please try again.\n")
        raise SystemExit

    seasons = [
        f"{year}-{str(year + 1)[2:]}"
        for year in range(first_year, last_year + 1)
    ]

    print("\nAvailable Seasons\n")

    for i, season in enumerate(seasons, start=1):
        print(f"{i}. {season}")

    season_choice = prompt_int(
        "\nChoose season: ",
        range(1, len(seasons) + 1)
    )

    season = seasons[season_choice - 1]

    return player["full_name"], player_id, season


def _select_team_and_season():
    """
    Team mode: pick a team (used to look up the team ID for the data
    query), then type in a season directly -- unlike player mode,
    there's no "career span" to build a season list from, so this just
    takes free-text input. Accent color is asked separately later, same
    as player mode.
    Returns (team_display_name, team_id, season).
    """

    while True:
        team_input = input("Enter team name: ").strip()

        team_id = resolve_team_id(team_input)

        if team_id is not None:
            break

        print("\nTeam not found. Try again.\n")

    season = input(
        "\nEnter season (ex. 2025-26): "
    ).strip()

    display_name = " ".join(word.capitalize() for word in team_input.split())

    return display_name, team_id, season


def _select_axis_stat(mode: str, prompt_text: str = "Choose stat: "):
    """
    Shared stat picker for every Axis Graph (Bar Chart, Scatter Plot,
    and anything added later) -- filters AXIS_GRAPH_STATS by mode,
    prints it grouped by category with continuous numbering, and
    prints any Bradley rating's glossary description above its entry.
    Returns (stat_field, stat_label, stat_source).
    """
    filtered_categories = []
    for category, stats in AXIS_GRAPH_STATS:
        matching = [s for s in stats if mode in s[3]]
        if matching:
            filtered_categories.append((category, matching))

    numbered_stats = []

    print("\nAvailable Stats\n")

    for category, stats in filtered_categories:
        print(f"{category}:")
        for field, label, source, _ in stats:
            numbered_stats.append((field, label, source))
            if field in BRADLEY_RATING_DESCRIPTIONS:
                print(BRADLEY_RATING_DESCRIPTIONS[field])
            print(f"{len(numbered_stats)}. {label}")
        print()

    stat_choice = prompt_int(
        prompt_text,
        range(1, len(numbered_stats) + 1)
    )

    return numbered_stats[stat_choice - 1]


def _select_bar_chart_options(mode: str):
    """
    Bar Chart mode: stat -> top N -> optional specific inclusions ->
    season -> orientation. No single subject is chosen upfront --
    unlike the court graphs, the comparison group here is driven
    entirely by the stat leaderboard (plus whatever specific names you
    choose to add).
    Returns (stat_field, stat_label, stat_source, top_n, included_names, season, orientation).
    """

    stat_field, stat_label, stat_source = _select_axis_stat(mode)

    top_n = prompt_int(
        "\nDisplay the top __: ",
        range(1, 500)
    )

    entity_word = "player" if mode == "player" else "team"

    included_input = input(
        f"\nEnter {entity_word}(s) name to be included (press Enter to skip): "
    ).strip()

    included_names = (
        [name.strip() for name in included_input.split(",") if name.strip()]
        if included_input
        else []
    )

    season = input(
        "\nEnter season (ex. 2025-26): "
    ).strip()

    print("\n1. Vertical")
    print("2. Horizontal")

    orientation_choice = prompt_int(
        "\nChoose orientation: ",
        range(1, 3)
    )

    orientation = "vertical" if orientation_choice == 1 else "horizontal"

    return stat_field, stat_label, stat_source, top_n, included_names, season, orientation


def _select_scatter_plot_options(mode: str):
    """
    Scatter Plot mode: Y-axis stat -> X-axis stat -> top N (ranked by
    the Y-axis stat) -> optional specific inclusions -> season. No
    orientation prompt -- that's specific to Bar Chart.
    Returns (stat_field_y, stat_label_y, stat_source_y, stat_field_x,
    stat_label_x, stat_source_x, top_n, included_names, season).
    """

    stat_field_y, stat_label_y, stat_source_y = _select_axis_stat(
        mode, "Choose first stat measurement (y axis): "
    )

    stat_field_x, stat_label_x, stat_source_x = _select_axis_stat(
        mode, "Choose second stat measurement (x axis): "
    )

    top_n = prompt_int(
        "\nDisplay the top __ (ranked by the Y-axis stat): ",
        range(1, 500)
    )

    entity_word = "player" if mode == "player" else "team"

    included_input = input(
        f"\nEnter {entity_word}(s) name to be included (press Enter to skip): "
    ).strip()

    included_names = (
        [name.strip() for name in included_input.split(",") if name.strip()]
        if included_input
        else []
    )

    season = input(
        "\nEnter season (ex. 2025-26): "
    ).strip()

    return (
        stat_field_y, stat_label_y, stat_source_y,
        stat_field_x, stat_label_x, stat_source_x,
        top_n, included_names, season
    )


def main() -> None:
    """Run the full Bradley Analytics workflow from start to finish."""

    print("\n===========================================\n")
    print("   The Bradley Analytics Software Engine")
    print("          Created by Alex Bradley")
    print("\n===========================================\n")


    # Search by player, team, or criteria. Criteria isn't built yet --
    # loop back with a message instead of dead-ending if it's picked.
    while True:
        print("Search by player, team or criteria\n")
        print("1. Player")
        print("2. Team")
        print("3. Criteria")

        mode_choice = prompt_int(
            "\nChoose an option: ",
            range(1, 4)
        )

        if mode_choice == 3:
            print("\nCriteria search isn't available yet.\n")
            continue

        mode = "player" if mode_choice == 1 else "team"
        break


    # Select visualization -- now happens before subject/season
    # selection, since Bar Chart's flow branches off entirely
    # differently right after this.
    print("\nAvailable Visualizations\n")
    print("Court Graphs:")

    for i, name in enumerate(COURT_GRAPHS, start=1):
        print(f"{i}. {name}")

    print("\nAxis Graphs:")

    for i, name in enumerate(AXIS_GRAPHS, start=len(COURT_GRAPHS) + 1):
        print(f"{i}. {name}")

    print("\nAnimated:")

    for i, name in enumerate(ANIMATED_GRAPHS, start=len(COURT_GRAPHS) + len(AXIS_GRAPHS) + 1):
        print(f"{i}. {name}")

    visualization_choice = prompt_int(
        "\nChoose visualization: ",
        range(1, len(ALL_VISUALIZATIONS) + 1)
    )

    selected_visualization = ALL_VISUALIZATIONS[visualization_choice - 1]
    is_axis_graph = selected_visualization in AXIS_GRAPHS
    is_scatter_plot = selected_visualization == "Scatter Plot"


    if is_scatter_plot:
        # Scatter Plot thread -- two stats instead of one, no single
        # subject chosen upfront (same as Bar Chart). Ranked by the
        # Y-axis stat.
        (
            stat_field_y, stat_label_y, stat_source_y,
            stat_field_x, stat_label_x, stat_source_x,
            top_n, included_names, season
        ) = _select_scatter_plot_options(mode)

        filename = (
            f"top-{top_n}-{stat_field_y.lower()}-vs-{stat_field_x.lower()}_{season}"
        )

    elif is_axis_graph:
        # Bar Chart thread -- no single subject chosen upfront. The
        # comparison group comes entirely from the stat leaderboard,
        # plus any specifically-requested names.
        (
            stat_field, stat_label, stat_source, top_n, included_names, season, orientation
        ) = _select_bar_chart_options(mode)

        filename = f"top-{top_n}-{stat_field.lower()}_{season}"

    else:
        # Court graph thread -- unchanged: pick a single subject, with
        # season either coming from their career span (player mode) or
        # asked directly (team mode).
        if mode == "player":
            subject_name, player_id, season = _select_player_and_season()
            team_id = 0
        else:
            subject_name, team_id, season = _select_team_and_season()
            player_id = 0

        filename = (
            subject_name
            .lower()
            .replace(" ", "-")
            + f"_{season}"
        )


    # Select accent color -- a team name or a raw hex code, asked last
    # for every visualization except Scatter Plot, which shows no
    # color at all (images only, no fill/accent to apply).
    if is_scatter_plot:
        color = None
    else:
        color_input = input(
            "\nFor color, enter team name or a color code: "
        ).strip()

        color = resolve_color(color_input)

        print(f"\nAccent color: {color}")


    # Store user selections for the data download.
    # ERROR HANDLING #3
    # Writing the request file can fail if the data/ folder was
    # deleted, is read-only, or the file is already open elsewhere
    # (common on Windows if it's open in Excel). Customize the message
    # printed below.
    try:
        if is_scatter_plot:
            pd.DataFrame({
                "mode": [mode],
                "stat_field_y": [stat_field_y],
                "stat_label_y": [stat_label_y],
                "stat_source_y": [stat_source_y],
                "stat_display_name_y": [STAT_DISPLAY_NAMES.get(stat_field_y, stat_label_y)],
                "stat_field_x": [stat_field_x],
                "stat_label_x": [stat_label_x],
                "stat_source_x": [stat_source_x],
                "stat_display_name_x": [STAT_DISPLAY_NAMES.get(stat_field_x, stat_label_x)],
                "top_n": [top_n],
                "included_names": ["|".join(included_names)],
                "season": [season],
                "filename": [filename],
                "width": [AXIS_GRAPH_WIDTH],
                "height": [AXIS_GRAPH_HEIGHT],
                "visualization": [selected_visualization],
            }).to_csv(
                DATA_DIR / "scatter_request.csv",
                index=False
            )
        elif is_axis_graph:
            pd.DataFrame({
                "mode": [mode],
                "stat_field": [stat_field],
                "stat_label": [stat_label],
                "stat_source": [stat_source],
                "stat_display_name": [STAT_DISPLAY_NAMES.get(stat_field, stat_label)],
                "top_n": [top_n],
                "included_names": ["|".join(included_names)],
                "season": [season],
                "orientation": [orientation],
                "filename": [filename],
                "color": [color],
                "width": [AXIS_GRAPH_WIDTH],
                "height": [AXIS_GRAPH_HEIGHT],
                "visualization": [selected_visualization],
            }).to_csv(
                DATA_DIR / "axis_request.csv",
                index=False
            )
        else:
            pd.DataFrame({
                "mode": [mode],
                "subject": [subject_name],
                "player_id": [player_id],
                "team_id": [team_id],
                "season": [season],
                "filename": [filename],
                "color": [color],
                "width": [COURT_GRAPH_WIDTH],
                "height": [COURT_GRAPH_HEIGHT],
                "visualization": [selected_visualization],
            }).to_csv(
                DATA_DIR / "request.csv",
                index=False
            )
    except OSError:
        print("\nCould not save the request file. Make sure the data/ folder isn't open in another program.\n")
        return


    # Download data
    print("\nDownloading data...\n")

    if is_scatter_plot:
        data_script = "python/scatter_data.py"
    elif is_axis_graph:
        data_script = "python/axis_data.py"
    else:
        data_script = "python/nba_data.py"

    # ERROR HANDLING #4
    # sys.executable always points to the Python currently running this
    # script, so this works whether the system command is "python" or
    # "python3." This should rarely fail, but customize the message
    # printed below if it does.
    try:
        download = subprocess.run(
            [sys.executable, data_script],
            cwd=BASE_DIR
        )
    except FileNotFoundError:
        print(f"\nCould not launch the data download script. Make sure {data_script} exists.\n")
        return

    if download.returncode != 0:
        print("\nDownload failed.\n")
        return


    # Create visualization using R
    print("\nCreating visualization...\n")

    # ERROR HANDLING #5
    # shutil.which() is Python's built-in, cross-platform way to find a
    # command on the system PATH -- it works the same on Windows, Mac,
    # and Linux, so no OS-specific logic is needed here. Customize the
    # message printed below.
    rscript = shutil.which("Rscript")

    if rscript is None:
        print("\nCould not find Rscript. Make sure R is installed and added to your PATH.\n")
        return

    # ERROR HANDLING #6
    # The R visualization script itself can fail to launch if the path
    # found above is invalid. Customize the message printed below.
    try:
        result = subprocess.run(
            [
                rscript,
                f"r/{SCRIPTS[selected_visualization]}"
            ],
            cwd=BASE_DIR
        )
    except FileNotFoundError:
        print("\nCould not run Rscript. Make sure R is installed correctly.\n")
        return

    if result.returncode != 0:
        print("\nVisualization failed.\n")
        return


    output_extension = "gif" if selected_visualization in GIF_VISUALIZATIONS else "png"

    output_file = (
        f"visualizations/"
        f"{filename}_"
        f"{selected_visualization.lower().replace(' ', '-')}.{output_extension}"
    )


    print("\n===========================================\n")
    print("          Visualization Complete!")
    print("\n===========================================\n")
    print(f"Saved to:\n{output_file}")
    print("\nReady for another visualization.\n")


if __name__ == "__main__":
    main()

