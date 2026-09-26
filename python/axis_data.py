"""
axis_data.py
------------
Data fetching for axis-based visualizations (currently just Bar
Chart). Unlike nba_data.py, which pulls one subject's shot-level
data, this pulls a season-wide leaderboard for a chosen stat -- every
player or every team at once -- then narrows it down to the requested
comparison group: the top N by the chosen stat, plus any
specifically-requested names not already in that top N.

The chosen stat can come from five different places (stat_source,
set by bradley_analytics.py's BAR_CHART_STATS):
  "base"           -- LeagueDashPlayerStats/TeamStats, Base measure type
  "advanced"       -- same endpoints, Advanced measure type
  "bio"            -- LeagueDashPlayerBioStats (player mode only)
  "calculated"     -- not a raw field anywhere; computed from Base fields
  "bradley_rating" -- Bradley Analytics' own invented multi-season
                       composite ratings (bradley_ratings.py)
Base is always fetched regardless for base/advanced/bio/calculated
(needed for GP/attempts qualifiers, names, and IDs) -- Advanced/Bio
are only fetched when actually needed. bradley_rating skips this
entirely and produces its own already-qualified, already-ranked table.
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

# Maps each percentage stat to the attempts field and minimum that
# should qualify it. Add an entry here if you add another percentage
# stat to BAR_CHART_STATS in bradley_analytics.py. The three minimums
# above assume PER_MODE is "PerGame" -- if you switch PER_MODE to
# "Totals" or "Per36", these numbers mean something different and
# should be adjusted too. Doesn't affect manually-included names --
# if you specifically ask for someone, they show up regardless.
PCT_STAT_QUALIFIERS = {
    "FG_PCT": ("FGA", MIN_FGA_PER_GAME),
    "FG3_PCT": ("FG3A", MIN_FG3A_PER_GAME),
    "FT_PCT": ("FTA", MIN_FTA_PER_GAME),
}

# Formulas for "calculated" stats -- not a raw field anywhere, derived
# from Base fields after that data is already in hand. Each function
# takes the Base leaderboard and returns the new column's values.
CALCULATED_STATS = {
    "PPS": lambda df: df["PTS"] / df["FGA"],
    "FT_RATE": lambda df: df["FTA"] / df["FGA"],
    "FG3A_RATE": lambda df: df["FG3A"] / df["FGA"],
}


# Read the axis chart request from Bradley Analytics
request = pd.read_csv(
    DATA_DIR / "axis_request.csv"
)

mode = request.loc[0, "mode"]
stat_field = request.loc[0, "stat_field"]
stat_source = request.loc[0, "stat_source"]
top_n = int(request.loc[0, "top_n"])
season = request.loc[0, "season"]

id_column = "PLAYER_ID" if mode == "player" else "TEAM_ID"
name_column = "PLAYER_NAME" if mode == "player" else "TEAM_NAME"

# included_names is stored pipe-separated since a plain CSV cell can't
# hold a list. Empty string -> no manually-included names.
raw_included = request.loc[0, "included_names"]
included_names = (
    [name for name in str(raw_included).split("|") if name]
    if pd.notna(raw_included)
    else []
)


# ---------------------------------------------------------------- Bradley ratings (separate path entirely)
if stat_source == "bradley_rating":
    if stat_field == "BRADLEY_3PT_RATING":
        leaderboard = bradley_ratings.compute_three_point_rating(
            season, SEASON_TYPE, SETTINGS
        )
    else:
        raise SystemExit(f"Unknown Bradley rating: {stat_field}")

    name_column = "PLAYER_NAME"
    id_column = "PLAYER_ID"

    # Save the full per-player breakdown (season-by-season scores,
    # weights actually used after dampening, bonus applied) as a
    # companion file -- lets you audit exactly why any player ended up
    # with the rating they did, not just see the final number.
    breakdown_path = DATA_DIR / f"{stat_field.lower()}_breakdown.csv"
    leaderboard.sort_values(stat_field, ascending=False).to_csv(
        breakdown_path, index=False
    )
    print(f"Saved rating breakdown to {breakdown_path}\n")

    # Already qualified -- the rating's own per-season 3PA minimum
    # already excludes small-sample players, so the standard GP/
    # attempts qualifiers below don't apply here.
    qualified_leaderboard = leaderboard.sort_values(
        stat_field, ascending=False
    ).reset_index(drop=True)

else:
    # ---------------------------------------------------------------- Base (always fetched)
    # Needed regardless of stat_source -- GP and attempts fields drive the
    # qualifiers below, and this is also where names/IDs come from.
    print(f"Downloading base leaderboard for {season}...\n")

    # ERROR HANDLING
    # Same network/availability risks as nba_data.py's calls. Customize
    # the message printed below.
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

        leaderboard = base_response.get_data_frames()[0]
    except Exception as exc:
        raise SystemExit(
            f"Could not download the leaderboard from NBA.com: {exc}"
        )

    if leaderboard.empty:
        raise SystemExit(
            f"No leaderboard data found for {season}."
        )


    # ---------------------------------------------------------------- Advanced (conditional)
    if stat_source == "advanced":
        print(f"Downloading advanced stats for {stat_field}...\n")

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

        leaderboard = leaderboard.merge(
            advanced_df[[id_column, stat_field]],
            on=id_column,
            how="left"
        )


    # ---------------------------------------------------------------- Bio (conditional, player only)
    if stat_source == "bio":
        print(f"Downloading player bio stats for {stat_field}...\n")

        try:
            bio_response = leaguedashplayerbiostats.LeagueDashPlayerBioStats(
                season=season,
                season_type_all_star=SEASON_TYPE,
                # Hardcoded, not tied to the PER_MODE setting -- height/
                # weight/draft info don't vary by per-mode, and this
                # endpoint only accepts "Totals"/"PerGame" (a smaller set
                # than the per_mode_detailed used elsewhere), so reusing
                # PER_MODE directly could pass an invalid value here if
                # it's ever set to something like "Per36".
                per_mode_simple="PerGame",
            )
            bio_df = bio_response.get_data_frames()[0]
        except Exception as exc:
            raise SystemExit(
                f"Could not download bio stats from NBA.com: {exc}"
            )

        leaderboard = leaderboard.merge(
            bio_df[[id_column, stat_field]],
            on=id_column,
            how="left"
        )

        # Undrafted players have "Undrafted" (text) instead of a number
        # for DRAFT_YEAR/DRAFT_ROUND/DRAFT_NUMBER -- coerced to NaN here
        # so sorting doesn't break on a mixed text/number column. NaN
        # values naturally sort last and get excluded by the qualifiers
        # below.
        if stat_field.startswith("DRAFT_"):
            leaderboard[stat_field] = pd.to_numeric(
                leaderboard[stat_field], errors="coerce"
            )


    # ---------------------------------------------------------------- Calculated (conditional)
    if stat_source == "calculated":
        leaderboard[stat_field] = CALCULATED_STATS[stat_field](leaderboard)


    # Sort by the chosen stat, best value first
    leaderboard = leaderboard.sort_values(
        stat_field, ascending=False
    ).reset_index(drop=True)

    # Games-played qualifier for the top-N ranking (see MIN_GAMES_PLAYED
    # above). Manually-included names below still search the full,
    # unfiltered leaderboard -- a deliberate request should work
    # regardless of games played.
    qualified_leaderboard = leaderboard[
        leaderboard["GP"] >= MIN_GAMES_PLAYED
    ].reset_index(drop=True)

    # Minimum-attempts qualifier, only for percentage stats (see
    # PCT_STAT_QUALIFIERS above).
    if stat_field in PCT_STAT_QUALIFIERS:
        attempts_field, min_attempts = PCT_STAT_QUALIFIERS[stat_field]
        qualified_leaderboard = qualified_leaderboard[
            qualified_leaderboard[attempts_field] >= min_attempts
        ].reset_index(drop=True)


def find_match(name: str, names_series: pd.Series):
    """
    Match a user-entered name against the leaderboard's name column.
    Exact match first (case-insensitive), then falls back to a
    partial match -- same spirit as resolve_team_color/resolve_team_id
    in bradley_analytics.py.
    """
    name_lower = name.lower().strip()

    exact = names_series[names_series.str.lower() == name_lower]
    if not exact.empty:
        return exact.index[0]

    partial = names_series[names_series.str.lower().str.contains(name_lower, regex=False)]
    if not partial.empty:
        return partial.index[0]

    return None


# Start with the top N
top_rows = qualified_leaderboard.iloc[:top_n].copy()
top_names_lower = set(top_rows[name_column].str.lower())

# Add any manually-requested names that aren't already in the top N
missing_indices = []

for name in included_names:
    match_idx = find_match(name, leaderboard[name_column])

    if match_idx is None:
        print(f"Could not find a match for \"{name}\" -- skipping.")
        continue

    matched_name_lower = leaderboard.loc[match_idx, name_column].lower()

    if matched_name_lower not in top_names_lower:
        missing_indices.append(match_idx)
        top_names_lower.add(matched_name_lower)

if missing_indices:
    final_rows = pd.concat([top_rows, leaderboard.loc[missing_indices]])
else:
    final_rows = top_rows


axis_data = final_rows[[name_column, stat_field]].rename(
    columns={name_column: "name", stat_field: "value"}
)

# Carry an image-URL key through for bar_chart.r. Player mode uses
# PLAYER_ID directly (NBA.com headshot CDN). Team mode is translated
# to ESPN's lowercase team abbreviation here, since that's what
# ESPN's logo CDN needs, not NBA.com's own numeric team_id -- keeps
# bar_chart.r simple, it just builds the URL from whatever's here.
#
# NBA.com's own team logo CDN (cdn.nba.com/logos/nba/{TEAM_ID}/...)
# only serves SVG, which needs extra local rendering support R may
# not have. ESPN's CDN serves PNG instead, matching the same format
# the player headshots already use successfully.
#
# team_id keys match TEAM_IDS in bradley_analytics.py exactly. A
# handful of these abbreviations are genuine ESPN irregularities, not
# typos (e.g. Golden State is "gs" not "gsw", Utah is the full word
# "utah" not a 3-letter code) -- confirmed directly against ESPN's own
# team data and live game pages before writing this, but if one
# specific team's logo doesn't load, this table is the first place to
# check.
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
    axis_data["entity_id"] = final_rows["PLAYER_ID"].values
else:
    axis_data["entity_id"] = final_rows["TEAM_ID"].map(TEAM_ESPN_ABBREV).values

# If specific names were requested, highlight just those bars in the
# chosen accent color (rest render in a neutral gray in bar_chart.r).
# If no names were requested, every bar gets the accent color.
if included_names:
    included_lower = [n.lower() for n in included_names]
    axis_data["is_included"] = axis_data["name"].str.lower().apply(
        lambda n: any(inc in n for inc in included_lower)
    )
else:
    axis_data["is_included"] = True


axis_data.to_csv(
    DATA_DIR / "axis_data.csv",
    index=False
)

print(
    f"Downloaded {len(axis_data)} entries for the bar chart."
)
