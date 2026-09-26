"""
upload_stats.py -- the "Upload Stats" page: bring your own data, get the
same analysis the dashboard runs on NBA data.

Three audiences (see the NBA Launchpad pitch):
  1. THE PLAYER -- upload your own tracked shots -> shot chart, heat map, hex
     chart, zone breakdown and a plain-English tendency read-out.
  2. THE TEAM   -- upload a season of box scores -> roster table, season trend,
     archetype radar, clutch impact clock; optionally lineups (two-man network,
     3/4/5-man shapes) and passes (passing web).
  3. THE LEAGUE -- upload every team's stats -> ranked bar chart, scatter plot,
     leaderboard and a head-to-head matchup read.

This module has two layers. Everything above the "STREAMLIT UI" banner is
plain pandas/numpy/matplotlib (no Streamlit), so parsing, column detection,
coordinate handling and every calculation can be tested directly. The UI layer
below it is a thin wrapper.

PRIVACY: uploads are processed in memory for the current session only. Nothing
here writes to disk, calls st.cache_data / st.cache_resource (which would keep
user data in server memory shared across sessions), or posts to the public
Community Uploads page -- these files can be a child's shot history.
"""
from __future__ import annotations

import io
import re
import unicodedata

import numpy as np
import pandas as pd

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_ROWS = 250_000


class UploadError(Exception):
    """A problem with the uploaded file that the person can fix; message is user-facing."""


