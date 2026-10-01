"""
bradley_ratings.py
-------------------
Bradley Analytics' own invented rating formulas -- multi-season,
percentile-based composite scores on a 0-100 scale. Every input stat
is percentile-ranked within its own season's qualified pool before
being blended, since raw values aren't comparable season-to-season
(league-wide 3-point volume alone has shifted a lot year to year).

Each rating function returns a DataFrame with PLAYER_ID, PLAYER_NAME,
and a column matching the rating's stat field name -- same shape as
a normal season leaderboard, so axis_data.py can treat it the same
way once it's built.
"""

import pandas as pd
from nba_api.stats.endpoints import leaguedashplayerstats


def previous_season(season: str, n: int = 1) -> str:
    """'2023-24', n=1 -> '2022-23'. n=2 -> '2021-22'. Etc."""
    start_year = int(season.split("-")[0])
    new_start = start_year - n
    new_end = (new_start + 1) % 100
    return f"{new_start}-{new_end:02d}"


def fetch_season_totals(season: str, season_type: str) -> pd.DataFrame:
    """
    One season's Base stats at season Totals -- not Per36. Needed as
    Totals specifically because the "30 3PA" qualifier is a real
    season-total attempt count, not a per-36 rate (30 3PA every 36
    minutes would be essentially unreachable -- that's not what a
    volume qualifier is supposed to mean). The Per36 rate used for the
    rating's actual volume input is derived manually below from these
    totals (FG3A * 36 / MIN), rather than fetching Per36 as a second
    separate call.
    """
    response = leaguedashplayerstats.LeagueDashPlayerStats(
        season=season,
        season_type_all_star=season_type,
        measure_type_detailed_defense="Base",
        per_mode_detailed="Totals",
    )
    return response.get_data_frames()[0]


def dampened_weight(
    base_weight: float, floor_weight: float, gap: float, full_shrink_gap: float
) -> float:
    """
    Linear ramp, not a step function -- season -2's weight starts at
    base_weight when gap<=0 (not below recent form at all) and slides
    smoothly down to floor_weight once gap reaches full_shrink_gap or
    more. A player 19.9 points below gets almost the same treatment as
    20.0 points below, not a cliff between them.
    """
    if gap <= 0:
        return base_weight
    t = min(gap, full_shrink_gap) / full_shrink_gap
    return base_weight - (base_weight - floor_weight) * t


def consistency_bonus_amount(
    avg_deep_score: float, baseline: float, max_bonus: float
) -> float:
    """
    Linear ramp, not a hard threshold -- 0 bonus at/below baseline,
    scaling smoothly up to max_bonus at a perfect (1.0) average across
    the deep-history seasons.
    """
    if avg_deep_score <= baseline:
        return 0.0
    t = min((avg_deep_score - baseline) / (1.0 - baseline), 1.0)
    return max_bonus * t


