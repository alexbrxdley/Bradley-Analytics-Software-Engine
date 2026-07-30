"""
Bradley Analytics Software Engine
----------------------------------
Main command-line entry point.

Walks the user through selecting an NBA player, season, and visualization
type, then hands off to nba_data.py (Python) to pull the data and to the
R scripts in r/ to render the final shot chart or heat map.
"""

from pathlib import Path
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
R_DIR = BASE_DIR / "r"

DATA_DIR.mkdir(exist_ok=True)
VISUALIZATIONS_DIR.mkdir(exist_ok=True)

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

DEFAULT_COLOR = "#1D428A"


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


# Available visualizations
VISUALIZATIONS = [
    "Shot Chart",
    "Heat Map",
]

SCRIPTS = {
    "Shot Chart": "shot_chart.R",
    "Heat Map": "heat_map.R",
}


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


def main() -> None:
    """Run the full Bradley Analytics workflow from start to finish."""

    print("\n===========================================\n")
    print("   The Bradley Analytics Software Engine")
    print("          Created by Alex Bradley")
    print("\n===========================================\n")


    # Select player
    while True:
        player_name = input("Enter player name: ").strip()

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

            print(f"\nPlayer Found: {player['full_name']}")
            break

        print("\nPlayer not found. Try again.\n")


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
        return

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


    # Select visualization
    print("\nAvailable Visualizations\n")

    for i, visualization in enumerate(VISUALIZATIONS, start=1):
        print(f"{i}. {visualization}")

    visualization_choice = prompt_int(
        "\nChoose visualization: ",
        range(1, len(VISUALIZATIONS) + 1)
    )

    selected_visualization = VISUALIZATIONS[
        visualization_choice - 1
    ]


    # Select team color
    team = input(
        "\nEnter team name (for color): "
    ).strip()

    color = resolve_team_color(team)

    print(f"\nAccent color: {color}")


    # Create filename
    filename = (
        player["full_name"]
        .lower()
        .replace(" ", "-")
        + f"_{season}"
    )


    # Store user selections for the data download
    # ERROR HANDLING #3
    # Writing request.csv can fail if the data/ folder was deleted, is
    # read-only, or the file is already open elsewhere (common on
    # Windows if it's open in Excel). Customize the message printed
    # below.
    try:
        pd.DataFrame({
            "player": [player["full_name"]],
            "player_id": [player_id],
            "season": [season],
            "filename": [filename],
            "team": [team],
            "color": [color],
            "width": [3],
            "height": [2.5],
            "visualization": [selected_visualization],
        }).to_csv(
            DATA_DIR / "request.csv",
            index=False
        )
    except OSError:
        print("\nCould not save the request file. Make sure data/request.csv isn't open in another program.\n")
        return


    # Download NBA shot data
    print("\nDownloading data...\n")

    # ERROR HANDLING #4
    # sys.executable always points to the Python currently running this
    # script, so this works whether the system command is "python" or
    # "python3." This should rarely fail, but customize the message
    # printed below if it does.
    try:
        download = subprocess.run(
            [sys.executable, "python/nba_data.py"],
            cwd=BASE_DIR
        )
    except FileNotFoundError:
        print("\nCould not launch the data download script. Make sure python/nba_data.py exists.\n")
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


    output_file = (
        f"visualizations/"
        f"{filename}_"
        f"{selected_visualization.lower().replace(' ', '-')}.png"
    )


    print("\n===========================================\n")
    print("          Visualization Complete!")
    print("\n===========================================\n")
    print(f"Saved to:\n{output_file}")
    print("\nReady for another visualization.\n")


if __name__ == "__main__":
    main()