# =============================================================================
# READING FILES
# =============================================================================
def normalize_name(s) -> str:
    """'Shot X (ft)' -> 'shot_x_ft' -- the form column headers are compared in."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def read_table(data: bytes, filename: str) -> pd.DataFrame:
    """CSV / TSV / TXT / XLSX bytes -> DataFrame, with friendly errors."""
    if not data:
        raise UploadError("That file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadError(f"That file is {len(data) / 1e6:.0f} MB -- the limit is {MAX_UPLOAD_BYTES // 1_000_000} MB.")
    name = (filename or "").lower()
    try:
        if name.endswith((".xlsx", ".xlsm", ".xls")):
            try:
                df = pd.read_excel(io.BytesIO(data))
            except ImportError:
                raise UploadError("Excel files need the 'openpyxl' package installed -- or save the sheet as CSV and upload that.")
        else:
            text = None
            for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
                try:
                    text = data.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            df = pd.read_csv(io.StringIO(text), sep=None, engine="python", skipinitialspace=True)
    except UploadError:
        raise
    except Exception as e:  # pandas' parser errors are not user-friendly
        raise UploadError(f"Couldn't read that file as a table ({type(e).__name__}). Is it a CSV or Excel sheet with a header row?")
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]
    df = df.loc[:, [c for c in df.columns if c and not c.lower().startswith("unnamed:")]]
    if df.empty or len(df.columns) < 2:
        raise UploadError("Couldn't find a table with at least two columns and one row of data. The first row should be the column names.")
    if len(df) > MAX_ROWS:
        raise UploadError(f"That file has {len(df):,} rows -- the limit is {MAX_ROWS:,}.")
    return df.reset_index(drop=True)


def auto_map(columns, aliases: dict) -> dict:
    """
    {field: column_or_None}. Exact normalized match against a field's aliases
    first (in alias priority order), then a looser "header contains alias"
    pass for anything still unmapped. A column is only ever used for one field.
    """
    norm = {c: normalize_name(c) for c in columns}
    used, mapping = set(), {}
    for field, alist in aliases.items():
        mapping[field] = None
        for alias in alist:
            hit = next((c for c, n in norm.items() if n == alias and c not in used), None)
            if hit:
                mapping[field] = hit
                used.add(hit)
                break
    for field, alist in aliases.items():
        if mapping[field] is not None:
            continue
        for alias in alist:
            if len(alias) < 4:
                continue
            hit = next((c for c, n in norm.items() if c not in used and re.search(rf"(^|_){re.escape(alias)}($|_)", n)), None)
            if hit:
                mapping[field] = hit
                used.add(hit)
                break
    return mapping


# =============================================================================
# THE PLAYER -- shot data
# =============================================================================
SHOT_ALIASES = {
    "x": ["x", "loc_x", "locx", "shot_x", "shotx", "x_coord", "x_coordinate", "court_x", "xloc", "x_loc", "xpos", "x_pos",
          "x_position", "x_ft", "x_feet", "location_x", "coord_x", "left_right"],
    "y": ["y", "loc_y", "locy", "shot_y", "shoty", "y_coord", "y_coordinate", "court_y", "yloc", "y_loc", "ypos", "y_pos",
          "y_position", "y_ft", "y_feet", "location_y", "coord_y", "distance_from_baseline"],
    "made": ["made", "make", "shot_made", "shot_made_flag", "made_flag", "result", "shot_result", "outcome", "make_miss",
             "made_missed", "is_made", "hit", "scored", "success", "shot_outcome", "fg", "fgm", "event_type", "makes"],
    "type": ["shot_type", "type", "points", "pts_type", "shot_value", "attempt_type", "is_three", "three_pointer", "three_pt", "is_3pt"],
    "zone": ["zone", "shot_zone", "shot_zone_basic", "area", "location", "court_zone", "region", "spot", "shot_location"],
    "date": ["date", "game_date", "session", "session_date", "practice_date", "day", "workout_date", "timestamp", "time"],
    "player": ["player", "player_name", "name", "shooter", "athlete", "full_name"],
    "period": ["period", "quarter", "qtr", "half"],
}

ZONE_SUMMARY_ALIASES = {
    "zone": ["zone", "shot_zone", "area", "location", "court_zone", "region", "spot", "shot_location", "zone_name"],
    "attempts": ["attempts", "fga", "att", "shots", "shots_taken", "total", "total_shots", "taken", "a"],
    "made": ["made", "fgm", "makes", "shots_made", "made_shots", "m"],
    "pct": ["fg_pct", "pct", "percentage", "percent", "fg", "accuracy", "make_pct"],
    "player": ["player", "player_name", "name", "athlete"],
    "date": ["date", "session", "session_date", "game_date"],
}

_MADE_TRUE = {"1", "1.0", "made", "make", "m", "hit", "y", "yes", "true", "t", "in", "good", "made shot", "score", "scored",
              "success", "swish", "o", "w", "+", "made_shot", "made fg", "fg made"}
_MADE_FALSE = {"0", "0.0", "miss", "missed", "x", "n", "no", "false", "f", "out", "bad", "missed shot", "brick", "fail",
               "failed", "-", "missed_shot", "missed fg", "fg missed", "off"}


def parse_made(series: pd.Series):
    """
    Any reasonable make/miss encoding -> 1 / 0 (NaN where unrecognised).
    Returns (flags, unrecognised_values). Handles 1/0, made/missed, true/false,
    yes/no, x/o, and NBA event types ("Made Shot" / "Missed Shot").
    """
    if pd.api.types.is_bool_dtype(series):
        return series.astype(float), []
    if pd.api.types.is_numeric_dtype(series):
        vals = pd.to_numeric(series, errors="coerce")
        out = pd.Series(np.where(vals.isna(), np.nan, (vals > 0).astype(float)), index=series.index)
        return out, []
    s = series.astype(str).str.strip().str.lower()
    out = pd.Series(np.nan, index=series.index, dtype=float)
    out[s.isin(_MADE_TRUE) | s.str.contains(r"\bmade\b|\bmake\b|\bmakes\b", regex=True) & ~s.str.contains("miss")] = 1.0
    out[s.isin(_MADE_FALSE) | s.str.contains("miss", regex=False)] = 0.0
    bad = sorted(set(series[out.isna() & series.notna()].astype(str)))[:8]
    return out, bad


# ---- coordinates --------------------------------------------------------------
COORD_SHORT = {"nba": "NBA units (tenths of a foot)", "hoop_ft": "feet from the hoop", "corner_ft": "feet from the court corner",
               "fraction": "0-1 fractions of the court"}
COORD_SYSTEMS = {
    "auto": "Auto-detect",
    "nba": "NBA units (tenths of a foot, hoop at 0,0) -- like LOC_X / LOC_Y",
    "hoop_ft": "Feet, hoop at 0,0 (x: left/right of the hoop, y: toward half court)",
    "corner_ft": "Feet, bottom-left corner of the half court at 0,0 (x: 0-50, y: 0-47)",
    "fraction": "0-1 fractions of the half court, bottom-left at 0,0",
}


def detect_coordinate_system(x: pd.Series, y: pd.Series):
    """(system_key, plain-English reason) from the shape of the numbers."""
    xv, yv = pd.to_numeric(x, errors="coerce").dropna(), pd.to_numeric(y, errors="coerce").dropna()
    if len(xv) < 3 or len(yv) < 3:
        return "hoop_ft", "Too few numeric coordinates to tell -- assuming feet from the hoop."
    x_lo, x_hi = np.percentile(xv, [1, 99])
    y_lo, y_hi = np.percentile(yv, [1, 99])
    if x_lo >= -0.01 and x_hi <= 1.01 and y_lo >= -0.01 and y_hi <= 1.01:
        return "fraction", "All values are between 0 and 1."
    if max(abs(x_lo), abs(x_hi)) > 60 or max(abs(y_lo), abs(y_hi)) > 60:
        return "nba", "Values run past 60, so they look like tenths of a foot (NBA shot-chart units)."
    if x_lo >= -0.5 and y_lo >= -0.5 and x_hi <= 50.5 and y_hi <= 47.5 and x_hi > 26:
        return "corner_ft", "x runs 0-50 and y runs 0-47, like feet measured from the court's corner."
    return "hoop_ft", "x is centred on zero and values are small, like feet measured from the hoop."


def to_nba_units(x: pd.Series, y: pd.Series, system: str, flip_x=False, flip_y=False):
    """Any supported coordinate system -> NBA units (tenths of a foot, hoop at 0,0, +y toward half court)."""
    xv = pd.to_numeric(x, errors="coerce").astype(float)
    yv = pd.to_numeric(y, errors="coerce").astype(float)
    if system == "nba":
        X, Y = xv, yv
    elif system == "hoop_ft":
        X, Y = xv * 10, yv * 10
    elif system == "corner_ft":
        X = (xv - 25.0) * 10
        Y = ((47.0 - yv) if flip_y else yv) * 10 - 52.5
        flip_y = False  # already applied against the court length
    elif system == "fraction":
        X = (xv - 0.5) * 500
        Y = ((1.0 - yv) if flip_y else yv) * 470 - 52.5
        flip_y = False
    else:
        raise UploadError(f"Unknown coordinate system: {system}")
    if flip_x:
        X = -X
    if flip_y:
        Y = -Y
    return X, Y


# ---- zones ----------------------------------------------------------------------
# Same court geometry as court.py: hoop at (0,0), restricted-area radius 40,
# paint |x|<=80 and y from -47.5 to 142.5, corner-3 lines at |x|=220 up to
# y=92.5, arc radius 237.5. Units are tenths of a foot.
ZONE_ORDER = [
    "Restricted Area", "Paint (Non-RA)", "Mid-Range Left", "Mid-Range Top", "Mid-Range Right",
    "Left Corner 3", "Left Wing 3", "Top of Key 3", "Right Wing 3", "Right Corner 3",
]
THREE_ZONES = {"Left Corner 3", "Left Wing 3", "Top of Key 3", "Right Wing 3", "Right Corner 3"}
# canonical zone -> (SHOT_ZONE_BASIC, SHOT_ZONE_AREA) in the NBA's own vocabulary,
# so the existing hex chart's zone labels work on uploaded data unchanged.
ZONE_TO_NBA = {
    "Restricted Area": ("Restricted Area", "Center(C)"),
    "Paint (Non-RA)": ("In The Paint (Non-RA)", "Center(C)"),
    "Mid-Range Left": ("Mid-Range", "Left Side(L)"),
    "Mid-Range Top": ("Mid-Range", "Center(C)"),
    "Mid-Range Right": ("Mid-Range", "Right Side(R)"),
    "Left Corner 3": ("Left Corner 3", "Left Side(L)"),
    "Left Wing 3": ("Above the Break 3", "Left Side Center(LC)"),
    "Top of Key 3": ("Above the Break 3", "Center(C)"),
    "Right Wing 3": ("Above the Break 3", "Right Side Center(RC)"),
    "Right Corner 3": ("Right Corner 3", "Right Side(R)"),
}
_TOP_OF_KEY_HALF_ANGLE = 25.0  # degrees either side of straight ahead


def classify_zones(X, Y) -> np.ndarray:
    """Vectorised: NBA-unit coordinates -> canonical zone name per shot ('' = off the half court)."""
    X = np.asarray(X, dtype=float)
    Y = np.asarray(Y, dtype=float)
    r = np.hypot(X, Y)
    ax = np.abs(X)
    out = np.full(X.shape, "", dtype=object)
    valid = np.isfinite(X) & np.isfinite(Y) & (Y <= 400) & (Y >= -60) & (ax <= 300)
    three = ((Y <= 92.5) & (ax >= 220)) | ((Y > 92.5) & (r >= 237.5))
    corner = three & (Y <= 92.5)
    ra = (r <= 40) & ~three
    paint = (ax <= 80) & (Y >= -47.5) & (Y <= 142.5) & ~ra & ~three
    mid = ~three & ~ra & ~paint
    theta = np.degrees(np.arctan2(X, np.where(Y == 0, 1e-9, Y)))  # 0 = straight ahead, + = right
    out[valid & ra] = "Restricted Area"
    out[valid & paint] = "Paint (Non-RA)"
    out[valid & mid & (X < -80)] = "Mid-Range Left"
    out[valid & mid & (X > 80)] = "Mid-Range Right"
    out[valid & mid & (ax <= 80)] = "Mid-Range Top"
    out[valid & corner & (X < 0)] = "Left Corner 3"
    out[valid & corner & (X >= 0)] = "Right Corner 3"
    atb = valid & three & ~corner
    out[atb & (np.abs(theta) <= _TOP_OF_KEY_HALF_ANGLE)] = "Top of Key 3"
    out[atb & (theta < -_TOP_OF_KEY_HALF_ANGLE)] = "Left Wing 3"
    out[atb & (theta > _TOP_OF_KEY_HALF_ANGLE)] = "Right Wing 3"
    return out


def build_shots_frame(df: pd.DataFrame, mapping: dict, system: str, flip_x=False, flip_y=False) -> tuple[pd.DataFrame, dict]:
    """
    Raw upload + column mapping -> a clean frame in the exact schema the NBA
    shot-chart builders expect (LOC_X, LOC_Y, SHOT_MADE_FLAG, SHOT_ZONE_BASIC,
    SHOT_ZONE_AREA, SHOT_TYPE, SHOT_DISTANCE) plus ZONE, DATE, PLAYER.
    Also returns a report dict (counts, warnings, detected system) for the UI.
    """
    for req in ("x", "y", "made"):
        if not mapping.get(req):
            raise UploadError({"x": "Pick the column that holds each shot's x position.",
                               "y": "Pick the column that holds each shot's y position.",
                               "made": "Pick the column that says whether each shot was made or missed."}[req])
    if len({mapping["x"], mapping["y"], mapping["made"]}) < 3:
        raise UploadError("x, y and made/missed each need their own column.")
    report = {"rows": len(df), "warnings": []}
    detected_reason = None
    if system == "auto":
        system, detected_reason = detect_coordinate_system(df[mapping["x"]], df[mapping["y"]])
    report["system"], report["system_reason"] = system, detected_reason

    made, bad = parse_made(df[mapping["made"]])
    if bad:
        report["warnings"].append("Couldn't read these make/miss values, so those shots were skipped: " + ", ".join(f"'{b}'" for b in bad) + ".")
    X, Y = to_nba_units(df[mapping["x"]], df[mapping["y"]], system, flip_x, flip_y)
    out = pd.DataFrame({"LOC_X": X, "LOC_Y": Y, "SHOT_MADE_FLAG": made})
    out["ZONE"] = classify_zones(out["LOC_X"], out["LOC_Y"])
    finite = out[["LOC_X", "LOC_Y", "SHOT_MADE_FLAG"]].notna().all(axis=1)
    on_court = out["ZONE"] != ""
    report["skipped_unreadable"] = int((~finite).sum())
    report["skipped_off_court"] = int((finite & ~on_court).sum())
    keep = finite & on_court
    if keep.sum() == 0:
        raise UploadError("None of the shots landed on the half court with the current coordinate settings. "
                          "Try a different coordinate system (or flip an axis) under 'Court coordinates'.")
    if report["skipped_off_court"] > 0.15 * max(len(df), 1):
        report["warnings"].append(f"{report['skipped_off_court']} shots ({report['skipped_off_court'] / len(df):.0%}) fell off the half court -- "
                                  "if that's a lot, the coordinate system is probably wrong.")
    out = out[keep].copy()
    out["LOC_X"], out["LOC_Y"] = out["LOC_X"].round(1), out["LOC_Y"].round(1)
    out["SHOT_MADE_FLAG"] = out["SHOT_MADE_FLAG"].astype(int)
    out["SHOT_ZONE_BASIC"] = out["ZONE"].map(lambda z: ZONE_TO_NBA[z][0])
    out["SHOT_ZONE_AREA"] = out["ZONE"].map(lambda z: ZONE_TO_NBA[z][1])
    out["SHOT_DISTANCE"] = (np.hypot(out["LOC_X"], out["LOC_Y"]) / 10).round().astype(int)
    out["IS_THREE"] = out["ZONE"].isin(THREE_ZONES)
    out["SHOT_TYPE"] = np.where(out["IS_THREE"], "3PT Field Goal", "2PT Field Goal")
    # keep original row order info + optional context columns
    out["PLAYER"] = df.loc[out.index, mapping["player"]].astype(str).str.strip() if mapping.get("player") else ""
    if mapping.get("date"):
        parsed = pd.to_datetime(df.loc[out.index, mapping["date"]], errors="coerce")
        out["DATE"] = parsed if parsed.notna().mean() >= 0.6 else df.loc[out.index, mapping["date"]].astype(str)
    else:
        out["DATE"] = pd.NaT
    out["SHOT_NUMBER"] = np.arange(1, len(out) + 1)
    report["kept"] = int(len(out))
    return out.reset_index(drop=True), report


# ---- zone summary (aggregated) uploads ---------------------------------------
def guess_zone(label) -> str | None:
    """Best-effort keyword match of a free-text zone label to a canonical zone (None = ask the person)."""
    t = " " + re.sub(r"[^a-z0-9]+", " ", str(label).lower()) + " "
    left = bool(re.search(r"\b(left|l|lt)\b", t))
    right = bool(re.search(r"\b(right|r|rt)\b", t))
    if "corner" in t:
        return "Right Corner 3" if right and not left else "Left Corner 3" if left else None
    is_three = bool(re.search(r"\b(3|3pt|3 pt|3 point|three|threes|arc|atb|break|wing|beyond)\b", t)) or "top of the key" in t
    if is_three:
        if "wing" in t or left or right:
            return "Right Wing 3" if right and not left else "Left Wing 3"
        return "Top of Key 3"
    if re.search(r"\b(restricted|rim|layup|layups|dunk|basket|ra)\b", t):
        return "Restricted Area"
    if re.search(r"\b(paint|lane|floater|key|post|block)\b", t):
        return "Paint (Non-RA)"
    if re.search(r"\b(mid|midrange|mid range|elbow|free throw|ft line|pullup|pull up|2pt|2 pt|two)\b", t):
        return "Mid-Range Right" if right and not left else "Mid-Range Left" if left else "Mid-Range Top"
    return None


def build_zone_table_from_summary(df: pd.DataFrame, mapping: dict, zone_choices: dict) -> pd.DataFrame:
    """Aggregated (zone, attempts, made) rows -> the standard zone table. zone_choices: raw label -> canonical zone (or None to ignore)."""
    if not mapping.get("zone"):
        raise UploadError("Pick the column that names each zone.")
    if not mapping.get("attempts") and not (mapping.get("made") and mapping.get("pct")):
        raise UploadError("Pick an 'attempts' column (or both 'made' and a percentage column).")
    d = pd.DataFrame({"raw": df[mapping["zone"]].astype(str).str.strip()})
    d["ZONE"] = d["raw"].map(zone_choices)
    d = d[d["ZONE"].notna() & (d["ZONE"] != "")]
    if mapping.get("attempts"):
        d["FGA"] = pd.to_numeric(df.loc[d.index, mapping["attempts"]], errors="coerce")
        if mapping.get("made"):
            d["FGM"] = pd.to_numeric(df.loc[d.index, mapping["made"]], errors="coerce")
        else:
            p = pd.to_numeric(df.loc[d.index, mapping["pct"]], errors="coerce")
            p = p / 100 if p.dropna().max() > 1.5 else p
            d["FGM"] = (d["FGA"] * p).round()
    else:
        d["FGM"] = pd.to_numeric(df.loc[d.index, mapping["made"]], errors="coerce")
        p = pd.to_numeric(df.loc[d.index, mapping["pct"]], errors="coerce")
        p = p / 100 if p.dropna().max() > 1.5 else p
        d["FGA"] = (d["FGM"] / p.replace(0, np.nan)).round()
    d = d.dropna(subset=["FGA", "FGM"])
    d = d[d["FGA"] > 0]
    if d.empty:
        raise UploadError("No zone rows with attempts were left after mapping. Check the zone mapping and the attempts column.")
    g = d.groupby("ZONE")[["FGA", "FGM"]].sum()
    if (g["FGM"] > g["FGA"]).any():
        bad = ", ".join(g.index[g["FGM"] > g["FGA"]])
        raise UploadError(f"More makes than attempts in: {bad}. Check that the 'made' and 'attempts' columns aren't swapped.")
    return zone_table_from_counts(g["FGA"], g["FGM"])


def zone_table_from_counts(fga: pd.Series, fgm: pd.Series) -> pd.DataFrame:
    """Zone table (every canonical zone, in court order) from per-zone attempts and makes."""
    t = pd.DataFrame(index=ZONE_ORDER)
    t["FGA"] = fga.reindex(ZONE_ORDER).fillna(0).astype(int)
    t["FGM"] = fgm.reindex(ZONE_ORDER).fillna(0).astype(int)
    total = max(int(t["FGA"].sum()), 1)
    t["FG%"] = np.where(t["FGA"] > 0, t["FGM"] / t["FGA"].where(t["FGA"] > 0, 1), np.nan)
    t["Share of shots"] = t["FGA"] / total
    pts_per_make = pd.Series([3 if z in THREE_ZONES else 2 for z in ZONE_ORDER], index=ZONE_ORDER)
    t["Points/shot"] = np.where(t["FGA"] > 0, t["FGM"] * pts_per_make / t["FGA"].where(t["FGA"] > 0, 1), np.nan)
    t["eFG%"] = np.where(t["FGA"] > 0, (t["FGM"] + 0.5 * t["FGM"] * (pts_per_make == 3)) / t["FGA"].where(t["FGA"] > 0, 1), np.nan)
    t.index.name = "Zone"
    return t


def zone_table(shots: pd.DataFrame) -> pd.DataFrame:
    g = shots.groupby("ZONE")["SHOT_MADE_FLAG"].agg(["count", "sum"])
    return zone_table_from_counts(g["count"], g["sum"])


def shooting_summary(zt: pd.DataFrame) -> dict:
    """Overall numbers and shot-diet split from a zone table."""
    fga, fgm = int(zt["FGA"].sum()), int(zt["FGM"].sum())
    three = zt.loc[[z for z in ZONE_ORDER if z in THREE_ZONES]]
    fg3a, fg3m = int(three["FGA"].sum()), int(three["FGM"].sum())
    pts = (fgm - fg3m) * 2 + fg3m * 3
    grp = {
        "At the rim": ["Restricted Area"], "Paint": ["Paint (Non-RA)"],
        "Mid-range": ["Mid-Range Left", "Mid-Range Top", "Mid-Range Right"],
        "Corner 3s": ["Left Corner 3", "Right Corner 3"], "Above-the-break 3s": ["Left Wing 3", "Top of Key 3", "Right Wing 3"],
    }
    mix = {}
    for name, zs in grp.items():
        a, m = int(zt.loc[zs, "FGA"].sum()), int(zt.loc[zs, "FGM"].sum())
        p = sum((3 if z in THREE_ZONES else 2) * int(zt.loc[z, "FGM"]) for z in zs)
        mix[name] = {"fga": a, "fgm": m, "share": a / fga if fga else 0, "fg": m / a if a else np.nan, "pps": p / a if a else np.nan}
    return {"fga": fga, "fgm": fgm, "fg": fgm / fga if fga else np.nan, "fg3a": fg3a, "fg3m": fg3m,
            "efg": (fgm + 0.5 * fg3m) / fga if fga else np.nan, "pps": pts / fga if fga else np.nan,
            "three_share": fg3a / fga if fga else 0, "mix": mix}


def tendency_insights(zt: pd.DataFrame, min_attempts: int = 10) -> list[str]:
    """Plain-English read-out of a zone table -- facts first, one hedged suggestion."""
    s = shooting_summary(zt)
    if s["fga"] == 0:
        return []
    out = []
    top = zt["FGA"].idxmax()
    out.append(f"**Most-used spot:** {top} -- {zt.loc[top, 'Share of shots']:.0%} of all shots, made {zt.loc[top, 'FG%']:.0%}.")
    ok = zt[zt["FGA"] >= min_attempts]
    if len(ok) >= 2:
        best, worst = ok["FG%"].idxmax(), ok["FG%"].idxmin()
        out.append(f"**Best zone** (at least {min_attempts} shots): {best} at {ok.loc[best, 'FG%']:.0%} ({int(ok.loc[best, 'FGM'])}/{int(ok.loc[best, 'FGA'])}).")
        if worst != best:
            out.append(f"**Toughest zone:** {worst} at {ok.loc[worst, 'FG%']:.0%} ({int(ok.loc[worst, 'FGM'])}/{int(ok.loc[worst, 'FGA'])}), "
                       f"{ok.loc[worst, 'Share of shots']:.0%} of shots.")
    elif s["fga"] < min_attempts * 2:
        out.append(f"Only {s['fga']} shots so far -- zone percentages will settle down as you add more.")
    m = s["mix"]
    mid, rim, cor, atb = m["Mid-range"], m["At the rim"], m["Corner 3s"], m["Above-the-break 3s"]
    three_a = cor["fga"] + atb["fga"]
    three_p = (cor["fgm"] + atb["fgm"]) * 3 / three_a if three_a else np.nan
    if mid["fga"] >= min_attempts and (rim["fga"] >= min_attempts or three_a >= min_attempts):
        cmp_bits = []
        if rim["fga"] >= min_attempts:
            cmp_bits.append(f"{rim['pps']:.2f} at the rim")
        if three_a >= min_attempts:
            cmp_bits.append(f"{three_p:.2f} from three")
        lower = all(mid["pps"] < v for v in ([rim["pps"]] if rim["fga"] >= min_attempts else []) + ([three_p] if three_a >= min_attempts else []))
        out.append(f"**Shot diet:** mid-range is {mid['share']:.0%} of shots and scores {mid['pps']:.2f} points per shot, vs " + " and ".join(cmp_bits)
                   + (". Swapping some mid-range attempts for rim or three-point looks is usually the quickest efficiency gain." if lower else "."))
    out.append(f"**Overall:** {s['fgm']}/{s['fga']} ({s['fg']:.1%}), {s['efg']:.1%} eFG, {s['pps']:.2f} points per shot; {s['three_share']:.0%} of attempts were threes.")
    return out


def progress_by_session(shots: pd.DataFrame) -> pd.DataFrame | None:
    """FG% / attempts per date, or None if the file has no usable dates or only one."""
    if "DATE" not in shots.columns or shots["DATE"].isna().all():
        return None
    d = shots.dropna(subset=["DATE"]).copy()
    if pd.api.types.is_datetime64_any_dtype(d["DATE"]):
        d["SESSION"] = d["DATE"].dt.normalize()
    else:
        d["SESSION"] = d["DATE"].astype(str)
    g = d.groupby("SESSION")["SHOT_MADE_FLAG"].agg(["count", "sum"]).rename(columns={"count": "FGA", "sum": "FGM"})
    if len(g) < 2:
        return None
    g["FG%"] = g["FGM"] / g["FGA"]
    return g.sort_index()


# =============================================================================
# THE TEAM -- box scores, lineups, passes
# =============================================================================
BOX_ALIASES = {
    "player": ["player", "player_name", "name", "athlete", "full_name"],
    "date": ["date", "game_date", "match_date", "session_date"],
    "game": ["game", "game_id", "game_number", "game_no", "gm", "game_num"],
    "opp": ["opp", "opponent", "vs", "opp_team", "against", "matchup"],
    "period": ["period", "quarter", "qtr", "q"],
    "min": ["min", "minutes", "mins", "mp", "time_played", "minutes_played"],
    "pts": ["pts", "points", "pt", "point"],
    "fgm": ["fgm", "fg_made", "field_goals_made", "fg"],
    "fga": ["fga", "fg_att", "fg_attempts", "field_goals_attempted"],
    "fg3m": ["fg3m", "3pm", "3p_made", "threes_made", "tpm", "three_pm", "3fgm", "fg3_made"],
    "fg3a": ["fg3a", "3pa", "3p_att", "threes_attempted", "tpa", "three_pa", "3fga", "fg3_att"],
    "ftm": ["ftm", "ft_made", "free_throws_made", "ft"],
    "fta": ["fta", "ft_att", "free_throws_attempted"],
    "oreb": ["oreb", "off_reb", "offensive_rebounds", "orb"],
    "dreb": ["dreb", "def_reb", "defensive_rebounds", "drb"],
    "reb": ["reb", "rebounds", "trb", "tot_reb", "total_rebounds"],
    "ast": ["ast", "assists", "asst"],
    "stl": ["stl", "steals", "st"],
    "blk": ["blk", "blocks", "bl"],
    "tov": ["tov", "to", "turnovers", "tovs"],
    "pf": ["pf", "fouls", "personal_fouls"],
    "pm": ["plus_minus", "pm", "plusminus"],
}
BOX_LABELS = {
    "player": "Player name", "pts": "Points", "date": "Game date", "game": "Game # / id", "opp": "Opponent", "period": "Quarter (optional)",
    "min": "Minutes", "fgm": "FG made", "fga": "FG attempted", "fg3m": "3P made", "fg3a": "3P attempted", "ftm": "FT made",
    "fta": "FT attempted", "oreb": "Off. rebounds", "dreb": "Def. rebounds", "reb": "Rebounds", "ast": "Assists", "stl": "Steals",
    "blk": "Blocks", "tov": "Turnovers", "pf": "Fouls", "pm": "Plus/minus",
}
_STAT_COL = {"pts": "PTS", "fgm": "FGM", "fga": "FGA", "fg3m": "FG3M", "fg3a": "FG3A", "ftm": "FTM", "fta": "FTA", "oreb": "OREB",
             "dreb": "DREB", "reb": "REB", "ast": "AST", "stl": "STL", "blk": "BLK", "tov": "TOV", "pf": "PF", "pm": "PLUS_MINUS",
             "min": "MIN"}
_COUNT_COLS = list(_STAT_COL.values())


def _parse_minutes(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce")

    def one(v):
        v = str(v).strip()
        m = re.match(r"^(\d+):(\d{1,2})(?::\d+)?$", v)
        if m:
            return int(m.group(1)) + int(m.group(2)) / 60
        try:
            return float(v)
        except ValueError:
            return np.nan
    return s.map(one)


def build_box_frame(df: pd.DataFrame, mapping: dict):
    """
    Raw box-score upload -> (games, periods, report).
      games   one row per player per game (quarter rows are summed up),
              columns PLAYER, GAME, GAME_IDX, LABEL, DATE + stat columns.
      periods one row per player/game/quarter (only if a quarter column exists), else None.
    """
    if not mapping.get("player"):
        raise UploadError("Pick the column that holds each player's name.")
    if not mapping.get("pts"):
        raise UploadError("Pick the points column.")
    names = df[mapping["player"]].astype(str).str.strip()
    keep = names.ne("") & names.str.lower().ne("nan")
    src = df[keep]
    d = pd.DataFrame({"PLAYER": names[keep]}, index=src.index)
    report = {"rows": len(df), "warnings": []}
    for f, col in _STAT_COL.items():
        m = mapping.get(f)
        if m:
            d[col] = _parse_minutes(src[m]) if f == "min" else pd.to_numeric(src[m], errors="coerce")
    if "REB" not in d.columns and {"OREB", "DREB"} <= set(d.columns):
        d["REB"] = d["OREB"] + d["DREB"]
    if d["PTS"].notna().sum() == 0:
        raise UploadError("The points column has no numbers in it.")

    parts, date = [], pd.Series(pd.NaT, index=d.index)
    if mapping.get("date"):
        raw = src[mapping["date"]]
        parsed = pd.to_datetime(raw, errors="coerce")
        if parsed.notna().mean() >= 0.6:
            date = parsed.dt.normalize()
            parts.append(date.astype(str))
        else:
            parts.append(raw.astype(str))
    if mapping.get("game"):
        parts.append(src[mapping["game"]].astype(str))
    if mapping.get("opp"):
        parts.append(src[mapping["opp"]].astype(str))
    d["DATE"] = date
    has_period = False
    if mapping.get("period"):
        per = pd.to_numeric(src[mapping["period"]].astype(str).str.extract(r"(\d+)")[0], errors="coerce")
        has_period = per.nunique() >= 2
    if parts:
        d["GAME"] = parts[0].str.cat(parts[1:], sep=" | ") if len(parts) > 1 else parts[0]
    elif has_period:
        raise UploadError("Quarter-by-quarter rows need a date, game or opponent column so they can be grouped into games.")
    else:
        d["GAME"] = "G" + (d.groupby("PLAYER").cumcount() + 1).astype(str)

    periods = None
    if has_period:
        p = d.copy()
        p["PERIOD"] = per
        periods = p.dropna(subset=["PERIOD"]).copy()
        periods["PERIOD"] = periods["PERIOD"].astype(int)
    agg = {c: "sum" for c in _COUNT_COLS if c in d.columns}
    grp = d.groupby(["PLAYER", "GAME"], sort=False)
    games = grp.agg({**{c: (lambda s: s.sum(min_count=1)) for c in agg}, "DATE": "first"}).reset_index()
    order = games.groupby("GAME", sort=False)["DATE"].min()
    if order.notna().any():
        rank = order.sort_values(kind="stable").index
    else:
        rank = order.index
    games["GAME_IDX"] = games["GAME"].map({g: i for i, g in enumerate(rank)})
    def label(row):
        if pd.notna(row["DATE"]):
            return row["DATE"].strftime("%b %d")
        return str(row["GAME"]).split(" | ")[0]
    games["LABEL"] = games.apply(label, axis=1)
    games = games.sort_values(["PLAYER", "GAME_IDX"]).reset_index(drop=True)
    if periods is not None:
        periods = periods.groupby(["PLAYER", "GAME", "PERIOD"], as_index=False)[[c for c in agg if c in periods.columns]].sum(min_count=1)
    report["games"] = int(games["GAME"].nunique())
    report["players"] = int(games["PLAYER"].nunique())
    return games, periods, report


def _ratio(n, d):
    return n / d.where(d > 0)


def player_table(games: pd.DataFrame, per: str = "Per Game") -> pd.DataFrame:
    """Roster table. per: 'Per Game' | 'Per 36' | 'Totals' (percentages are always computed from totals)."""
    cols = [c for c in _COUNT_COLS if c in games.columns and games[c].notna().any()]
    g = games.groupby("PLAYER")
    t = g[cols].sum(min_count=1)
    t["GP"] = g.size()
    out = pd.DataFrame(index=t.index)
    out["GP"] = t["GP"]
    has_min = "MIN" in t.columns
    if has_min:
        out["MIN"] = t["MIN"] if per == "Totals" else t["MIN"] / t["GP"]
    for c in ("PTS", "REB", "AST", "STL", "BLK", "TOV", "PF", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "OREB", "DREB", "PLUS_MINUS"):
        if c not in t.columns:
            continue
        if per == "Totals":
            out[c] = t[c]
        elif per == "Per 36" and has_min:
            out[c] = t[c] / t["MIN"].where(t["MIN"] > 0) * 36
        else:
            out[c] = t[c] / t["GP"]
    if {"FGM", "FGA"} <= set(t.columns):
        out["FG%"] = _ratio(t["FGM"], t["FGA"])
    if {"FG3M", "FG3A"} <= set(t.columns):
        out["3P%"] = _ratio(t["FG3M"], t["FG3A"])
    if {"FTM", "FTA"} <= set(t.columns):
        out["FT%"] = _ratio(t["FTM"], t["FTA"])
    if {"FGM", "FG3M", "FGA"} <= set(t.columns):
        out["eFG%"] = _ratio(t["FGM"] + 0.5 * t["FG3M"], t["FGA"])
    if {"PTS", "FGA", "FTA"} <= set(t.columns):
        out["TS%"] = _ratio(t["PTS"], 2 * (t["FGA"] + 0.44 * t["FTA"]))
    if {"AST", "TOV"} <= set(t.columns):
        out["AST/TOV"] = _ratio(t["AST"], t["TOV"])
    out.index.name = "Player"
    return out.sort_values("PTS", ascending=False) if "PTS" in out.columns else out


RADAR_LABELS = ["Scoring", "Playmaking", "Rebounding", "Defense", "Efficiency"]


def radar_percentiles(per_game: pd.DataFrame, min_games: int) -> pd.DataFrame:
    """0-100 percentile of each teammate within the roster on five archetype categories."""
    t = per_game[per_game["GP"] >= min_games]
    cats = {}
    if "PTS" in t.columns:
        cats["Scoring"] = t["PTS"]
    if "AST" in t.columns:
        cats["Playmaking"] = t["AST"]
    if "REB" in t.columns:
        cats["Rebounding"] = t["REB"]
    if {"STL", "BLK"} & set(t.columns):
        cats["Defense"] = t.get("STL", 0) + t.get("BLK", 0)
    if "TS%" in t.columns and t["TS%"].notna().any():
        cats["Efficiency"] = t["TS%"]
    elif "FG%" in t.columns:
        cats["Efficiency"] = t["FG%"]
    if len(cats) < 3 or len(t) < 3:
        raise UploadError("The radar needs at least 3 players with enough games, and at least 3 of: points, assists, rebounds, steals/blocks, shooting.")
    df = pd.DataFrame(cats).rank(pct=True) * 100
    return df.fillna(0)


TREND_STATS = {
    "Points": ("PTS", False), "Rebounds": ("REB", False), "Assists": ("AST", False), "Steals": ("STL", False),
    "Blocks": ("BLK", False), "Turnovers": ("TOV", False), "Minutes": ("MIN", False), "Plus/minus": ("PLUS_MINUS", False),
    "Field goal %": (("FGM", "FGA"), True), "3-point %": (("FG3M", "FG3A"), True), "Free throw %": (("FTM", "FTA"), True),
}


def available_trend_stats(games: pd.DataFrame) -> list[str]:
    ok = []
    for name, (col, _) in TREND_STATS.items():
        cols = col if isinstance(col, tuple) else (col,)
        if all(c in games.columns and games[c].notna().any() for c in cols):
            ok.append(name)
    return ok


def trend_series(games: pd.DataFrame, player: str, stat_name: str):
    """(x_labels, values, is_percentage) for one player's game-by-game numbers."""
    col, is_pct = TREND_STATS[stat_name]
    d = games[games["PLAYER"] == player].sort_values("GAME_IDX")
    if is_pct:
        vals = d[col[0]] / d[col[1]].where(d[col[1]] > 0)
    else:
        vals = d[col]
    ok = vals.notna()
    return d.loc[ok, "LABEL"].tolist(), vals[ok].astype(float).tolist(), is_pct


