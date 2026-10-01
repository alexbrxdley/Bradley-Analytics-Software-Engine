from pathlib import Path

import pandas as pd
from nba_api.stats.endpoints import ShotChartDetail


# Project data folder
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

DATA_DIR.mkdir(exist_ok=True)


# Read the request selected in Bradley Analytics
request = pd.read_csv(
    DATA_DIR / "request.csv"
)

mode = request.loc[0, "mode"]
subject = request.loc[0, "subject"]
player_id = int(request.loc[0, "player_id"])
team_id = int(request.loc[0, "team_id"])
season = request.loc[0, "season"]
visualization = request.loc[0, "visualization"]


# Download shot data -- player mode filters by player_id (team_id=0
# means "any team"), team mode filters by team_id with player_id=0,
# which returns shots from every player on that team for the season.
print(
    f"Downloading shot data for {subject} ({season})...\n"
)

if mode == "player":
    shot_response = ShotChartDetail(
        team_id=0,
        player_id=player_id,
        season_nullable=season,
        context_measure_simple="FGA",
    )
else:
    shot_response = ShotChartDetail(
        team_id=team_id,
        player_id=0,
        season_nullable=season,
        context_measure_simple="FGA",
    )

shots = shot_response.get_data_frames()[0]


if shots.empty:
    raise ValueError(
        f"No shot data found for {subject} during {season}."
    )


shots.to_csv(
    DATA_DIR / "shots.csv",
    index=False
)

print(
    f"Downloaded {len(shots):,} shots."
)


# Download league-wide shot data -- only Hex Shot Chart actually
# uses this, to compare each hex's FG% against the league average
# from that same spot. Every other visualization skips this step
# entirely, since it's a large extra API call for data nothing else
# reads.
if visualization == "Hex Shot Chart":
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