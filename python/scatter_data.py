"""
scatter_data.py
----------------
Data fetching for Scatter Plot. Two stats instead of one: the Y-axis
stat drives ranking and qualifying (same logic axis_data.py uses for
Bar Chart -- top N, plus any manually-included names), then the
X-axis stat's value is looked up for that same final entity set.

Self-contained rather than importing from axis_data.py -- that file
is a running script, not a set of importable functions, and axis_data.py's
Bar Chart pipeline is already tested and working, so this mirrors its
fetch logic instead of risking a refactor of it.

Same five stat sources as Bar Chart (stat_source, set by
bradley_analytics.py's AXIS_GRAPH_STATS): base/advanced/bio/calculated/
bradley_rating.
"""

from pathlib import Path
import json

import pandas as pd
from nba_api.stats.endpoints import (
    leaguedashplayerstats,
    leaguedashteamstats,
    leaguedashplayerbiostats,
)

import bradley_ratings


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

DATA_DIR.mkdir(exist_ok=True)


# All customizable settings live in settings.json at the project root
# -- shared by every Python and R file, so there's one place to edit
# instead of a separate block in each file.
with open(BASE_DIR / "settings.json") as f:
    SETTINGS = json.load(f)

PER_MODE = SETTINGS["data"]["per_mode"]
SEASON_TYPE = SETTINGS["data"]["season_type"]
MIN_GAMES_PLAYED = SETTINGS["data"]["min_games_played"]
MIN_FGA_PER_GAME = SETTINGS["data"]["min_fga_per_game"]
MIN_FG3A_PER_GAME = SETTINGS["data"]["min_fg3a_per_game"]
MIN_FTA_PER_GAME = SETTINGS["data"]["min_fta_per_game"]

PCT_STAT_QUALIFIERS = {
    "FG_PCT": ("FGA", MIN_FGA_PER_GAME),
    "FG3_PCT": ("FG3A", MIN_FG3A_PER_GAME),
    "FT_PCT": ("FTA", MIN_FTA_PER_GAME),
}

CALCULATED_STATS = {
    "PPS": lambda df: df["PTS"] / df["FGA"],
    "FT_RATE": lambda df: df["FTA"] / df["FGA"],
    "FG3A_RATE": lambda df: df["FG3A"] / df["FGA"],
}


def fetch_stat_leaderboard(mode: str, stat_field: str, stat_source: str, season: str, id_column: str):
    """
    Fetches one stat's full season leaderboard, exactly like
    axis_data.py does for Bar Chart -- Base always fetched (for GP/
    attempts/name/ID columns), Advanced/Bio/Calculated layered in only
    when needed. bradley_rating skips all of this and produces its
    own already-qualified table.
    """
    if stat_source == "bradley_rating":
        if stat_field == "BRADLEY_3PT_RATING":
            df = bradley_ratings.compute_three_point_rating(season, SEASON_TYPE, SETTINGS)
        else:
            raise SystemExit(f"Unknown Bradley rating: {stat_field}")
        return df

    try:
        if mode == "player":
            base_response = leaguedashplayerstats.LeagueDashPlayerStats(
                season=season,
                season_type_all_star=SEASON_TYPE,
                measure_type_detailed_defense="Base",
                per_mode_detailed=PER_MODE,
            )
        else:
            base_response = leaguedashteamstats.LeagueDashTeamStats(
                season=season,
                season_type_all_star=SEASON_TYPE,
                measure_type_detailed_defense="Base",
                per_mode_detailed=PER_MODE,
            )
        df = base_response.get_data_frames()[0]
    except Exception as exc:
        raise SystemExit(
            f"Could not download the leaderboard from NBA.com: {exc}"
        )

    if df.empty:
        raise SystemExit(f"No leaderboard data found for {season}.")

    if stat_source == "advanced":
        try:
            if mode == "player":
                advanced_response = leaguedashplayerstats.LeagueDashPlayerStats(
                    season=season,
                    season_type_all_star=SEASON_TYPE,
                    measure_type_detailed_defense="Advanced",
                    per_mode_detailed=PER_MODE,
                )
            else:
                advanced_response = leaguedashteamstats.LeagueDashTeamStats(
                    season=season,
                    season_type_all_star=SEASON_TYPE,
                    measure_type_detailed_defense="Advanced",
                    per_mode_detailed=PER_MODE,
                )
            advanced_df = advanced_response.get_data_frames()[0]
        except Exception as exc:
            raise SystemExit(
                f"Could not download advanced stats from NBA.com: {exc}"
            )

        df = df.merge(
            advanced_df[[id_column, stat_field]], on=id_column, how="left"
        )

    elif stat_source == "bio":
        try:
            bio_response = leaguedashplayerbiostats.LeagueDashPlayerBioStats(
                season=season,
                season_type_all_star=SEASON_TYPE,
                # Hardcoded, not tied to PER_MODE -- see axis_data.py
                # for the full reasoning (this endpoint only accepts
                # "Totals"/"PerGame", a smaller set than PER_MODE's
                # possible values).
                per_mode_simple="PerGame",
            )
            bio_df = bio_response.get_data_frames()[0]
        except Exception as exc:
            raise SystemExit(
                f"Could not download bio stats from NBA.com: {exc}"
            )

        df = df.merge(
            bio_df[[id_column, stat_field]], on=id_column, how="left"
        )

        if stat_field.startswith("DRAFT_"):
            df[stat_field] = pd.to_numeric(df[stat_field], errors="coerce")

    elif stat_source == "calculated":
        df[stat_field] = CALCULATED_STATS[stat_field](df)

    return df