def quarter_stats(periods, player: str):
    """Per-game averages by quarter (Q1-Q4) for the impact clock, or None if there's no quarter data."""
    if periods is None:
        return None
    d = periods[periods["PLAYER"] == player]
    n_games = max(d["GAME"].nunique(), 1)
    out = []
    for q in (1, 2, 3, 4):
        dq = d[d["PERIOD"] == q]
        fga = dq["FGA"].sum() if "FGA" in dq.columns else 0
        fgm = dq["FGM"].sum() if "FGM" in dq.columns else 0
        out.append({"PTS": float(dq["PTS"].sum() / n_games), "FG_PCT": float(fgm / fga) if fga else 0.0,
                    "PLUS_MINUS": float(dq["PLUS_MINUS"].sum() / n_games) if "PLUS_MINUS" in dq.columns else 0.0})
    if all(q["PTS"] == 0 for q in out):
        return None
    return out


LINEUP_ALIASES = {
    "lineup": ["lineup", "group_name", "players", "group", "combo", "combination", "unit", "five"],
    "a": ["player_a", "player_1", "p1", "player1", "first_player"],
    "b": ["player_b", "player_2", "p2", "player2", "second_player"],
    "value": ["net_rating", "net_rtg", "netrtg", "net", "plus_minus", "pm", "plusminus", "rating"],
    "min": ["min", "minutes", "mins", "mp"],
}
_LINEUP_SPLIT = re.compile(r"\s+-\s+|\s*[;|/+&]\s*|\s*,\s*")