def compute_three_point_rating(
    current_season: str, season_type: str, settings: dict
) -> pd.DataFrame:
    """
    Bradley 3-Point Shooting Rating. Inputs: 3P% and 3PA-per-36
    (derived from season totals), each percentile-ranked within their
    own season's qualified pool (min_3pa total attempts that season or
    more), then blended:
      - pct_weight / volume_weight on the current season's own score
      - season_weights blends current + 2 seasons back
      - outlier_full_shrink_gap/outlier_floor_weight: if 2-seasons-back
        is below the recent (current + -1) average, its weight slides
        down toward outlier_floor_weight the further below it is,
        reaching the floor at outlier_full_shrink_gap points below --
        a smooth ramp, not a cliff. The shrunk amount shifts to the
        current season's weight.
      - consistency_max_bonus: seasons -3 and -4, if both exist and
        qualify, add a bonus that scales smoothly with how far their
        average is above consistency_baseline, up to consistency_max_bonus.
    Rookies (no qualifying prior seasons) get the current season's
    score only, scaled to 0-100.
    """
    cfg = settings["bradley_ratings"]["three_point_rating"]
    min_3pa = cfg["min_3pa"]
    shrinkage_k = cfg["shrinkage_k"]
    pct_weight = cfg["pct_weight"]
    volume_weight = cfg["volume_weight"]
    w_current, w_s1, w_s2 = cfg["season_weights"]
    outlier_full_shrink_gap = cfg["outlier_full_shrink_gap"]
    outlier_floor_weight = cfg["outlier_floor_weight"]
    lookback = cfg["consistency_lookback_seasons"]
    consistency_baseline = cfg["consistency_baseline"]
    consistency_max_bonus = cfg["consistency_max_bonus"]

    def shrink_pct(df: pd.DataFrame) -> pd.Series:
        """
        Pulls each player's 3P% toward that season's league average,
        by an amount that depends on their sample size -- a player
        right at the 30-3PA minimum gets pulled hard toward average
        (their raw percentage isn't a reliable signal yet), while a
        400-attempt shooter barely moves at all (their raw number
        already IS reliable). shrinkage_k is the number of
        league-average "pseudo-attempts" mixed in -- higher = more
        aggressive shrinkage for low-volume players.
        """
        league_avg_pct = df["FG3M"].sum() / df["FG3A"].sum()
        return (df["FG3M"] + shrinkage_k * league_avg_pct) / (df["FG3A"] + shrinkage_k)

    def season_score(df: pd.DataFrame) -> pd.Series:
        """Shrunk 3P% and 3PA-per-36 (derived from totals), each
        percentile-ranked within this season's qualified pool,
        blended by pct_weight/volume_weight."""
        shrunk_pct = shrink_pct(df)
        fg3a_per36 = df["FG3A"] * 36 / df["MIN"]
        pct_rank = shrunk_pct.rank(pct=True)
        vol_rank = fg3a_per36.rank(pct=True)
        return pct_weight * pct_rank + volume_weight * vol_rank

    print(f"Downloading {current_season} 3-point data...\n")
    current_df = fetch_season_totals(current_season, season_type)
    current_df = current_df[current_df["FG3A"] >= min_3pa].copy()

    if current_df.empty:
        raise SystemExit(
            f"No players meet the {min_3pa} 3PA minimum for {current_season}."
        )

    current_df["raw_pct"] = current_df["FG3M"] / current_df["FG3A"]
    current_df["shrunk_pct"] = shrink_pct(current_df)
    current_df["season_score"] = season_score(current_df)

    # scores_by_season[0] = current season, [1] = one season back, etc.
    scores_by_season = {0: current_df.set_index("PLAYER_ID")["season_score"]}

    for n in range(1, lookback + 1):
        season_str = previous_season(current_season, n)
        print(f"Downloading {season_str} 3-point data...\n")
        try:
            df = fetch_season_totals(season_str, season_type)
            df = df[df["FG3A"] >= min_3pa].copy()
            if not df.empty:
                df["season_score"] = season_score(df)
                scores_by_season[n] = df.set_index("PLAYER_ID")["season_score"]
            else:
                scores_by_season[n] = pd.Series(dtype=float)
        except Exception:
            # A season that doesn't exist yet (e.g. this is only the
            # league's 2nd season) or a download hiccup -- treated as
            # no data for that season, same as not qualifying.
            scores_by_season[n] = pd.Series(dtype=float)

    results = []

    for player_id, row in current_df.set_index("PLAYER_ID").iterrows():
        current_pct = scores_by_season[0].get(player_id)
        s1 = scores_by_season.get(1, pd.Series(dtype=float)).get(player_id)
        s2 = scores_by_season.get(2, pd.Series(dtype=float)).get(player_id)

        if s1 is None and s2 is None:
            # Rookie, or no qualifying seasons in the lookback window
            blended = current_pct
            cw, w1, w2 = 1.0, 0.0, 0.0
        else:
            cw, w1, w2 = w_current, w_s1, w_s2

            # Outlier dampening: season -2 exists -- shrink its weight
            # smoothly based on how far below the recent (current + -1)
            # average it is, shifting the difference to the current
            # season.
            if s2 is not None:
                recent_avg = (current_pct + (s1 if s1 is not None else current_pct)) / 2
                gap = recent_avg - s2
                w2_new = dampened_weight(w2, outlier_floor_weight, gap, outlier_full_shrink_gap)
                cw += (w2 - w2_new)
                w2 = w2_new

            # Missing season -1 or -2 (gap year, injury, etc.) --
            # fold its weight into the current season rather than
            # silently treating the missing season as a 0.
            if s1 is None:
                cw += w1
                w1 = 0
            if s2 is None:
                cw += w2
                w2 = 0

            blended = (
                cw * current_pct
                + w1 * (s1 if s1 is not None else 0)
                + w2 * (s2 if s2 is not None else 0)
            )

        rating_before_bonus = max(0, min(100, blended * 100))
        rating = blended * 100

        # Consistency bonus: seasons -3 and -4, only if both exist and
        # qualify -- amount scales smoothly with how strong they were.
        deep_scores = [
            scores_by_season.get(n, pd.Series(dtype=float)).get(player_id)
            for n in range(3, lookback + 1)
        ]
        deep_scores = [s for s in deep_scores if s is not None]

        bonus_applied = 0.0
        if len(deep_scores) >= 2:
            avg_deep = sum(deep_scores) / len(deep_scores)
            bonus_applied = consistency_bonus_amount(
                avg_deep, consistency_baseline, consistency_max_bonus
            )
            rating += bonus_applied

        rating = max(0, min(100, rating))

        results.append({
            "PLAYER_ID": player_id,
            "PLAYER_NAME": row["PLAYER_NAME"],
            "BRADLEY_3PT_RATING": rating,
            # Diagnostic columns -- not used by the chart itself, but
            # kept so any rating can be audited: what each season
            # actually scored, what weight it ended up getting after
            # dampening/missing-season adjustments, and how much the
            # consistency bonus added.
            "CURRENT_SEASON_SCORE": None if current_pct is None else round(current_pct * 100, 1),
            "CURRENT_SEASON_RAW_PCT": round(row["raw_pct"] * 100, 1),
            "CURRENT_SEASON_SHRUNK_PCT": round(row["shrunk_pct"] * 100, 1),
            "SEASON_MINUS_1_SCORE": None if s1 is None else round(s1 * 100, 1),
            "SEASON_MINUS_2_SCORE": None if s2 is None else round(s2 * 100, 1),
            "WEIGHT_CURRENT_USED": round(cw, 3),
            "WEIGHT_S1_USED": round(w1, 3),
            "WEIGHT_S2_USED": round(w2, 3),
            "RATING_BEFORE_BONUS": round(rating_before_bonus, 1),
            "CONSISTENCY_BONUS_APPLIED": round(bonus_applied, 2),
        })

    return pd.DataFrame(results)