def qualify(df: pd.DataFrame, stat_field: str, stat_source: str) -> pd.DataFrame:
    """Same GP/attempts qualifiers Bar Chart uses -- skipped for
    bradley_rating, which is already qualified by its own per-season
    3PA minimum."""
    if stat_source == "bradley_rating":
        return df.reset_index(drop=True)

    qualified = df[df["GP"] >= MIN_GAMES_PLAYED]

    if stat_field in PCT_STAT_QUALIFIERS:
        attempts_field, min_attempts = PCT_STAT_QUALIFIERS[stat_field]
        qualified = qualified[qualified[attempts_field] >= min_attempts]

    return qualified.reset_index(drop=True)


def find_match(name: str, names_series: pd.Series):
    """Same matching logic as axis_data.py -- exact match first
    (case-insensitive), then a partial-match fallback."""
    name_lower = name.lower().strip()

    exact = names_series[names_series.str.lower() == name_lower]
    if not exact.empty:
        return exact.index[0]

    partial = names_series[names_series.str.lower().str.contains(name_lower, regex=False)]
    if not partial.empty:
        return partial.index[0]

    return None


# ---------------------------------------------------------------- Main
request = pd.read_csv(DATA_DIR / "scatter_request.csv")

mode = request.loc[0, "mode"]
stat_field_y = request.loc[0, "stat_field_y"]
stat_source_y = request.loc[0, "stat_source_y"]
stat_field_x = request.loc[0, "stat_field_x"]
stat_source_x = request.loc[0, "stat_source_x"]
top_n = int(request.loc[0, "top_n"])
season = request.loc[0, "season"]

id_column = "PLAYER_ID" if mode == "player" else "TEAM_ID"
name_column = "PLAYER_NAME" if mode == "player" else "TEAM_NAME"

raw_included = request.loc[0, "included_names"]
included_names = (
    [name for name in str(raw_included).split("|") if name]
    if pd.notna(raw_included)
    else []
)


# Y-axis stat drives ranking and qualifying -- same top-N-plus-
# manually-included-names logic as Bar Chart.
print(f"Downloading {stat_field_y} (Y axis) for {season}...\n")
y_df = fetch_stat_leaderboard(mode, stat_field_y, stat_source_y, season, id_column)

if stat_source_y == "bradley_rating":
    name_column, id_column = "PLAYER_NAME", "PLAYER_ID"

    breakdown_path = DATA_DIR / f"{stat_field_y.lower()}_breakdown.csv"
    y_df.sort_values(stat_field_y, ascending=False).to_csv(breakdown_path, index=False)
    print(f"Saved rating breakdown to {breakdown_path}\n")

y_df = y_df.sort_values(stat_field_y, ascending=False).reset_index(drop=True)
qualified_y = qualify(y_df, stat_field_y, stat_source_y)

top_rows = qualified_y.iloc[:top_n].copy()
top_names_lower = set(top_rows[name_column].str.lower())

missing_indices = []
for name in included_names:
    match_idx = find_match(name, y_df[name_column])

    if match_idx is None:
        print(f"Could not find a match for \"{name}\" -- skipping.")
        continue

    matched_name_lower = y_df.loc[match_idx, name_column].lower()

    if matched_name_lower not in top_names_lower:
        missing_indices.append(match_idx)
        top_names_lower.add(matched_name_lower)

if missing_indices:
    final_rows = pd.concat([top_rows, y_df.loc[missing_indices]])
else:
    final_rows = top_rows