def parse_lineups(df: pd.DataFrame, mapping: dict, min_minutes: float = 0.0):
    """
    Lineup upload -> (two_man_lookup, groups_by_size).
    two_man_lookup: {frozenset({a, b}): value}; groups_by_size: {n: [(names_tuple, value, minutes_or_None)]} for n >= 3.
    Accepts either two player columns (pairs) or one lineup column with names separated by ' - ', ';', '|', '/', ',' or '+'.
    """
    if not mapping.get("value"):
        raise UploadError("Pick the column with each lineup's net rating (or plus/minus).")
    if not mapping.get("lineup") and not (mapping.get("a") and mapping.get("b")):
        raise UploadError("Pick either a lineup column (names separated by ' - ') or two player columns.")
    val = pd.to_numeric(df[mapping["value"]], errors="coerce")
    mins = pd.to_numeric(df[mapping["min"]], errors="coerce") if mapping.get("min") else pd.Series(np.inf, index=df.index)
    two, groups = {}, {}
    for i in df.index:
        if pd.isna(val[i]) or (mapping.get("min") and not mins[i] >= min_minutes):
            continue
        if mapping.get("lineup"):
            names = tuple(n.strip() for n in _LINEUP_SPLIT.split(str(df.at[i, mapping["lineup"]])) if n.strip())
        else:
            names = (str(df.at[i, mapping["a"]]).strip(), str(df.at[i, mapping["b"]]).strip())
        if len(set(names)) != len(names) or len(names) < 2:
            continue
        if len(names) == 2:
            two[frozenset(names)] = float(val[i])
        else:
            groups.setdefault(len(names), []).append((names, float(val[i]), float(mins[i]) if mapping.get("min") and pd.notna(mins[i]) else None))
    return two, groups


PASS_ALIASES = {
    "passer": ["passer", "from", "from_player", "passer_name", "player"],
    "receiver": ["receiver", "to", "to_player", "teammate", "receiver_name", "pass_to"],
    "passes": ["passes", "pass", "count", "passes_made", "n", "total"],
    "fgm": ["fgm", "made", "shots_made", "fg_made"],
    "fga": ["fga", "attempts", "shots", "fg_att"],
    "fg3a": ["fg3a", "3pa", "threes_attempted"],
}


