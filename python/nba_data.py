from pathlib import Path

import pandas as pd
from nba_api.stats.endpoints import ShotChartDetail


# Project data folder
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

DATA_DIR.mkdir(exist_ok=True)


# Read the player and season selected in Bradley Analytics
request = pd.read_csv(
    DATA_DIR / "request.csv"
)

player = request.loc[0, "player"]
player_id = int(request.loc[0, "player_id"])
season = request.loc[0, "season"]


# Download player's shot data
print(
    f"Downloading shot data for {player} ({season})...\n"
)

player_response = ShotChartDetail(
    team_id=0,
    player_id=player_id,
    season_nullable=season,
    context_measure_simple="FGA",
)

shots = player_response.get_data_frames()[0]


if shots.empty:
    raise ValueError(
        f"No shot data found for {player} during {season}."
    )


shots.to_csv(
    DATA_DIR / "shots.csv",
    index=False
)

print(
    f"Downloaded {len(shots):,} shots."
)


# Download league shot data for future comparison visualizations
print(
    "\nDownloading comparison shot data...\n"
)

league_response = ShotChartDetail(
    team_id=0,
    player_id=0,
    season_nullable=season,
    context_measure_simple="FGA",
)

comparison_shots = league_response.get_data_frames()[0]


if comparison_shots.empty:
    raise ValueError(
        f"No comparison shot data found for {season}."
    )


comparison_shots.to_csv(
    DATA_DIR / "comparison_shots.csv",
    index=False
)

print(
    f"Downloaded {len(comparison_shots):,} comparison shots."
)