# X-axis stat: only need this same final entity set's values, not a
# fresh top-N/qualifier pass of its own -- the entity set is already
# fixed by the Y-axis stat.
print(f"Downloading {stat_field_x} (X axis) for {season}...\n")
x_df = fetch_stat_leaderboard(mode, stat_field_x, stat_source_x, season, id_column)

x_id_column = "PLAYER_ID" if stat_source_x == "bradley_rating" else id_column
x_lookup = x_df.set_index(x_id_column)[stat_field_x]


scatter_data = final_rows[[name_column, id_column, stat_field_y]].rename(
    columns={name_column: "name", id_column: "entity_key", stat_field_y: "y_value"}
)

scatter_data["x_value"] = scatter_data["entity_key"].map(x_lookup)

# A player/team can qualify for the Y-axis stat but not the X-axis
# stat (e.g. X axis is a Bradley rating with its own attempts minimum
# that this entity doesn't clear) -- there's no valid point to plot
# for them without an X value, so they're dropped, not silently shown
# at a wrong position.
missing_x = scatter_data["x_value"].isna()
if missing_x.any():
    dropped_names = scatter_data.loc[missing_x, "name"].tolist()
    print(
        f"Dropped {missing_x.sum()} entr{'y' if missing_x.sum() == 1 else 'ies'} "
        f"with no qualifying {stat_field_x} value: {', '.join(dropped_names)}"
    )
scatter_data = scatter_data[~missing_x].reset_index(drop=True)


# Carry an image-URL key through for scatter_plot.r -- same CDN
# pattern as Bar Chart. Player mode uses PLAYER_ID directly (NBA.com
# headshot CDN). Team mode is translated to ESPN's lowercase team
# abbreviation, since that's what ESPN's logo CDN needs, not NBA.com's
# own numeric team_id. NBA.com's own team logo CDN only serves SVG,
# which needs extra local rendering support R may not have -- ESPN's
# CDN serves PNG instead, matching the player headshots' format.
#
# team_id keys match TEAM_IDS in bradley_analytics.py exactly. A
# handful of these abbreviations are genuine ESPN irregularities, not
# typos (e.g. Golden State is "gs" not "gsw", Utah is the full word
# "utah" not a 3-letter code) -- confirmed directly against ESPN's own
# team data and live game pages, but if one specific team's logo
# doesn't load, this table is the first place to check.
TEAM_ESPN_ABBREV = {
    1610612737: "atl",  # Hawks
    1610612738: "bos",  # Celtics
    1610612751: "bkn",  # Nets
    1610612766: "cha",  # Hornets
    1610612741: "chi",  # Bulls
    1610612739: "cle",  # Cavaliers
    1610612742: "dal",  # Mavericks
    1610612743: "den",  # Nuggets
    1610612765: "det",  # Pistons
    1610612744: "gs",   # Warriors
    1610612745: "hou",  # Rockets
    1610612754: "ind",  # Pacers
    1610612746: "lac",  # Clippers
    1610612747: "lal",  # Lakers
    1610612763: "mem",  # Grizzlies
    1610612748: "mia",  # Heat
    1610612749: "mil",  # Bucks
    1610612750: "min",  # Timberwolves
    1610612740: "no",   # Pelicans
    1610612752: "ny",   # Knicks
    1610612760: "okc",  # Thunder
    1610612753: "orl",  # Magic
    1610612755: "phi",  # 76ers
    1610612756: "phx",  # Suns
    1610612757: "por",  # Trail Blazers
    1610612758: "sac",  # Kings
    1610612759: "sa",   # Spurs
    1610612761: "tor",  # Raptors
    1610612762: "utah", # Jazz
    1610612764: "wsh",  # Wizards
}

if mode == "player":
    scatter_data["entity_id"] = scatter_data["entity_key"]
else:
    scatter_data["entity_id"] = scatter_data["entity_key"].map(TEAM_ESPN_ABBREV)

scatter_data = scatter_data.drop(columns=["entity_key"])

# If specific names were requested, those entities render larger in
# scatter_plot.r so they stand out from the general leaderboard (the
# chosen accent color only applies in the rare text-label fallback,
# when an entity_id is missing and no image can be shown at all). If
# no names were requested, every point gets the same treatment.
if included_names:
    included_lower = [n.lower() for n in included_names]
    scatter_data["is_included"] = scatter_data["name"].str.lower().apply(
        lambda n: any(inc in n for inc in included_lower)
    )
else:
    scatter_data["is_included"] = True


scatter_data.to_csv(
    DATA_DIR / "scatter_data.csv",
    index=False
)

print(
    f"Downloaded {len(scatter_data)} entries for the scatter plot."
)