def parse_passes(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    for req, msg in (("passer", "passer"), ("receiver", "receiver"), ("passes", "number of passes")):
        if not mapping.get(req):
            raise UploadError(f"Pick the {msg} column.")
    d = pd.DataFrame({"PASSER": df[mapping["passer"]].astype(str).str.strip(), "RECEIVER": df[mapping["receiver"]].astype(str).str.strip(),
                      "PASSES": pd.to_numeric(df[mapping["passes"]], errors="coerce")})
    for f, c in (("fgm", "FGM"), ("fga", "FGA"), ("fg3a", "FG3A")):
        d[c] = pd.to_numeric(df[mapping[f]], errors="coerce") if mapping.get(f) else 0
    d = d.dropna(subset=["PASSES"])
    d = d[(d["PASSER"] != d["RECEIVER"]) & (d["PASSES"] > 0)]
    if d.empty:
        raise UploadError("No passer-to-teammate rows with a positive pass count were found.")
    return d.groupby(["PASSER", "RECEIVER"], as_index=False).sum(numeric_only=True)


# =============================================================================
# THE LEAGUE -- one row per team (or per game)
# =============================================================================
_LOWER_BETTER = re.compile(r"(^|_)(tov|to|turnovers?|pf|fouls?|opp|allowed|against|pa|drtg|def_rating|losses|l)($|_)")


def lower_is_better(col: str) -> bool:
    return bool(_LOWER_BETTER.search(normalize_name(col)))


def guess_team_column(df: pd.DataFrame) -> str:
    for c in df.columns:
        if normalize_name(c) in ("team", "team_name", "squad", "club", "school", "name"):
            return c
    for c in df.columns:
        if pd.to_numeric(df[c], errors="coerce").notna().mean() < 0.5:
            return c
    return df.columns[0]


def league_table(df: pd.DataFrame, team_col: str, mode: str = "auto"):
    """
    -> (table, mode_used). One row per team, numeric stat columns only. mode 'teams' = the file already has one row per
    team; 'games' = one row per game, averaged per team; 'auto' picks by whether a team name repeats.
    """
    if team_col not in df.columns:
        raise UploadError("Pick the column that names each team.")
    d = df.copy()
    teams = d[team_col].astype(str).str.strip()
    num = [c for c in d.columns if c != team_col and pd.to_numeric(d[c], errors="coerce").notna().mean() >= 0.8]
    if not num:
        raise UploadError("No numeric stat columns were found. Every column besides the team name should be a number.")
    for c in num:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["_team"] = teams
    if mode == "auto":
        mode = "games" if teams.duplicated().any() else "teams"
    if mode == "games":
        t = d.groupby("_team", sort=False)[num].mean()
        t.insert(0, "Games", d.groupby("_team", sort=False).size())
    else:
        t = d.drop_duplicates("_team").set_index("_team")[num]
    t.index.name = "Team"
    if len(t) < 2:
        raise UploadError("A league needs at least two teams.")
    cols = {normalize_name(c): c for c in t.columns}
    def find(*names):
        return next((cols[n] for n in names if n in cols), None)
    pts, fga, fta, fgm, fg3m = find("pts", "points", "pf_pts", "ppg"), find("fga"), find("fta"), find("fgm"), find("fg3m", "3pm")
    opp = find("opp_pts", "pts_allowed", "pa", "pts_against", "opp_points", "points_allowed")
    if pts and fga and fta and "TS%" not in t.columns:
        t["TS%"] = t[pts] / (2 * (t[fga] + 0.44 * t[fta])).where(t[fga] > 0)
    if fgm and fg3m and fga and "eFG%" not in t.columns:
        t["eFG%"] = (t[fgm] + 0.5 * t[fg3m]) / t[fga].where(t[fga] > 0)
    if pts and opp and "Net points" not in t.columns:
        t["Net points"] = t[pts] - t[opp]
    return t, mode


def is_fraction_column(s: pd.Series) -> bool:
    v = s.dropna()
    return len(v) > 0 and v.min() >= 0 and v.max() <= 1.0


def format_stat(col: str, value) -> str:
    if pd.isna(value):
        return "-"
    return f"{value:.1%}" if is_fraction_column(pd.Series([value])) and ("%" in col or "pct" in col.lower()) else f"{value:,.1f}" if abs(value) < 1000 else f"{value:,.0f}"


def matchup_read(t: pd.DataFrame, a: str, b: str):
    """Side-by-side stat comparison of two teams with the edge measured in league standard deviations."""
    if a == b:
        raise UploadError("Pick two different teams.")
    z = (t - t.mean()) / t.std(ddof=0).replace(0, np.nan)
    rows = []
    for c in t.columns:
        if c == "Games" or pd.isna(t.loc[a, c]) or pd.isna(t.loc[b, c]):
            continue
        sign = -1 if lower_is_better(c) else 1
        edge = sign * (z.loc[a, c] - z.loc[b, c]) if pd.notna(z.loc[a, c]) and pd.notna(z.loc[b, c]) else 0.0
        rows.append({"Stat": c, a: t.loc[a, c], b: t.loc[b, c], "_edge": edge})
    df = pd.DataFrame(rows)
    df["Edge"] = np.where(df["_edge"] > 0.25, a, np.where(df["_edge"] < -0.25, b, "Even"))
    return df.sort_values("_edge", ascending=False).reset_index(drop=True)


# =============================================================================
# CHART BUILDERS (matplotlib, transparent background like the rest of the app)
# =============================================================================
def _base_axes(width, height):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(colors="white")
    return fig, ax


def build_upload_zone_map(zt: pd.DataFrame, width=6, height=5):
    """Half court with every zone shaded by its FG% (same geometry the shots were classified with)."""
    import matplotlib.pyplot as plt
    import matplotlib.patheffects as pe
    from matplotlib.colors import Normalize
    from court import new_court_figure, draw_court
    fig, ax = new_court_figure(width=width, height=height)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    step = 2.0
    xe, ye = np.arange(-250, 250 + step, step), np.arange(-47.5, 350 + step, step)
    xc, yc = (xe[:-1] + xe[1:]) / 2, (ye[:-1] + ye[1:]) / 2
    XX, YY = np.meshgrid(xc, yc)
    Z = classify_zones(XX.ravel(), YY.ravel()).reshape(XX.shape)
    val = np.full(Z.shape, np.nan)
    for z in ZONE_ORDER:
        if zt.loc[z, "FGA"] > 0:
            val[Z == z] = zt.loc[z, "FG%"]
    played = zt.loc[zt["FGA"] > 0, "FG%"]
    lo = max(0.0, float(played.min()) - 0.05) if len(played) else 0.2
    hi = min(1.0, float(played.max()) + 0.05) if len(played) else 0.6
    if hi - lo < 0.15:
        lo, hi = max(0, lo - 0.05), hi + 0.05
    ax.pcolormesh(xe, ye, np.ma.masked_invalid(val), cmap=plt.cm.RdYlGn, norm=Normalize(lo, hi), alpha=0.8, zorder=0, shading="flat")
    empty = np.where(np.isnan(val) & (Z != ""), 1.0, np.nan)
    ax.pcolormesh(xe, ye, np.ma.masked_invalid(empty), cmap="gray", vmin=0, vmax=8, alpha=0.35, zorder=0, shading="flat")
    draw_court(ax, color="white", lw=1.4)
    for z in ZONE_ORDER:
        mask = Z == z
        if not mask.any():
            continue
        cx, cy = float(XX[mask].mean()), float(YY[mask].mean())
        r = zt.loc[z]
        txt = f"{int(r['FGM'])}/{int(r['FGA'])}\n{r['FG%']:.0%}" if r["FGA"] > 0 else "-"
        t = ax.text(cx, cy, txt, ha="center", va="center", color="white", fontsize=7.5, fontweight="bold", zorder=6)
        t.set_path_effects([pe.withStroke(linewidth=2.2, foreground="#0d0d0d")])
    return fig


def build_progress_chart(prog: pd.DataFrame, color, width=9, height=4.5):
    """FG% by session with attempts noted, plus the overall average as a reference line."""
    fig, ax = _base_axes(width, height)
    x = np.arange(len(prog))
    ax.plot(x, prog["FG%"].values, color=color, linewidth=2.2, marker="o", markersize=6, zorder=3)
    overall = prog["FGM"].sum() / prog["FGA"].sum()
    ax.axhline(overall, color="white", linestyle="--", linewidth=1, alpha=0.6, zorder=1)
    ax.text(len(prog) - 0.5, overall, f" overall {overall:.0%}", color="white", va="bottom", ha="right", fontsize=9, alpha=0.8)
    for xi, (fg, n) in enumerate(zip(prog["FG%"].values, prog["FGA"].values)):
        ax.annotate(f"{fg:.0%}\n({int(n)} shots)", (xi, fg), textcoords="offset points", xytext=(0, 9), ha="center", color="white", fontsize=8)
    labels = [ts.strftime("%b %d") if hasattr(ts, "strftime") else str(ts) for ts in prog.index]
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=35, ha="right", color="white", fontsize=9)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_ylim(max(0, prog["FG%"].min() - 0.12), min(1, prog["FG%"].max() + 0.14))
    ax.set_ylabel("Field goal % by session", color="white", fontsize=11, fontweight="bold")
    ax.margins(x=0.06)
    fig.tight_layout()
    return fig


def build_rank_bar(names, values, highlight, color, ylabel, fmt, horizontal=None, width=9, height=6):
    """Bars for any ranked list (highlighted names in the chosen color, everyone else neutral gray)."""
    n = len(names)
    horizontal = (n > 14) if horizontal is None else horizontal
    fig, ax = _base_axes(width, max(height, 0.32 * n + 1.5) if horizontal else height)
    colors = [color if nm in highlight else "#B5B5B5" for nm in names]
    idx = np.arange(n)
    hi = max(max(values), 0) if len(values) else 1
    lo = min(min(values), 0)
    span = (hi - lo) or 1
    if horizontal:
        ax.barh(idx, values, color=colors, height=0.72)
        ax.set_yticks(idx)
        ax.set_yticklabels(names, color="white", fontsize=9)
        ax.invert_yaxis()
        for i, v in enumerate(values):
            ax.text(v + span * 0.01 if v >= 0 else v - span * 0.01, i, fmt(v), va="center", ha="left" if v >= 0 else "right", color="white", fontsize=9, fontweight="bold")
        ax.set_xlabel(ylabel, color="white", fontsize=11, fontweight="bold")
        ax.set_xlim(lo - span * 0.03 if lo < 0 else 0, hi + span * 0.12)
    else:
        ax.bar(idx, values, color=colors, width=0.72)
        ax.set_xticks(idx)
        ax.set_xticklabels(names, rotation=30, ha="right", color="white", fontsize=9)
        for i, v in enumerate(values):
            ax.text(i, v + span * 0.015 if v >= 0 else v - span * 0.015, fmt(v), ha="center", va="bottom" if v >= 0 else "top", color="white", fontsize=9, fontweight="bold")
        ax.set_ylabel(ylabel, color="white", fontsize=11, fontweight="bold")
        ax.set_ylim(lo - span * 0.08 if lo < 0 else 0, hi + span * 0.12)
    fig.tight_layout()
    return fig


def build_team_scatter(t: pd.DataFrame, xcol: str, ycol: str, highlight, color, width=9, height=6.5):
    """Every team as a labeled dot, dashed lines at the league average of each axis."""
    fig, ax = _base_axes(width, height)
    d = t[[xcol, ycol]].dropna()
    hl = d.index.isin(list(highlight))
    ax.scatter(d.loc[~hl, xcol], d.loc[~hl, ycol], s=55, color="#B5B5B5", zorder=3)
    if hl.any():
        ax.scatter(d.loc[hl, xcol], d.loc[hl, ycol], s=110, color=color, edgecolor="white", linewidth=1.2, zorder=4)
    for name, r in d.iterrows():
        ax.annotate(str(name), (r[xcol], r[ycol]), textcoords="offset points", xytext=(6, 6), color="white", fontsize=8.5,
                    fontweight="bold" if name in highlight else "normal")
    ax.axvline(d[xcol].mean(), color="white", linestyle="--", linewidth=0.8, alpha=0.4)
    ax.axhline(d[ycol].mean(), color="white", linestyle="--", linewidth=0.8, alpha=0.4)
    ax.set_xlabel(xcol, color="white", fontsize=11, fontweight="bold")
    ax.set_ylabel(ycol, color="white", fontsize=11, fontweight="bold")
    if is_fraction_column(d[xcol]) and "%" in xcol:
        ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    if is_fraction_column(d[ycol]) and "%" in ycol:
        ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    fig.tight_layout()
    return fig


def baseline_comparison_frame(shots: pd.DataFrame, fg_pct: float, copies: int = 100) -> pd.DataFrame:
    """
    A stand-in 'league' for the hex chart when the person wants each area compared with their OWN overall FG%: the
    same shot locations repeated `copies` times with makes set to exactly that percentage, so every hex and every
    zone label's comparison number comes out as their average.
    """
    base = shots[["LOC_X", "LOC_Y", "SHOT_ZONE_BASIC", "SHOT_ZONE_AREA"]]
    rep = pd.concat([base] * copies, ignore_index=True)
    made = np.zeros(len(rep), dtype=int)
    made[: int(round(fg_pct * len(rep)))] = 1
    # spread makes evenly through the frame so every hex sees ~the same rate
    rng = np.random.default_rng(0)
    rng.shuffle(made)
    rep["SHOT_MADE_FLAG"] = made
    return rep


# =============================================================================
# SAMPLE DATA + TEMPLATES (so anyone can try every screen without their own files)
# =============================================================================
_SAMPLE_ZONE_RATES = {  # zone: (share of shots, base FG%)
    "Restricted Area": (0.16, 0.56), "Paint (Non-RA)": (0.10, 0.36), "Mid-Range Left": (0.08, 0.30), "Mid-Range Top": (0.11, 0.26),
    "Mid-Range Right": (0.08, 0.32), "Left Corner 3": (0.06, 0.29), "Left Wing 3": (0.10, 0.23), "Top of Key 3": (0.12, 0.27),
    "Right Wing 3": (0.10, 0.21), "Right Corner 3": (0.09 - 0.0, 0.31),
}


def sample_player_shots(n_sessions: int = 8, shots_per_session: int = 40, seed: int = 7) -> pd.DataFrame:
    """A made-up young shooter: shot locations in feet from the hoop, one row per shot, improving slowly over sessions."""
    rng = np.random.default_rng(seed)
    zones = list(_SAMPLE_ZONE_RATES)
    weights = np.array([_SAMPLE_ZONE_RATES[z][0] for z in zones])
    weights = weights / weights.sum()
    rows = []
    for s in range(n_sessions):
        date = pd.Timestamp("2026-08-03") + pd.Timedelta(days=4 * s)
        for z in rng.choice(zones, size=shots_per_session, p=weights):
            while True:
                x, y = rng.uniform(-250, 250), rng.uniform(-40, 340)
                if classify_zones([x], [y])[0] == z:
                    break
            p = min(0.9, _SAMPLE_ZONE_RATES[z][1] + 0.012 * s)
            rows.append({"date": date.strftime("%Y-%m-%d"), "player": "Sample Player", "x_ft": round(x / 10, 1), "y_ft": round(y / 10, 1),
                         "result": "made" if rng.random() < p else "missed"})
    return pd.DataFrame(rows)


def sample_zone_summary(seed: int = 7) -> pd.DataFrame:
    labels = {"Restricted Area": "At the rim", "Paint (Non-RA)": "In the paint", "Mid-Range Left": "Mid-range left", "Mid-Range Top": "Mid-range top",
              "Mid-Range Right": "Mid-range right", "Left Corner 3": "Left corner 3", "Left Wing 3": "Left wing 3", "Top of Key 3": "Top of the key 3",
              "Right Wing 3": "Right wing 3", "Right Corner 3": "Right corner 3"}
    shots = sample_player_shots(seed=seed)
    sh, _ = build_shots_frame(shots, {"x": "x_ft", "y": "y_ft", "made": "result", "player": None, "date": None, "type": None, "zone": None, "period": None}, "hoop_ft")
    g = sh.groupby("ZONE")["SHOT_MADE_FLAG"].agg(["count", "sum"])
    return pd.DataFrame({"Zone": [labels[z] for z in g.index], "Attempts": g["count"].values, "Made": g["sum"].values})


SAMPLE_PLAYERS = ["Maya Thompson", "Jordan Reyes", "Ava Kim", "Noah Patel", "Liam O'Connor", "Sofia Alvarez", "Ethan Brooks", "Zoe Carter", "Isaiah Moore"]
SAMPLE_OPPONENTS = ["Hawks", "Lions", "Wolves", "Storm", "Comets", "Rams", "Bears", "Falcons", "Titans", "Jets", "Knights", "Eagles", "Pirates", "Wildcats"]


def sample_box_scores(seed: int = 11) -> pd.DataFrame:
    """9 players x 14 games x 4 quarters of made-up box-score rows (quarter rows unlock the impact clock)."""
    rng = np.random.default_rng(seed)
    skill = {p: dict(usg=u, fg=f, three=t, reb=r, ast=a, stl=s, blk=b) for p, (u, f, t, r, a, s, b) in zip(SAMPLE_PLAYERS, [
        (1.9, .46, .35, 1.6, 1.4, .5, .1), (1.5, .42, .30, 2.3, 1.0, .4, .4), (1.2, .40, .33, 1.0, 1.9, .9, .1), (1.1, .48, .10, 3.0, .5, .3, .9),
        (1.0, .39, .28, 1.7, .8, .6, .2), (.9, .41, .32, 1.1, 1.1, .7, .1), (.8, .44, .15, 2.4, .5, .3, .5), (.7, .37, .27, .9, 1.2, .8, .1), (.6, .35, .20, 1.3, .6, .4, .2)])}
    rows = []
    for g in range(14):
        date = (pd.Timestamp("2026-01-10") + pd.Timedelta(days=7 * g)).strftime("%Y-%m-%d")
        for i, p in enumerate(SAMPLE_PLAYERS):
            if rng.random() < 0.06:
                continue
            k = skill[p]
            mins_q = [max(0, rng.normal(9 - 0.5 * i / 2, 1.2)) for _ in range(4)]
            for q, m in enumerate(mins_q, start=1):
                fga = rng.poisson(k["usg"] * m / 4 * 0.55)
                fg3a = rng.binomial(fga, min(0.8, max(0.02, k["three"] * 1.3)))
                fg3m = rng.binomial(fg3a, min(0.6, k["three"]))
                fg2m = rng.binomial(fga - fg3a, min(0.8, k["fg"] + 0.05))
                fta = rng.poisson(0.15 * k["usg"] * m / 4)
                ftm = rng.binomial(fta, 0.62)
                rows.append({"date": date, "opponent": SAMPLE_OPPONENTS[g], "player": p, "quarter": q, "min": round(m, 1),
                             "pts": 2 * fg2m + 3 * fg3m + ftm, "fgm": fg2m + fg3m, "fga": fga, "fg3m": fg3m, "fg3a": fg3a, "ftm": ftm, "fta": fta,
                             "reb": rng.poisson(k["reb"] * m / 8), "ast": rng.poisson(k["ast"] * m / 8), "stl": rng.poisson(k["stl"] * m / 8),
                             "blk": rng.poisson(k["blk"] * m / 8), "tov": rng.poisson(0.5 * k["usg"] * m / 8), "plus_minus": int(rng.normal(0.4 * (2 - i / 3), 3))})
    return pd.DataFrame(rows)


def sample_lineups(seed: int = 5) -> pd.DataFrame:
    import itertools
    rng = np.random.default_rng(seed)
    quality = {p: q for p, q in zip(SAMPLE_PLAYERS, [6, 4, 5, 2, 0, 1, 1, -2, -3])}
    rows = []
    for size, n_keep in ((2, 30), (3, 14), (4, 10), (5, 8)):
        combos = list(itertools.combinations(SAMPLE_PLAYERS, size))
        for idx in rng.choice(len(combos), size=min(n_keep, len(combos)), replace=False):
            c = combos[idx]
            rows.append({"lineup": " - ".join(c), "min": round(float(rng.uniform(12, 160) / (size - 1)), 1),
                         "net_rating": round(sum(quality[p] for p in c) / size * 2.2 + float(rng.normal(0, 4)), 1)})
    return pd.DataFrame(rows)


def sample_passes(seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for passer in SAMPLE_PLAYERS[:3]:
        for r in [p for p in SAMPLE_PLAYERS if p != passer][:6]:
            n = int(rng.integers(20, 120))
            fga = int(n * rng.uniform(0.3, 0.55))
            rows.append({"passer": passer, "receiver": r, "passes": n, "fgm": int(fga * rng.uniform(0.3, 0.55)), "fga": fga, "fg3a": int(fga * rng.uniform(0.1, 0.4))})
    return pd.DataFrame(rows)


def sample_league(seed: int = 9) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    names = ["Hawks", "Lions", "Wolves", "Storm", "Comets", "Rams", "Bears", "Falcons", "Titans", "Jets"]
    rows = []
    for nm in names:
        gp = 14
        fga = rng.uniform(48, 60); fgm = fga * rng.uniform(.34, .44); fg3a = fga * rng.uniform(.2, .4); fg3m = fg3a * rng.uniform(.2, .33)
        fta = rng.uniform(10, 18); ftm = fta * rng.uniform(.5, .7); pts = 2 * (fgm - fg3m) + 3 * fg3m + ftm
        w = int(rng.integers(3, 12))
        rows.append({"team": nm, "gp": gp, "w": w, "l": gp - w, "pts": round(pts, 1), "opp_pts": round(pts + rng.normal(0, 6), 1), "fgm": round(fgm, 1),
                     "fga": round(fga, 1), "fg3m": round(fg3m, 1), "fg3a": round(fg3a, 1), "ftm": round(ftm, 1), "fta": round(fta, 1),
                     "reb": round(rng.uniform(24, 36), 1), "ast": round(rng.uniform(8, 16), 1), "stl": round(rng.uniform(4, 10), 1),
                     "blk": round(rng.uniform(1, 5), 1), "tov": round(rng.uniform(11, 20), 1)})
    return pd.DataFrame(rows)


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


TEMPLATES = {
    "player_shots": "date,player,x_ft,y_ft,result\n2026-08-03,Your Name,0.5,3.0,made\n2026-08-03,Your Name,-22.0,4.5,missed\n2026-08-03,Your Name,8.0,22.0,made\n",
    "player_zones": "zone,attempts,made\nAt the rim,20,11\nIn the paint,12,4\nLeft corner 3,8,2\nTop of the key 3,15,4\n",
    "team_box": "date,opponent,player,min,pts,fgm,fga,fg3m,fg3a,ftm,fta,reb,ast,stl,blk,tov,plus_minus\n2026-01-10,Hawks,Player One,24,12,5,11,1,4,1,2,4,3,1,0,2,4\n2026-01-10,Hawks,Player Two,20,8,3,9,0,3,2,4,6,1,0,1,1,-2\n",
    "team_lineups": "lineup,min,net_rating\nPlayer One - Player Two,42,6.5\nPlayer One - Player Two - Player Three,18,3.1\n",
    "team_passes": "passer,receiver,passes,fgm,fga,fg3a\nPlayer One,Player Two,48,12,26,8\nPlayer One,Player Three,35,9,20,3\n",
    "league": "team,gp,w,l,pts,opp_pts,fgm,fga,fg3m,fg3a,ftm,fta,reb,ast,stl,blk,tov\nHawks,14,9,5,52.1,45.0,19.2,50.1,4.1,14.0,9.6,14.2,31.0,12.0,7.0,2.0,15.0\nLions,14,6,8,44.3,47.2,16.0,48.9,3.0,12.5,9.3,13.0,29.5,9.0,5.5,3.1,17.0\n",
}


# =============================================================================
# STREAMLIT UI  (everything below needs Streamlit; everything above does not)
# =============================================================================
import hashlib

_AUDIENCES = ["The Player", "The Team", "The League"]


def _sig(*parts) -> str:
    return hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()[:12]


def _df_sig(df: pd.DataFrame) -> str:
    return hashlib.md5(pd.util.hash_pandas_object(df, index=True).values.tobytes()).hexdigest()[:12]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "chart"


def _cached(st, name, sig, builder):
    """
    Per-SESSION memo (st.session_state, not st.cache_*, so one person's upload can never be served to another).
    Streamlit reruns the script on every click; without this every download/Tableau click would redraw every chart.
    """
    import matplotlib.pyplot as plt
    cache = st.session_state.setdefault("_up_cache", {})
    key = (name, sig)
    if key not in cache:
        while len(cache) >= 16:
            old = cache.pop(next(iter(cache)))
            if hasattr(old, "savefig"):
                plt.close(old)
        cache[key] = builder()
    return cache[key]


def _png_bytes(fig, black_text: bool) -> bytes:
    """PNG for download: an opaque background so the (white or black) text is readable in any viewer."""
    alpha, face = fig.patch.get_alpha(), fig.patch.get_facecolor()
    fig.patch.set_alpha(1)
    fig.patch.set_facecolor("#FFFFFF" if black_text else "#0d0d0d")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    fig.patch.set_alpha(0 if alpha is None else alpha)
    fig.patch.set_facecolor(face)
    return buf.getvalue()


def _show(st, h, fig, title, key, sig):
    st.pyplot(fig)
    black = st.session_state.get("_global_chart_text_color") == "black"
    png = _cached(st, f"png_{key}", _sig(sig, black), lambda: _png_bytes(fig, black))
    c1, c2 = st.columns(2)
    c1.download_button("Download PNG", png, file_name=f"{_slug(title)}.png", mime="image/png", key=f"up_dl_{key}", use_container_width=True)
    with c2:
        h.tableau(fig, title, f"up_tab_{key}")


def _get_input(st, k, label, sample_fn, sample_name, template_name, template_text, help_text=None):
    """File uploader + 'use sample data' + blank template. Returns (bytes, filename) or (None, None)."""
    flag = f"up_sample_{k}"
    up = st.file_uploader(label, type=["csv", "tsv", "txt", "xlsx"], key=f"up_file_{k}", help=help_text)
    c1, c2 = st.columns(2)
    if c1.button("Use sample data", key=f"up_sample_btn_{k}", use_container_width=True):
        st.session_state[flag] = True
    c2.download_button("Download a blank template", template_text, file_name=template_name, mime="text/csv", key=f"up_tpl_{k}", use_container_width=True)
    if up is not None:
        st.session_state[flag] = False
        return up.getvalue(), up.name
    if st.session_state.get(flag):
        bkey = f"up_sample_bytes_{k}"
        if bkey not in st.session_state:
            st.session_state[bkey] = to_csv_bytes(sample_fn())
        st.caption("Showing made-up sample data. Upload your own file above to replace it.")
        return st.session_state[bkey], sample_name
    return None, None


def _read(st, data, fname):
    try:
        return read_table(data, fname)
    except UploadError as e:
        st.error(str(e))
        return None


def _mapping_ui(st, df, aliases, labels, required, prefix):
    """Auto-detected column mapping the person can override. Opens itself when a required column wasn't found."""
    auto = auto_map(df.columns, {f: aliases[f] for f in labels})
    sig = _sig(*df.columns)
    opts = ["(none)"] + list(df.columns)
    mapping = {f: None for f in aliases}
    with st.expander("Column mapping (detected automatically -- change anything that's wrong)", expanded=not all(auto.get(r) for r in required)):
        cols = st.columns(2)
        for i, (field, label) in enumerate(labels.items()):
            default = auto.get(field)
            choice = cols[i % 2].selectbox(label + (" *" if field in required else ""), opts, index=opts.index(default) if default in opts else 0,
                                           key=f"{prefix}_map_{field}_{sig}")
            mapping[field] = None if choice == "(none)" else choice
    return mapping


def _pct_display(df: pd.DataFrame, pct_cols) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if c in pct_cols:
            out[c] = out[c].map(lambda v: "-" if pd.isna(v) else f"{v:.1%}")
        elif pd.api.types.is_float_dtype(out[c]):
            out[c] = out[c].map(lambda v: "-" if pd.isna(v) else f"{v:,.1f}")
    return out


def _color(st, h, key):
    raw = h.color_picker(key)
    return h.resolve_color(raw or "Gold")


# ------------------------------------------------------------------ THE PLAYER
def _player_tab(st, h):
    import visuals
    kind = st.radio("What does your file contain?", ["Every shot's location", "Totals for each zone"], horizontal=True, key="up_pl_kind")
    if kind == "Every shot's location":
        data, fname = _get_input(st, "pl_shots", "Upload shot data (CSV or Excel)", sample_player_shots, "sample_shots.csv", "shots_template.csv",
                                 TEMPLATES["player_shots"], "One row per shot: where it was taken (x, y) and whether it went in.")
    else:
        data, fname = _get_input(st, "pl_zones", "Upload zone totals (CSV or Excel)", sample_zone_summary, "sample_zones.csv", "zones_template.csv",
                                 TEMPLATES["player_zones"], "One row per zone: how many shots you took there and how many you made.")
    if data is None:
        st.caption("Upload a file, or try the sample data, to see your shot chart, heat map, zone breakdown and a plain-English read of your tendencies.")
        return
    df = _read(st, data, fname)
    if df is None:
        return
    with st.expander("Preview your file"):
        st.dataframe(df.head(15))

    subject = "Uploaded player"
    if kind == "Every shot's location":
        labels = {"x": "x (left / right)", "y": "y (toward the basket)", "made": "Made / missed", "player": "Player (optional)", "date": "Date or session (optional)"}
        mapping = _mapping_ui(st, df, SHOT_ALIASES, labels, ("x", "y", "made"), "up_pl")
        work = df
        if mapping["player"]:
            names = sorted(df[mapping["player"]].dropna().astype(str).str.strip().unique())
            if len(names) > 1:
                subject = st.selectbox("Player in this file:", names, key=f"up_pl_who_{_sig(*df.columns)}")
                work = df[df[mapping["player"]].astype(str).str.strip() == subject]
            elif names:
                subject = names[0]
        with st.expander("Court coordinates"):
            system = st.selectbox("Coordinate system:", list(COORD_SYSTEMS), format_func=lambda k: COORD_SYSTEMS[k], key="up_pl_sys")
            fx = st.checkbox("Flip left / right", key="up_pl_fx")
            fy = st.checkbox("Flip toward / away from the basket", key="up_pl_fy")
        try:
            shots, rep = build_shots_frame(work, mapping, system, fx, fy)
        except UploadError as e:
            st.error(str(e))
            return
        note = f"Read {rep['kept']} shots."
        if rep.get("system_reason"):
            note += f" Coordinates look like {COORD_SHORT[rep['system']]}: {rep['system_reason'][0].lower() + rep['system_reason'][1:]}"
        st.caption(note)
        for w in rep["warnings"]:
            st.warning(w)
        zt = zone_table(shots)
    else:
        labels = {"zone": "Zone name", "attempts": "Attempts", "made": "Made", "pct": "FG % (if no 'made' column)"}
        mapping = _mapping_ui(st, df, ZONE_SUMMARY_ALIASES, labels, ("zone",), "up_zn")
        shots = None
        zone_choices = {}
        if mapping["zone"]:
            with st.expander("Match your zone names to court zones", expanded=True):
                cols = st.columns(2)
                for i, lab in enumerate(df[mapping["zone"]].dropna().astype(str).str.strip().unique()):
                    g = guess_zone(lab)
                    ch = cols[i % 2].selectbox(f"'{lab}' is...", ["(ignore this row)"] + ZONE_ORDER, index=ZONE_ORDER.index(g) + 1 if g else 0,
                                               key=f"up_zn_choice_{_sig(lab, *df.columns)}")
                    zone_choices[lab] = None if ch.startswith("(") else ch
        try:
            zt = build_zone_table_from_summary(df, mapping, zone_choices)
        except UploadError as e:
            st.error(str(e))
            return

    color = _color(st, h, "up_pl_color")
    compare, season = "Your own overall FG%", None
    if shots is not None:
        compare = st.radio("Hex chart compares each area with:", ["Your own overall FG%", "NBA league average"], horizontal=True, key="up_pl_cmp")
        if compare == "NBA league average":
            season = st.selectbox("NBA season:", h.seasons, key="up_pl_season")
    if not h.run_button(True, "upload_player"):
        return

    summ = shooting_summary(zt)
    tcolor = st.session_state.get("_global_chart_text_color", "white")
    sig = _sig(_df_sig(shots) if shots is not None else zt.to_csv(), color, tcolor, subject, compare, season)
    m = st.columns(4)
    m[0].metric("Shots", f"{summ['fga']:,}")
    m[1].metric("Field goal %", f"{summ['fg']:.1%}")
    m[2].metric("Effective FG %", f"{summ['efg']:.1%}")
    m[3].metric("Points per shot", f"{summ['pps']:.2f}")
    st.subheader("What the numbers say")
    for line in tendency_insights(zt):
        st.markdown("- " + line)

    def section(title, key, builder, note=None):
        st.subheader(title)
        try:
            fig = _cached(st, key, sig, builder)
        except Exception as e:
            st.caption(f"Couldn't draw this chart: {e}")
            return
        if note:
            st.caption(note)
        _show(st, h, fig, f"{title} -- {subject}", key, sig)

    if shots is not None:
        def need(n):
            if len(shots) < n:
                raise UploadError(f"needs at least {n} shots (this file has {len(shots)})")
        def heat():
            need(10)
            return visuals.build_heat_map(shots, color)
        def hexchart():
            need(10)
            if compare == "NBA league average":
                with h.loading("Fetching league averages"):
                    league = h.league_shots(season)
            else:
                league = baseline_comparison_frame(shots, summ["fg"])
            return visuals.build_hex_shot_chart(shots, league, color)
        section("Shot Chart", "up_pl_shot", lambda: visuals.build_shot_chart(shots, color))
        section("Heat Map", "up_pl_heat", heat)
        section("Hex Shot Chart", "up_pl_hex", hexchart,
                "Each hex is sized by how often you shoot there and colored by how you shoot compared with "
                + ("the NBA average from that spot." if compare == "NBA league average" else "your own overall percentage.")
                + " In each zone label, the first percentage is yours; the second is the comparison.")
    section("Zone Map", "up_pl_zone", lambda: build_upload_zone_map(zt), "Each zone is shaded by field goal % (red = lower, green = higher). Labels show makes / attempts.")
    st.subheader("Zone breakdown")
    disp = zt.reset_index()
    st.dataframe(_pct_display(disp, {"FG%", "Share of shots", "eFG%"}).rename(columns={"Points/shot": "Points / shot"}))
    dl1, dl2 = st.columns(2)
    dl1.download_button("Download zone table (CSV)", zt.reset_index().to_csv(index=False).encode(), file_name="zone_table.csv", mime="text/csv", key="up_pl_dl_zone", use_container_width=True)
    if shots is not None:
        dl2.download_button("Download cleaned shots (CSV)", shots.drop(columns=["SHOT_NUMBER"]).to_csv(index=False).encode(), file_name="cleaned_shots.csv",
                            mime="text/csv", key="up_pl_dl_shots", use_container_width=True)
        prog = progress_by_session(shots)
        if prog is not None:
            section("Progress by Session", "up_pl_prog", lambda: build_progress_chart(prog, color), "Field goal % for each date in your file.")


# ------------------------------------------------------------------- THE TEAM
def _team_tab(st, h):
    import visuals
    data, fname = _get_input(st, "tm_box", "Upload box scores (CSV or Excel)", sample_box_scores, "sample_box_scores.csv", "box_scores_template.csv",
                             TEMPLATES["team_box"], "One row per player per game. Add a quarter column to unlock the Clutch Impact Clock.")
    if data is None:
        st.caption("Upload a season of box scores, or try the sample data, for a roster table, season trends, archetype radars and more.")
        return
    df = _read(st, data, fname)
    if df is None:
        return
    with st.expander("Preview your file"):
        st.dataframe(df.head(15))
    mapping = _mapping_ui(st, df, BOX_ALIASES, BOX_LABELS, ("player", "pts"), "up_tm")
    try:
        games, periods, rep = build_box_frame(df, mapping)
    except UploadError as e:
        st.error(str(e))
        return
    st.caption(f"{rep['players']} players across {rep['games']} games" + (" -- quarter-by-quarter rows found, so the Clutch Impact Clock is available." if periods is not None else "."))

    options = ["Roster Table", "Leaders Bar Chart", "Season Trend", "Archetype Radar"] + (["Clutch Impact Clock"] if periods is not None else []) + ["Lineup Network", "Passing Web"]
    viz = st.radio("Visualization:", options, horizontal=True, key="up_tm_viz")
    players = sorted(games["PLAYER"].unique())
    season = "season"
    if games["DATE"].notna().any():
        lo, hi = games["DATE"].min(), games["DATE"].max()
        season = f"{lo:%b %Y}" if lo.to_period("M") == hi.to_period("M") else f"{lo:%b %Y} - {hi:%b %Y}"
    tcolor = st.session_state.get("_global_chart_text_color", "white")
    gsig = _df_sig(games)

    def show(fig_key, title, builder, extra, color):
        sig = _sig(gsig, fig_key, extra, color, tcolor)
        try:
            fig = _cached(st, fig_key, sig, builder)
        except Exception as e:
            st.error(f"Couldn't draw this chart: {e}")
            return
        _show(st, h, fig, title, fig_key, sig)

    if viz == "Roster Table":
        per = st.radio("Stat mode:", ["Per Game", "Per 36", "Totals"], horizontal=True, key="up_tm_per")
        tab = player_table(games, per)
        st.dataframe(_pct_display(tab.reset_index(), {"FG%", "3P%", "FT%", "eFG%", "TS%"}))
        st.download_button("Download roster table (CSV)", tab.reset_index().to_csv(index=False).encode(), file_name="roster_table.csv", mime="text/csv", key="up_tm_dl")
        return

    tab = player_table(games, "Per Game")
    if viz == "Leaders Bar Chart":
        stat_cols = [c for c in tab.columns if c != "GP"]
        stat = st.selectbox("Stat:", stat_cols, index=stat_cols.index("PTS") if "PTS" in stat_cols else 0, key="up_tm_bar_stat")
        top_n = st.number_input("Show the top __ players:", min_value=1, max_value=max(len(tab), 1), value=min(10, len(tab)), key="up_tm_bar_n")
        me = st.multiselect("Highlight:", players, key="up_tm_bar_hl")
        color = _color(st, h, "up_tm_bar_color")
        if h.run_button(True, "upload_team_bar"):
            asc = lower_is_better(stat)
            top = tab[stat].dropna().sort_values(ascending=asc).head(int(top_n))
            pct = "%" in stat
            fmt = (lambda v: f"{v:.0%}") if pct else (lambda v: f"{v:,.1f}")
            label = f"{stat} per game" if stat in ("PTS", "REB", "AST", "STL", "BLK", "TOV", "PF", "MIN") else stat
            show("up_tm_bar", f"Team leaders -- {stat}", lambda: build_rank_bar(top.index.tolist(), top.tolist(), me, color, label, fmt), (stat, top_n, tuple(me)), color)
    elif viz == "Season Trend":
        who = st.selectbox("Player:", players, key="up_tm_tr_who")
        stat = st.selectbox("Stat:", available_trend_stats(games), key="up_tm_tr_stat")
        win = st.slider("Rolling average (games):", 2, 10, 5, key="up_tm_tr_win")
        color = _color(st, h, "up_tm_tr_color")
        if h.run_button(True, "upload_team_trend"):
            lab, vals, is_pct = trend_series(games, who, stat)
            if len(vals) < 2:
                st.warning("That player has fewer than two games with this stat.")
            else:
                show("up_tm_trend", f"Season trend -- {who}", lambda: visuals.build_line_chart(lab, vals, stat, who, season, color, is_percentage=is_pct, rolling_window=win),
                     (who, stat, win), color)
    elif viz == "Archetype Radar":
        default_min = max(1, round(0.25 * rep["games"]))
        min_g = st.number_input("Only rank players with at least __ games:", min_value=1, max_value=max(int(tab["GP"].max()), 1), value=min(default_min, int(tab["GP"].max())), key="up_tm_rad_min")
        try:
            rp = radar_percentiles(tab, int(min_g))
        except UploadError as e:
            st.warning(str(e))
            return
        who = st.selectbox("Player:", list(rp.index), key="up_tm_rad_who")
        other = st.selectbox("Compare with (optional):", ["(nobody)"] + [p for p in rp.index if p != who], key="up_tm_rad_other")
        color = _color(st, h, "up_tm_rad_color")
        st.caption("Percentiles compare this player with teammates on your roster (not the league): 100 = best on the team in that category.")
        if h.run_button(True, "upload_team_radar"):
            two = None if other == "(nobody)" else rp.loc[other].tolist()
            show("up_tm_radar", f"Archetype radar -- {who}", lambda: visuals.build_radar_chart(list(rp.columns), rp.loc[who].tolist(), who, color, second_percentiles=two, second_name=None if two is None else other),
                 (who, other, int(min_g)), color)
    elif viz == "Clutch Impact Clock":
        who = st.selectbox("Player:", players, key="up_tm_ck_who")
        color = _color(st, h, "up_tm_ck_color")
        if h.run_button(True, "upload_team_clock"):
            qs = quarter_stats(periods, who)
            if qs is None:
                st.warning("That player has no quarter-by-quarter scoring in this file.")
            else:
                show("up_tm_clock", f"Clutch impact clock -- {who}", lambda: visuals.build_impact_clock(qs, who, color), (who,), color)
    elif viz == "Lineup Network":
        _lineup_section(st, h, visuals, show)
    else:
        _passing_section(st, h, visuals, players, show)


def _lineup_section(st, h, visuals, show):
    st.caption("Optional second file: how each lineup performed together (net rating or plus/minus).")
    data, fname = _get_input(st, "tm_lu", "Upload lineups (CSV or Excel)", sample_lineups, "sample_lineups.csv", "lineups_template.csv", TEMPLATES["team_lineups"],
                             "One row per lineup: the players (separated by ' - '), minutes together, and net rating.")
    if data is None:
        return
    lu = _read(st, data, fname)
    if lu is None:
        return
    labels = {"lineup": "Lineup (names joined by ' - ')", "a": "Player A (if two columns)", "b": "Player B (if two columns)", "value": "Net rating / plus-minus", "min": "Minutes together"}
    mapping = _mapping_ui(st, lu, LINEUP_ALIASES, labels, ("value",), "up_lu")
    min_min = st.number_input("Minimum minutes played together:", min_value=0, max_value=3000, value=10, step=5, key="up_lu_min") if mapping["min"] else 0
    try:
        two, groups = parse_lineups(lu, mapping, float(min_min))
    except UploadError as e:
        st.error(str(e))
        return
    choices = (["Two-man network"] if two else []) + [f"{n}-man lineups" for n in sorted(groups)]
    if not choices:
        st.warning("No lineups were left after filtering.")
        return
    pick = st.radio("Show:", choices, horizontal=True, key="up_lu_pick")
    color = "#D4AF37"
    if h.run_button(True, "upload_team_lineups"):
        if pick == "Two-man network":
            pl, pv = [tuple(k) for k in two], list(two.values())
            show("up_lu_net", "Two-man lineup network", lambda: visuals.build_network_diagram(pl, pv, player_image_urls={}), (len(two), min_min), color)
        else:
            n = int(pick.split("-")[0])
            grp = groups[n]
            show(f"up_lu_{n}", f"{n}-man lineups", lambda: visuals.build_lineup_shapes_diagram(grp, two, player_image_urls={}), (n, len(grp), min_min), color)


def _passing_section(st, h, visuals, players, show):
    st.caption("Optional second file: who passed to whom, and the shots that came from those passes.")
    data, fname = _get_input(st, "tm_ps", "Upload passes (CSV or Excel)", sample_passes, "sample_passes.csv", "passes_template.csv", TEMPLATES["team_passes"],
                             "One row per passer-to-teammate pair: number of passes, and (optionally) the shots that followed.")
    if data is None:
        return
    ps = _read(st, data, fname)
    if ps is None:
        return
    labels = {"passer": "Passer", "receiver": "Receiver", "passes": "Number of passes", "fgm": "FG made (optional)", "fga": "FG attempted (optional)", "fg3a": "3P attempted (optional)"}
    mapping = _mapping_ui(st, ps, PASS_ALIASES, labels, ("passer", "receiver", "passes"), "up_ps")
    try:
        pp = parse_passes(ps, mapping)
    except UploadError as e:
        st.error(str(e))
        return
    who = st.selectbox("Passer:", sorted(pp["PASSER"].unique()), key="up_ps_who")
    color = _color(st, h, "up_ps_color")
    if h.run_button(True, "upload_team_passing"):
        d = pp[pp["PASSER"] == who].sort_values("PASSES", ascending=False).head(8)
        extra = [{"fga": int(r.FGA), "fg3a": int(r.FG3A)} for r in d.itertuples()]
        show("up_ps_web", f"Passing web -- {who}", lambda: visuals.build_court_connection_map(
            who, d["RECEIVER"].tolist(), d["PASSES"].astype(int).tolist(), d["FGM"].astype(int).tolist(), color, receiver_extra_stats=extra), (who,), color)


# ----------------------------------------------------------------- THE LEAGUE
def _league_tab(st, h):
    data, fname = _get_input(st, "lg", "Upload team stats (CSV or Excel)", sample_league, "sample_league.csv", "league_template.csv", TEMPLATES["league"],
                             "One row per team (season totals or averages) or one row per game -- games are averaged per team.")
    if data is None:
        st.caption("Upload every team's stats, or try the sample data, for rankings, a scatter plot and a head-to-head matchup read.")
        return
    df = _read(st, data, fname)
    if df is None:
        return
    team_col = st.selectbox("Team name column:", list(df.columns), index=list(df.columns).index(guess_team_column(df)), key=f"up_lg_team_{_sig(*df.columns)}")
    try:
        t, mode = league_table(df, team_col)
    except UploadError as e:
        st.error(str(e))
        return
    st.caption(f"{len(t)} teams" + (" -- one row per game detected, averaged for each team." if mode == "games" else "."))
    stats = [c for c in t.columns if c != "Games"]
    pct_cols = {c for c in stats if "%" in c and is_fraction_column(t[c])}
    viz = st.radio("Visualization:", ["Leaderboard", "Bar Chart", "Scatter Plot", "Matchup"], horizontal=True, key="up_lg_viz")
    tcolor = st.session_state.get("_global_chart_text_color", "white")
    tsig = _df_sig(t.reset_index())
    fmt_for = lambda c: (lambda v: f"{v:.1%}") if c in pct_cols else (lambda v: f"{v:,.1f}")

    if viz == "Leaderboard":
        stat = st.selectbox("Stat:", stats, index=stats.index("pts") if "pts" in stats else 0, key="up_lg_lb_stat")
        order = st.radio("Order:", ["Highest first", "Lowest first"], index=1 if lower_is_better(stat) else 0, horizontal=True, key=f"up_lg_lb_ord_{stat}")
        ranked = t[stat].dropna().sort_values(ascending=(order == "Lowest first"))
        board = pd.DataFrame({"Rank": range(1, len(ranked) + 1), "Team": ranked.index, stat: ranked.values,
                              "Percentile": (t[stat].rank(pct=True) * 100).reindex(ranked.index).round(0).astype(int).values})
        st.dataframe(_pct_display(board, pct_cols))
        with st.expander("Full league table"):
            st.dataframe(_pct_display(t.reset_index(), pct_cols))
        st.download_button("Download league table (CSV)", t.reset_index().to_csv(index=False).encode(), file_name="league_table.csv", mime="text/csv", key="up_lg_dl")
        return
    hl = st.multiselect("Highlight team(s):", list(t.index), key="up_lg_hl")
    color = _color(st, h, "up_lg_color")

    def show(key, title, builder, extra):
        sig = _sig(tsig, key, extra, color, tcolor)
        try:
            fig = _cached(st, key, sig, builder)
        except Exception as e:
            st.error(f"Couldn't draw this chart: {e}")
            return
        _show(st, h, fig, title, key, sig)

    if viz == "Bar Chart":
        stat = st.selectbox("Stat:", stats, index=stats.index("pts") if "pts" in stats else 0, key="up_lg_bar_stat")
        top_n = st.number_input("Show the top __ teams:", min_value=1, max_value=len(t), value=min(len(t), 12), key="up_lg_bar_n")
        if h.run_button(True, "upload_league_bar"):
            top = t[stat].dropna().sort_values(ascending=lower_is_better(stat)).head(int(top_n))
            show("up_lg_bar", f"League leaders -- {stat}", lambda: build_rank_bar(top.index.tolist(), top.tolist(), hl, color, stat, fmt_for(stat)), (stat, top_n, tuple(hl)))
    elif viz == "Scatter Plot":
        xs = st.selectbox("x-axis:", stats, index=stats.index("pts") if "pts" in stats else 0, key="up_lg_sx")
        ys = st.selectbox("y-axis:", stats, index=stats.index("opp_pts") if "opp_pts" in stats else min(1, len(stats) - 1), key="up_lg_sy")
        if h.run_button(True, "upload_league_scatter"):
            show("up_lg_scatter", f"{ys} vs {xs}", lambda: build_team_scatter(t, xs, ys, hl, color), (xs, ys, tuple(hl)))
    else:
        c1, c2 = st.columns(2)
        a = c1.selectbox("Your team:", list(t.index), key="up_lg_ma")
        b = c2.selectbox("Opponent:", [x for x in t.index if x != a], key="up_lg_mb")
        mu = matchup_read(t, a, b)
        edges_a, edges_b = mu[mu["Edge"] == a].head(3)["Stat"].tolist(), mu[mu["Edge"] == b].tail(3)["Stat"].tolist()[::-1]
        st.subheader("Matchup read")
        st.markdown(f"- **{a}'s clearest edges:** " + (", ".join(edges_a) if edges_a else "none stand out"))
        st.markdown(f"- **{b}'s clearest edges:** " + (", ".join(edges_b) if edges_b else "none stand out"))
        st.caption("Edges are measured in league standard deviations; stats where lower is better (turnovers, fouls, points allowed) are flipped.")
        show_tab = mu.drop(columns=["_edge"]).copy()
        for c in (a, b):
            show_tab[c] = [format_stat(s, v) if s in pct_cols else f"{v:,.1f}" for s, v in zip(show_tab["Stat"], show_tab[c])]
        st.dataframe(show_tab)


# ------------------------------------------------------------------ ENTRY POINT
def render_upload_stats_page(h):
    """
    Called from app.py. `h` carries the app's own helpers so this page looks and behaves like every other one:
    h.run_button(enabled, key), h.loading(label), h.tableau(fig, label, key), h.info_card(title, body),
    h.color_picker(key), h.resolve_color(text), h.league_shots(season), h.seasons.
    """
    import streamlit as st
    st.title("Upload Stats")
    st.caption("Bring your own numbers -- a player's shots, a team's box scores, or a whole league -- and get the same analysis this dashboard runs on NBA data. "
               "CSV or Excel files up to 15 MB.")
    h.info_card("Your data stays private",
                "Files are read in memory for this session only. They are never saved, never added to Community Uploads, and disappear when you close the tab.")
    who = st.radio("This data is for:", _AUDIENCES, horizontal=True, key="up_audience")
    {"The Player": _player_tab, "The Team": _team_tab, "The League": _league_tab}[who](st, h)
