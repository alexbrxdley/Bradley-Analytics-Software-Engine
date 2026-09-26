"""
ai_search.py

The AI Search page ("Bradley"): ask any basketball question in plain language and get a written answer plus an
interactive chart that answers it.

How a question is handled:
  1. The language model (Groq) reads the question. If something that changes the answer is missing -- above all the
     season -- it asks for it first, with one-click answer options.
  2. It looks up the real numbers with the data tools below (live NBA stats: season and career stats, game logs,
     league leaders with filters, shot zones, clutch / hustle / defense / play-type tables, passing, lineups, on/off,
     head-to-head), and uses web search for news or anything the stats tables don't cover.
  3. It writes the answer, and creates the chart that best answers the question. Every chart has controls on top
     (colour, style, season, top-N, per-game/totals ...) that redraw it instantly, with no new question needed.

Everything lives in st.session_state, so the whole conversation -- text and charts -- stays on the page.
"""

import difflib
import hashlib
from html import escape as html_escape
import json
import math
import os
import re
import time
import unicodedata
import uuid

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import hotspots as hover
import interactive
import nba_data
import pickers
import stats_config
import ui_hooks
import visuals
from teams import get_player_headshot_url, get_team_logo_url

MODEL = "openai/gpt-oss-120b"
SEARCH_MODEL = "groq/compound-mini"
MAX_ROUNDS = 8
HTML_CACHE_SIZE = 16
LIVE_ANSWERS = 6        # charts in the latest answers are drawn right away; older ones on request

CTX = {}   # helpers handed over by app.py (name lookups, colour resolution, loading animation ...)


class ToolError(Exception):
    """A tool problem to report back to the model (bad name, unknown stat, no data) -- never a crash."""


# ================================================================ names

def _fold(s):
    s = "".join(c for c in unicodedata.normalize("NFKD", str(s or "")) if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_NICKNAMES = {
    "steph": "Stephen Curry", "chef curry": "Stephen Curry", "kd": "Kevin Durant", "bron": "LeBron James",
    "king james": "LeBron James", "greek freak": "Giannis Antetokounmpo", "the greek freak": "Giannis Antetokounmpo",
    "ad": "Anthony Davis", "the brow": "Anthony Davis", "sga": "Shai Gilgeous-Alexander", "cp3": "Chris Paul",
    "dame": "Damian Lillard", "ant": "Anthony Edwards", "ant man": "Anthony Edwards", "wemby": "Victor Wembanyama",
    "pg13": "Paul George", "kat": "Karl-Anthony Towns", "jimmy buckets": "Jimmy Butler", "joker": "Nikola Jokic",
    "the joker": "Nikola Jokic", "the process": "Joel Embiid", "melo": "Carmelo Anthony", "mj": "Michael Jordan",
    "shaq": "Shaquille O'Neal", "black mamba": "Kobe Bryant", "the big fundamental": "Tim Duncan",
    "dr j": "Julius Erving", "the answer": "Allen Iverson", "d wade": "Dwyane Wade", "flash": "Dwyane Wade",
    "the mailman": "Karl Malone", "the dream": "Hakeem Olajuwon", "spida": "Donovan Mitchell", "book": "Devin Booker",
    "the beard": "James Harden", "russ": "Russell Westbrook", "brodie": "Russell Westbrook", "uncle drew": "Kyrie Irving",
    "scottie": "Scottie Barnes", "chet": "Chet Holmgren", "cade": "Cade Cunningham", "luka": "Luka Doncic",
    "giannis": "Giannis Antetokounmpo", "lebron": "LeBron James", "kobe": "Kobe Bryant", "zion": "Zion Williamson",
    "wemby s": "Victor Wembanyama", "bam": "Bam Adebayo", "trae": "Trae Young", "ja": "Ja Morant",
}

_TEAM_ALIASES = {
    "sixers": "Philadelphia 76ers", "76ers": "Philadelphia 76ers", "cavs": "Cleveland Cavaliers",
    "mavs": "Dallas Mavericks", "wolves": "Minnesota Timberwolves", "t wolves": "Minnesota Timberwolves",
    "blazers": "Portland Trail Blazers", "dubs": "Golden State Warriors", "gsw": "Golden State Warriors",
    "okc": "Oklahoma City Thunder", "nola": "New Orleans Pelicans", "pels": "New Orleans Pelicans",
    "knicks": "New York Knicks", "nets": "Brooklyn Nets", "celts": "Boston Celtics", "c s": "Boston Celtics",
    "lakers": "Los Angeles Lakers", "clips": "LA Clippers", "clippers": "LA Clippers", "spurs": "San Antonio Spurs",
    "grizz": "Memphis Grizzlies", "wizards": "Washington Wizards", "sac": "Sacramento Kings",
}


def _player_index():
    idx = st.session_state.get("_ai_player_index")
    if idx is None:
        full, last, first = {}, {}, {}
        for rec in CTX["PLAYER_NAME_TO_RECORD"].values():
            f = _fold(rec.get("full_name"))
            full.setdefault(f, []).append(rec)
            parts = f.split()
            if parts:
                tail = [p for p in parts if p not in {"jr", "sr", "ii", "iii", "iv"}]
                if tail:
                    last.setdefault(tail[-1], []).append(rec)
                    if len(tail) > 2:
                        last.setdefault(" ".join(tail[1:]), []).append(rec)
                first.setdefault(parts[0], []).append(rec)
        idx = {"full": full, "last": last, "first": first, "names": list(full)}
        st.session_state["_ai_player_index"] = idx
    return idx


def _pick_active(recs):
    active = [r for r in recs if r.get("is_active")]
    return active or recs


def resolve_player(query):
    """-> the nba_api player record for a name as people type it ('jokic', 'Steph', 'Curry, Stephen', 'SGA')."""
    q = _fold(query)
    if not q:
        raise ToolError("No player name given.")
    if "," in str(query):
        last, _, first = str(query).partition(",")
        q = _fold(f"{first} {last}")
    q = _fold(_NICKNAMES.get(q, q))
    idx = _player_index()
    if q in idx["full"]:
        return _pick_active(idx["full"][q])[0]
    for table in ("last", "first"):
        recs = idx[table].get(q)
        if recs:
            active = [r for r in recs if r.get("is_active")]
            if len(active) == 1:
                return active[0]
            if len(recs) == 1:
                return recs[0]
            options = ", ".join(r["full_name"] for r in (active or recs)[:6])
            raise ToolError(f"'{query}' could be several players: {options}. Ask which one.")
    close = difflib.get_close_matches(q, idx["names"], n=5, cutoff=0.72)
    if close:
        best = _pick_active(idx["full"][close[0]])[0]
        if difflib.SequenceMatcher(None, q, close[0]).ratio() >= 0.88 or len(close) == 1:
            return best
        raise ToolError(f"No exact match for '{query}'. Closest: "
                        + ", ".join(_pick_active(idx["full"][c])[0]["full_name"] for c in close) + ".")
    raise ToolError(f"No NBA player found named '{query}'.")


def resolve_team(query):
    q = _fold(query)
    if not q:
        raise ToolError("No team name given.")
    q = _fold(_TEAM_ALIASES.get(q, q))
    recs = list(CTX["TEAM_NAME_TO_RECORD"].values())
    exact = [r for r in recs if q in {_fold(r["full_name"]), _fold(r["nickname"]), _fold(r["abbreviation"]),
                                      _fold(r["city"]), _fold(f'{r["city"]} {r["nickname"]}')}]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise ToolError(f"'{query}' could be: " + ", ".join(r["full_name"] for r in exact) + ". Ask which one.")
    if q in ("la", "los angeles", "l a"):
        raise ToolError("'LA' could be the Lakers or the Clippers -- ask which one.")
    hits = [r for r in recs if len(q) >= 3 and q in _fold(r["full_name"]).split()]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise ToolError(f"'{query}' could be: " + ", ".join(r["full_name"] for r in hits) + ". Ask which one.")
    names = [_fold(r["full_name"]) for r in recs]
    close = difflib.get_close_matches(q, names, n=1, cutoff=0.6)
    if close:
        return next(r for r in recs if _fold(r["full_name"]) == close[0])
    raise ToolError(f"No NBA team found for '{query}'.")


def _subject(subject_type, name):
    """-> (mode, record, id, display_name, short_label)"""
    if (subject_type or "player") == "team":
        r = resolve_team(name)
        return "team", r, r["id"], r["full_name"], r.get("nickname") or r["full_name"]
    r = resolve_player(name)
    parts = [p for p in r["full_name"].split() if p.lower().rstrip(".") not in {"jr", "sr", "ii", "iii", "iv"}]
    return "player", r, r["id"], r["full_name"], (parts[-1] if parts else r["full_name"])


# ================================================================ stats

STAT_LABELS = {
    "PTS": "Points", "REB": "Rebounds", "AST": "Assists", "STL": "Steals", "BLK": "Blocks", "TOV": "Turnovers",
    "FGM": "FGM", "FGA": "FGA", "FG_PCT": "FG%", "FG3M": "3PM", "FG3A": "3PA", "FG3_PCT": "3P%", "FTM": "FTM",
    "FTA": "FTA", "FT_PCT": "FT%", "OREB": "Off. Rebounds", "DREB": "Def. Rebounds", "PF": "Fouls",
    "PFD": "Fouls Drawn", "PLUS_MINUS": "+/-", "MIN": "Minutes", "GP": "Games", "W": "Wins", "L": "Losses",
    "W_PCT": "Win %", "DD2": "Double-Doubles", "TD3": "Triple-Doubles", "TS_PCT": "TS%", "EFG_PCT": "eFG%",
    "USG_PCT": "Usage %", "AST_PCT": "AST%", "REB_PCT": "REB%", "OREB_PCT": "OREB%", "DREB_PCT": "DREB%",
    "AST_TO": "AST/TO", "AST_RATIO": "AST Ratio", "TM_TOV_PCT": "TOV%", "OFF_RATING": "Off. Rating",
    "DEF_RATING": "Def. Rating", "NET_RATING": "Net Rating", "PACE": "Pace", "PIE": "PIE", "POSS": "Possessions",
    "BLKA": "Shots Blocked", "NBA_FANTASY_PTS": "Fantasy Pts", "PPS": "Points per Shot", "FT_RATE": "FT Rate",
    "FG3A_RATE": "3PA Rate", "AGE": "Age",
}

_STAT_ALIASES = {
    "points": "PTS", "pts": "PTS", "ppg": "PTS", "scoring": "PTS", "rebounds": "REB", "rebounding": "REB", "rpg": "REB",
    "boards": "REB", "assists": "AST", "apg": "AST", "dimes": "AST", "steals": "STL", "spg": "STL", "blocks": "BLK",
    "bpg": "BLK", "turnovers": "TOV", "tov": "TOV", "to": "TOV", "field goal percentage": "FG_PCT", "fg": "FG_PCT",
    "fg pct": "FG_PCT", "fg percentage": "FG_PCT", "three point percentage": "FG3_PCT", "3pt percentage": "FG3_PCT",
    "3p": "FG3_PCT", "3pt": "FG3_PCT", "3p pct": "FG3_PCT", "3pt pct": "FG3_PCT", "three point pct": "FG3_PCT",
    "threes made": "FG3M", "3pm": "FG3M", "threes": "FG3M", "3 pointers made": "FG3M", "three pointers made": "FG3M",
    "3pa": "FG3A", "three point attempts": "FG3A", "free throw percentage": "FT_PCT", "ft": "FT_PCT", "ft pct": "FT_PCT",
    "free throws made": "FTM", "free throw attempts": "FTA", "true shooting": "TS_PCT", "ts": "TS_PCT",
    "true shooting percentage": "TS_PCT", "effective field goal percentage": "EFG_PCT", "efg": "EFG_PCT",
    "usage": "USG_PCT", "usage rate": "USG_PCT", "usg": "USG_PCT", "plus minus": "PLUS_MINUS", "minutes": "MIN",
    "mpg": "MIN", "games": "GP", "games played": "GP", "wins": "W", "losses": "L", "win percentage": "W_PCT",
    "double doubles": "DD2", "triple doubles": "TD3", "net rating": "NET_RATING", "offensive rating": "OFF_RATING",
    "defensive rating": "DEF_RATING", "ortg": "OFF_RATING", "drtg": "DEF_RATING", "pace": "PACE",
    "offensive rebounds": "OREB", "defensive rebounds": "DREB", "fouls": "PF", "personal fouls": "PF",
    "assist percentage": "AST_PCT", "rebound percentage": "REB_PCT", "assist to turnover": "AST_TO",
    "field goals made": "FGM", "field goals attempted": "FGA", "field goal attempts": "FGA", "shots": "FGA",
    "player impact estimate": "PIE", "fantasy points": "NBA_FANTASY_PTS", "age": "AGE",
}


def _is_pct(field):
    return str(field).endswith("_PCT") or field in ("PIE",)


def stat_label(field):
    return STAT_LABELS.get(field, str(field).replace("_PCT", "%").replace("_", " ").title())


def _resolve_stat(name, columns):
    if not name:
        raise ToolError("No stat given.")
    cols = [c for c in columns if not str(c).endswith("_RANK")]
    u = str(name).strip().upper().replace("%", "_PCT").replace(" ", "_").replace("-", "_")
    if u in cols:
        return u
    alias = _STAT_ALIASES.get(_fold(name))
    if alias and alias in cols:
        return alias
    known = alias or (u if u in STAT_LABELS else None)
    if known:   # a real stat this table just doesn't have (e.g. TS% in a game log) -- never swap in a look-alike
        raise ToolError(f"{stat_label(known)} isn't available here. Available: "
                        f"{', '.join(c for c in cols if c in STAT_LABELS)}.")
    close = difflib.get_close_matches(u, cols, n=1, cutoff=0.9)
    if close:
        return close[0]
    common = [c for c in cols if c in STAT_LABELS][:40]
    raise ToolError(f"Unknown stat '{name}'. Available: {', '.join(common)}.")


LOWER_IS_BETTER = set(getattr(stats_config, "LOWER_IS_BETTER_STATS", set())) | {"TOV", "PF", "DEF_RATING", "L",
                                                                                  "D_FG_PCT", "PCT_PLUSMINUS"}
# a leaderboard with no direction given lists the highest values first -- except these, where "leading" means lowest
BEST_IS_LOWEST = {"DEF_RATING", "D_FG_PCT", "PCT_PLUSMINUS"}


def _num(v, field=None):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    if math.isnan(f):
        return None
    if field and _is_pct(field):
        return round(f, 3)
    if abs(f) < 10:
        return round(f, 3)
    return round(f, 1) if abs(f) < 1000 else round(f)


def _fmt(v, field):
    if v is None:
        return "-"
    v = float(v)
    if _is_pct(field):
        return f"{v:.1f}%" if abs(v) > 1.5 else f"{v:.1%}"     # a few tables report percentages on a 0-100 scale
    return f"{v:,.1f}" if abs(v) < 1000 else f"{v:,.0f}"


_PER_MODES = {"pergame": "PerGame", "per game": "PerGame", "totals": "Totals", "total": "Totals",
              "per36": "Per36", "per 36": "Per36"}


def _per_mode(v):
    return _PER_MODES.get(_fold(v).replace(" ", "") if v else "pergame", _PER_MODES.get(_fold(v or ""), "PerGame"))


def _season(v):
    s = str(v or "").strip()
    cur = stats_config.current_season()
    if not s or s.lower() in ("current", "this season", "latest", "now"):
        return cur
    if s.lower() in ("last season", "previous", "last"):
        y = int(cur[:4]) - 1
        return f"{y}-{str(y + 1)[-2:]}"
    if "career" in s.lower() or "all-time" in s.lower() or "all time" in s.lower():
        raise ToolError("That needs a single season here -- use career_stats / a career_trend chart for careers.")
    m = re.search(r"(\d{4})\s*[-\u2013\u2014/]\s*(\d{2,4})", s)
    if m:
        y = int(m.group(1))
        return f"{y}-{str(y + 1)[-2:]}"
    m = re.search(r"\b(\d{4})\b", s)
    if m:   # "2024" -> the season that ENDED in 2024 (how people usually say it)
        y = int(m.group(1)) - 1
        return f"{y}-{str(y + 1)[-2:]}"
    raise ToolError(f"Couldn't read the season '{v}' -- use the YYYY-YY form, e.g. {cur}.")


def _table(subject_type, season, per_mode):
    if subject_type == "team":
        df = nba_data.get_team_stats(season, per_mode=per_mode)
        return df, "TEAM_NAME", "TEAM_ID"
    return nba_data.get_player_stats(season, per_mode=per_mode), "PLAYER_NAME", "PLAYER_ID"


def _apply_filters(df, filters, season, per_mode):
    """Position / age / height / stat-range filters (players)."""
    filters = filters or {}
    notes = []
    if filters.get("position") not in (None, ""):
        want = str(filters["position"]).strip().upper()
        letter = {"PG": "G", "SG": "G", "GUARD": "G", "GUARDS": "G", "SF": "F", "PF": "F", "FORWARD": "F",
                  "FORWARDS": "F", "CENTER": "C", "CENTERS": "C", "WING": "F"}.get(want, want[:1])
        if letter not in ("G", "F", "C"):
            raise ToolError("position must be G, F or C.")
        pos = nba_data.get_player_positions(season)
        df = df.merge(pos, on="PLAYER_ID", how="left")
        df = df[df["POSITION"].astype(str).str.upper().str.contains(letter, na=False)]
        notes.append({"G": "guards", "F": "forwards", "C": "centers"}[letter])
    if any(filters.get(k) not in (None, "") for k in ("min_height_inches", "max_height_inches")):
        bio = nba_data.get_player_bio_stats(season)
        if "PLAYER_HEIGHT_INCHES" in bio.columns:
            df = df.merge(bio[["PLAYER_ID", "PLAYER_HEIGHT_INCHES"]], on="PLAYER_ID", how="left")
        if filters.get("min_height_inches") is not None and "PLAYER_HEIGHT_INCHES" in df:
            df = df[df["PLAYER_HEIGHT_INCHES"] >= float(filters["min_height_inches"])]
        if filters.get("max_height_inches") is not None and "PLAYER_HEIGHT_INCHES" in df:
            df = df[df["PLAYER_HEIGHT_INCHES"] <= float(filters["max_height_inches"])]
    if filters.get("min_age") is not None and "AGE" in df:
        df = df[df["AGE"] >= float(filters["min_age"])]
    if filters.get("max_age") is not None and "AGE" in df:
        df = df[df["AGE"] <= float(filters["max_age"])]
    if filters.get("team"):
        t = resolve_team(filters["team"])
        if "TEAM_ID" in df:
            df = df[df["TEAM_ID"] == t["id"]]
            notes.append(t["nickname"])
    for sf in filters.get("stat_filters") or []:
        field = _resolve_stat(sf.get("stat"), df.columns)
        vals = pd.to_numeric(df[field], errors="coerce")
        if sf.get("min") is not None:
            df = df[vals >= float(sf["min"])]
            vals = pd.to_numeric(df[field], errors="coerce")
        if sf.get("max") is not None:
            df = df[vals <= float(sf["max"])]
        notes.append(f"{stat_label(field)} {sf.get('min', '')}-{sf.get('max', '')}".replace(" -", " ≤").rstrip("-"))
    return df, notes


_ATTEMPT_FLOORS = {"FG_PCT": ("FGA", 5.0), "EFG_PCT": ("FGA", 5.0), "TS_PCT": ("FGA", 5.0), "FG3_PCT": ("FG3A", 2.5),
                   "FT_PCT": ("FTA", 2.0), "PPS": ("FGA", 5.0)}


def _qualify(df, subject_type, per_mode, field, filters):
    """Keeps the rankings meaningful: a minimum of games for per-game/per-36 player rankings, and attempt floors for
    shooting percentages (so a 1-for-1 shooter never 'leads the league' at 100%)."""
    notes = []
    if subject_type != "player" or df.empty:
        return df, notes
    filters = filters or {}
    min_games = filters.get("min_games")
    if min_games is None and field not in ("GP", "W", "L") and "GP" in df and per_mode != "Totals":
        min_games = max(1, int(round(0.4 * float(df["GP"].max() or 0))))
    if min_games:
        df = df[df["GP"] >= float(min_games)]
        notes.append(f"at least {int(min_games)} games")
    if field in _ATTEMPT_FLOORS:
        col, per_game = _ATTEMPT_FLOORS[field]
        if col in df:
            att = pd.to_numeric(df[col], errors="coerce")
            if per_mode == "Totals" and "GP" in df:
                att = att / df["GP"].replace(0, np.nan)
            df = df[att >= per_game]
            notes.append(f"at least {per_game:g} {col} per {'36 minutes' if per_mode == 'Per36' else 'game'}")
    return df, notes


def _rank_table(subject_type, stat, season, per_mode="PerGame", top_n=10, ascending=None, filters=None,
                extra_stats=None):
    season, per_mode = _season(season), _per_mode(per_mode)
    subject_type = "team" if subject_type == "team" else "player"
    df, name_col, id_col = _table(subject_type, season, per_mode)
    if df is None or df.empty:
        raise ToolError(f"No {subject_type} data for {season}.")
    field = _resolve_stat(stat, df.columns)
    df = df.copy()
    df[field] = pd.to_numeric(df[field], errors="coerce")
    df = df.dropna(subset=[field])
    df, fnotes = _apply_filters(df, filters, season, per_mode)
    df, qnotes = _qualify(df, subject_type, per_mode, field, filters)
    if ascending is None:
        ascending = field in BEST_IS_LOWEST
    df = df.sort_values(field, ascending=bool(ascending))
    top_n = max(1, min(int(top_n or 10), 50))
    extra = []
    for s in extra_stats or []:
        try:
            f = _resolve_stat(s, df.columns)
            if f != field:
                extra.append(f)
        except ToolError:
            pass
    return {"df": df, "top": df.head(top_n), "field": field, "label": stat_label(field), "season": season,
            "per_mode": per_mode, "name_col": name_col, "id_col": id_col, "ascending": bool(ascending),
            "notes": fnotes + qnotes, "extra": extra, "subject_type": subject_type, "pool": len(df)}


def _row_out(row, fields, name_col):
    out = {"name": row[name_col]}
    if "TEAM_ABBREVIATION" in row.index and name_col == "PLAYER_NAME":
        out["team"] = row["TEAM_ABBREVIATION"]
    for f in fields:
        if f in row.index:
            out[f] = _num(row[f], f)
    return out


def _league_rank(df, field, value, higher_better=True):
    vals = pd.to_numeric(df[field], errors="coerce").dropna()
    if value is None or vals.empty:
        return None
    better = (vals > value).sum() if higher_better else (vals < value).sum()
    return f"{int(better) + 1} of {len(vals)}"


# ================================================================ data tools

_DEFAULT_PLAYER_STATS = ["GP", "MIN", "PTS", "REB", "AST", "STL", "BLK", "TOV", "FG_PCT", "FG3_PCT", "FT_PCT",
                         "TS_PCT", "USG_PCT", "PLUS_MINUS"]
_DEFAULT_TEAM_STATS = ["GP", "W", "L", "W_PCT", "PTS", "REB", "AST", "FG_PCT", "FG3_PCT", "OFF_RATING", "DEF_RATING",
                       "NET_RATING", "PACE"]


def tool_season_stats(subject_type="player", names=None, season=None, per_mode="PerGame", stats=None):
    season, per_mode = _season(season), _per_mode(per_mode)
    subject_type = "team" if subject_type == "team" else "player"
    df, name_col, id_col = _table(subject_type, season, per_mode)
    if df is None or df.empty:
        raise ToolError(f"No {subject_type} stats for {season}.")
    fields = [_resolve_stat(s, df.columns) for s in (stats or [])] or \
        [f for f in (_DEFAULT_PLAYER_STATS if subject_type == "player" else _DEFAULT_TEAM_STATS) if f in df.columns]
    qual, _ = _qualify(df, subject_type, per_mode, "PTS", {})
    out = []
    for n in (names or [])[:8]:
        mode, rec, sid, disp, _ = _subject(subject_type, n)
        row = df[df[id_col] == sid]
        if row.empty:
            out.append({"name": disp, "note": f"no {season} regular-season stats (didn't play?)"})
            continue
        r = row.iloc[0]
        item = _row_out(r, fields, name_col)
        ranks = {}
        for f in fields:
            if f in ("GP", "MIN", "W", "L") or f not in r.index:
                continue
            base = qual if subject_type == "player" and not qual.empty else df
            try:
                val = float(r[f])
            except (TypeError, ValueError):
                continue
            rk = None if math.isnan(val) else _league_rank(base, f, val, f not in LOWER_IS_BETTER)
            if rk:
                ranks[f] = rk
        item["league_rank"] = ranks
        out.append(item)
    return {"season": season, "per_mode": per_mode, "rows": out,
            "rank_note": "ranks among players with enough games" if subject_type == "player" else "ranks among 30 teams"}


def _career_rows(player_id, per_mode):
    frames = nba_data.get_player_career_stats(player_id, per_mode)
    seasons = frames.get("season_totals_regular_season", pd.DataFrame())
    if seasons.empty:
        return seasons, frames
    # one row per season: the combined "TOT" row for a traded season
    rows = []
    for sid, grp in seasons.groupby("SEASON_ID", sort=True):
        tot = grp[grp["TEAM_ABBREVIATION"] == "TOT"]
        r = (tot.iloc[0] if not tot.empty else grp.iloc[-1]).copy()
        if not tot.empty:
            r["TEAM_ABBREVIATION"] = "/".join(t for t in grp["TEAM_ABBREVIATION"] if t != "TOT")
        rows.append(r)
    return pd.DataFrame(rows).reset_index(drop=True), frames


def tool_career_stats(player=None, per_mode="PerGame", stats=None, playoffs=False):
    _, rec, pid, disp, _ = _subject("player", player)
    per_mode = _per_mode(per_mode)
    seasons, frames = _career_rows(pid, per_mode)
    if playoffs:
        seasons = frames.get("season_totals_post_season", pd.DataFrame())
    if seasons is None or seasons.empty:
        raise ToolError(f"No career stats found for {disp}.")
    fields = [_resolve_stat(s, seasons.columns) for s in (stats or [])] or \
        [f for f in ["GP", "MIN", "PTS", "REB", "AST", "STL", "BLK", "FG_PCT", "FG3_PCT", "FT_PCT"] if f in seasons]
    rows = [{"season": r["SEASON_ID"], "team": r.get("TEAM_ABBREVIATION"), **{f: _num(r[f], f) for f in fields}}
            for _, r in seasons.iterrows()]
    career = frames.get("career_totals_post_season" if playoffs else "career_totals_regular_season", pd.DataFrame())
    total = {f: _num(career.iloc[0][f], f) for f in fields if not career.empty and f in career.columns}
    return {"player": disp, "per_mode": per_mode, "playoffs": bool(playoffs), "seasons": rows[-25:], "career": total}


def _game_log(mode, sid, season):
    log = nba_data.get_player_game_log(sid, season) if mode == "player" else nba_data.get_team_game_log(sid, season)
    if log is None or log.empty:
        return pd.DataFrame()
    log = log.copy()
    log["_DATE"] = pd.to_datetime(log["GAME_DATE"], errors="coerce", format="mixed")
    return log.sort_values("_DATE").reset_index(drop=True)


QUARTER_NAMES = {1: "1st quarter", 2: "2nd quarter", 3: "3rd quarter", 4: "4th quarter", 5: "overtime"}
_QUARTER_WORDS = {"1": 1, "q1": 1, "1st": 1, "first": 1, "2": 2, "q2": 2, "2nd": 2, "second": 2, "3": 3, "q3": 3,
                  "3rd": 3, "third": 3, "4": 4, "q4": 4, "4th": 4, "fourth": 4, "5": 5, "ot": 5, "overtime": 5}


def _quarter(v):
    """A quarter the model or the user named -> 1-4 (5 = overtime); None for the whole game."""
    if v is None:
        return None
    s = _fold(str(v)).replace("quarter", "").replace("period", "").replace(" ", "")
    if s in ("", "0", "all", "game", "wholegame", "full", "fullgame", "none", "null"):
        return None
    if s not in _QUARTER_WORDS:
        raise ToolError("quarter must be 1, 2, 3, 4 or OT (leave it out for whole games).")
    return _QUARTER_WORDS[s]


def _period_log(mode, sid, season, quarter):
    """Game by game, with the stats from ONE quarter only."""
    log = nba_data.get_period_game_log(mode, sid, season, quarter)
    if log is None or log.empty:
        return pd.DataFrame()
    log = log.copy()
    log["_DATE"] = pd.to_datetime(log["GAME_DATE"], errors="coerce", format="mixed")
    log = log.dropna(subset=["_DATE"]).sort_values("_DATE").reset_index(drop=True)
    # the same "APR 13, 2025" dates the whole-game logs use (these endpoints send "2025-04-13T00:00:00")
    log["GAME_DATE"] = log["_DATE"].dt.strftime("%b %d, %Y").str.upper()
    return log


def tool_quarter_stats(subject_type="player", name=None, season=None):
    """Per-game averages inside each quarter, and which quarter is best by points, FG% and plus-minus."""
    mode, rec, sid, disp, _ = _subject(subject_type, name)
    season = _season(season)
    bq = nba_data.get_player_stats_by_quarter(sid, season) if mode == "player" else \
        nba_data.get_team_stats_by_quarter(sid, season)
    if bq is None or bq.empty or "QUARTER" not in bq.columns:
        raise ToolError(f"Couldn't load quarter-by-quarter stats for {disp} in {season}.")
    bq = bq.sort_values("QUARTER").reset_index(drop=True)
    fields = [f for f in ("GP", "MIN", "PTS", "REB", "AST", "FGM", "FGA", "FG_PCT", "FG3M", "FG3_PCT", "FT_PCT",
                          "PLUS_MINUS") if f in bq.columns]
    rows = [{"quarter": QUARTER_NAMES.get(int(r["QUARTER"]), str(r["QUARTER"])), **{f: _num(r[f], f) for f in fields}}
            for _, r in bq.iterrows()]
    best = {}
    for f in ("PTS", "FG_PCT", "PLUS_MINUS"):
        if f in bq.columns:
            vals = pd.to_numeric(bq[f], errors="coerce")
            if vals.notna().any():
                i = vals.idxmax()
                best[f] = {"quarter": QUARTER_NAMES.get(int(bq.loc[i, "QUARTER"])), "value": _num(vals[i], f)}
    return {"subject": disp, "season": season, "per_game_by_quarter": rows, "best_quarter_by": best,
            "note": "Per-game averages within each quarter. For a quarter's numbers game by game, use game_log or a "
                    "game_trend chart with quarter set."}


def tool_game_log(subject_type="player", name=None, season=None, last_n=10, stats=None, quarter=None):
    mode, rec, sid, disp, _ = _subject(subject_type, name)
    season = _season(season)
    q = _quarter(quarter)
    log = _period_log(mode, sid, season, q) if q else _game_log(mode, sid, season)
    if log.empty:
        raise ToolError(f"No games found for {disp} in {season}" + (f" ({QUARTER_NAMES[q]})." if q else "."))
    fields = [_resolve_stat(s, log.columns) for s in (stats or [])] or \
        [f for f in ["MIN", "PTS", "REB", "AST", "STL", "BLK", "TOV", "FGM", "FGA", "FG3M", "FG3A", "PLUS_MINUS"]
         if f in log.columns]
    n = max(1, min(int(last_n or 10), 82))
    rows = [{"date": str(r["GAME_DATE"]), "matchup": r.get("MATCHUP"), "result": r.get("WL"),
             **{f: _num(r[f], f) for f in fields}} for _, r in log.tail(n).iterrows()]
    avgs = {f: _num(pd.to_numeric(log[f], errors="coerce").mean(), f) for f in fields}
    for pct, (mk, at) in {"FG_PCT": ("FGM", "FGA"), "FG3_PCT": ("FG3M", "FG3A"), "FT_PCT": ("FTM", "FTA")}.items():
        if pct in fields and {mk, at}.issubset(log.columns):
            tot = pd.to_numeric(log[at], errors="coerce").sum()
            avgs[pct] = _num(pd.to_numeric(log[mk], errors="coerce").sum() / tot, pct) if tot else None
    best = log.loc[pd.to_numeric(log["PTS"], errors="coerce").idxmax()] if "PTS" in log else None
    return {"subject": disp, "season": season, "games_played": len(log),
            "stats_are_from": QUARTER_NAMES[q] + " only" if q else "whole games", "season_averages": avgs,
            "high_scoring_game": ({"date": str(best["GAME_DATE"]), "matchup": best.get("MATCHUP"),
                                   "PTS": _num(best["PTS"])} if best is not None else None),
            "record": (f"{int((log['WL'] == 'W').sum())}-{int((log['WL'] == 'L').sum())}" if "WL" in log else None),
            "games": rows}


def tool_league_leaders(subject_type="player", stat=None, season=None, per_mode="PerGame", top_n=10, ascending=None,
                        filters=None, show_stats=None):
    t = _rank_table(subject_type, stat, season, per_mode, top_n, ascending, filters, show_stats)
    fields = [t["field"]] + t["extra"] + (["GP"] if "GP" in t["top"] and t["field"] != "GP" else [])
    rows = []
    for i, (_, r) in enumerate(t["top"].iterrows(), 1):
        rows.append({"rank": i, **_row_out(r, fields, t["name_col"])})
    return {"stat": t["field"], "season": t["season"], "per_mode": t["per_mode"], "order": "lowest first" if t["ascending"] else "highest first",
            "qualified_pool": t["pool"], "qualification": t["notes"], "rows": rows}


def _zone_table(shots, league=None):
    if shots is None or shots.empty or "SHOT_ZONE_BASIC" not in shots:
        return []
    g = shots.groupby("SHOT_ZONE_BASIC").agg(FGA=("SHOT_MADE_FLAG", "size"), FGM=("SHOT_MADE_FLAG", "sum"))
    total = float(g["FGA"].sum()) or 1.0
    lg = {}
    if league is not None and not league.empty and {"SHOT_ZONE_BASIC", "FGA", "FGM"}.issubset(league.columns):
        lz = league.groupby("SHOT_ZONE_BASIC")[["FGA", "FGM"]].sum()
        lg = {z: (r["FGM"] / r["FGA"] if r["FGA"] else None) for z, r in lz.iterrows()}
    out = []
    for z, r in g.sort_values("FGA", ascending=False).iterrows():
        if z == "Backcourt":
            continue
        out.append({"zone": z, "FGA": int(r["FGA"]), "share_of_shots": round(r["FGA"] / total, 3),
                    "FG_PCT": round(r["FGM"] / r["FGA"], 3) if r["FGA"] else None,
                    "league_FG_PCT": round(lg[z], 3) if lg.get(z) is not None else None})
    return out


def _shots(mode, sid, season):
    shots = nba_data.get_player_shots(sid, season) if mode == "player" else nba_data.get_team_shots(sid, season)
    if shots is None or shots.empty:
        raise ToolError(f"No shot data for that {mode} in {season}.")
    return shots


def tool_shot_zones(subject_type="player", name=None, season=None):
    mode, rec, sid, disp, _ = _subject(subject_type, name)
    season = _season(season)
    shots = _shots(mode, sid, season)
    league = nba_data.get_zone_league_averages(season, **({"player_id": sid} if mode == "player" else {"team_id": sid}))
    made = pd.to_numeric(shots["SHOT_MADE_FLAG"], errors="coerce")
    dist = pd.to_numeric(shots.get("SHOT_DISTANCE"), errors="coerce") if "SHOT_DISTANCE" in shots else None
    return {"subject": disp, "season": season, "total_FGA": int(len(shots)), "FG_PCT": round(float(made.mean()), 3),
            "avg_shot_distance_ft": round(float(dist.mean()), 1) if dist is not None else None,
            "zones": _zone_table(shots, league)}


_SPECIAL = {
    "clutch": ("get_player_clutch_stats", ["GP", "MIN", "PTS", "FG_PCT", "FG3_PCT", "FT_PCT", "PLUS_MINUS"]),
    "hustle": ("get_player_hustle_stats", ["DEFLECTIONS", "CHARGES_DRAWN", "SCREEN_ASSISTS", "LOOSE_BALLS_RECOVERED",
                                           "CONTESTED_SHOTS", "BOX_OUTS"]),
    "defense": ("get_player_defense_stats", ["GP", "FREQ", "D_FGM", "D_FGA", "D_FG_PCT", "NORMAL_FG_PCT", "PCT_PLUSMINUS"]),
    "playtype": ("get_player_playtype_stats", ["PLAY_TYPE", "GP", "POSS", "FREQ", "PPP", "PTS", "FG_PCT", "PERCENTILE"]),
}
_PLAYTYPES = {"isolation": "Isolation", "iso": "Isolation", "pick and roll ball handler": "PRBallHandler",
              "pnr ball handler": "PRBallHandler", "pick and roll": "PRBallHandler", "roll man": "PRRollman",
              "pick and roll roll man": "PRRollman", "post up": "Postup", "post": "Postup", "spot up": "Spotup",
              "handoff": "Handoff", "hand off": "Handoff", "cut": "Cut", "cuts": "Cut", "transition": "Transition",
              "off screen": "OffScreen", "putback": "OffRebound", "putbacks": "OffRebound", "misc": "Misc"}


def tool_special_stats(kind="clutch", season=None, names=None, sort_by=None, top_n=10, play_type=None, stats=None):
    kind = _fold(kind).replace(" ", "")
    kind = {"playtypes": "playtype", "synergy": "playtype", "defence": "defense"}.get(kind, kind)
    if kind not in _SPECIAL:
        raise ToolError("kind must be one of: clutch, hustle, defense, playtype.")
    season = _season(season)
    fn_name, default_cols = _SPECIAL[kind]
    fn = getattr(nba_data, fn_name)
    if kind == "playtype":
        pt = _PLAYTYPES.get(_fold(play_type or ""), play_type or "Isolation")
        df = fn(season, play_type=pt)
    else:
        df = fn(season)
    if df is None or df.empty:
        raise ToolError(f"No {kind} data for {season}.")
    name_col = "PLAYER_NAME" if "PLAYER_NAME" in df.columns else df.columns[1]
    cols = [_resolve_stat(s, df.columns) for s in (stats or [])] or [c for c in default_cols if c in df.columns]
    if names:
        recs = [resolve_player(n) for n in names[:8]]
        id_col = next((c for c in ("PLAYER_ID", "CLOSE_DEF_PERSON_ID") if c in df.columns), None)
        if id_col:
            df = df[df[id_col].isin([r["id"] for r in recs])]
        else:
            wanted = {_fold(r["full_name"]) for r in recs}
            df = df[df[name_col].map(_fold).isin(wanted)]
    notes = []
    if not names:
        # real volume only -- otherwise a 1-for-1 clutch shooter or a one-game defender "leads the league"
        def _floor(col, minimum, label):
            nonlocal df
            if col in df.columns:
                df = df[pd.to_numeric(df[col], errors="coerce") >= minimum]
                notes.append(f"at least {minimum} {label}")
        _floor("GP", 10, "games")
        if kind == "defense":
            _floor("D_FGA", 150, "shots defended")
        elif kind == "playtype":
            _floor("POSS", 50, "possessions")
        elif kind == "clutch" and sort_by:
            fl = {"FG_PCT": ("FGA", 20), "FG3_PCT": ("FG3A", 10), "FT_PCT": ("FTA", 10)}.get(_resolve_stat(sort_by, df.columns))
            if fl:
                _floor(fl[0], fl[1], fl[0])
    sort_by = sort_by or {"clutch": "PTS", "hustle": "DEFLECTIONS", "defense": "PCT_PLUSMINUS", "playtype": "PPP"}[kind]
    if sort_by:
        f = _resolve_stat(sort_by, df.columns)
        df = df.assign(**{f: pd.to_numeric(df[f], errors="coerce")}).sort_values(f, ascending=f in BEST_IS_LOWEST)
        if f not in cols:
            cols = [f] + cols
    n = max(1, min(int(top_n or 10), 30))
    rows = [_row_out(r, cols, name_col) for _, r in df.head(n).iterrows()]
    return {"kind": kind, "season": season, "numbers": "season totals (not per game)", "qualification": notes,
            "sorted_by": sort_by, "rows": rows,
            "available_columns": [c for c in df.columns if not c.endswith("_RANK") and "_ID" not in c][:45]}


def tool_passing(player=None, season=None, top_n=8):
    _, rec, pid, disp, _ = _subject("player", player)
    season = _season(season)
    df = nba_data.get_player_passes(pid, season)
    if df is None or df.empty:
        raise ToolError(f"No passing data for {disp} in {season}.")
    df = df.copy()
    df["PASS"] = pd.to_numeric(df["PASS"], errors="coerce")
    cols = [c for c in ["PASS", "AST", "FGM", "FGA", "FG_PCT", "FG3M", "FG3A"] if c in df.columns]
    rows = []
    for _, r in df.sort_values("PASS", ascending=False).head(max(1, min(int(top_n or 8), 15))).iterrows():
        name = str(r["PASS_TO"])
        if "," in name:
            last, first = (p.strip() for p in name.split(",", 1))
            name = f"{first} {last}"
        rows.append({"to": name, **{c: _num(r[c], c) for c in cols}})
    return {"passer": disp, "season": season,
            "note": "season totals: passes to each teammate, and that teammate's shots right after those passes",
            "rows": rows}


def tool_lineups(team=None, season=None, size=5, sort_by="NET_RATING", min_minutes=20, top_n=10):
    t = resolve_team(team)
    season = _season(season)
    size = max(2, min(int(size or 5), 5))
    adv = nba_data.get_team_lineup_combos(t["id"], season, group_quantity=size, measure_type="Advanced")
    if adv is None or adv.empty:
        raise ToolError(f"No {size}-man lineup data for {t['full_name']} in {season}.")
    adv = adv.copy()
    adv["MIN"] = pd.to_numeric(adv.get("MIN"), errors="coerce")
    adv = adv[adv["MIN"] >= float(20 if min_minutes is None else min_minutes)]
    f = _resolve_stat(sort_by or "NET_RATING", adv.columns)
    adv = adv.assign(**{f: pd.to_numeric(adv[f], errors="coerce")}).sort_values(f, ascending=f in LOWER_IS_BETTER)
    cols = [c for c in ["MIN", "OFF_RATING", "DEF_RATING", "NET_RATING", "PACE", "TS_PCT"] if c in adv.columns]
    rows = [{"lineup": r["GROUP_NAME"], **{c: _num(r[c], c) for c in cols}}
            for _, r in adv.head(max(1, min(int(top_n or 10), 20))).iterrows()]
    return {"team": t["full_name"], "season": season, "size": size, "sorted_by": f, "rows": rows}


def tool_head_to_head(player=None, opponent=None, season=None):
    _, rec, pid, disp, _ = _subject("player", player)
    _, rec2, oid, odisp, _ = _subject("player", opponent)
    season = _season(season)
    df = nba_data.get_player_vs_player_onoff(pid, oid, season)
    if df is None or df.empty:
        raise ToolError(f"No head-to-head data for {disp} vs {odisp} in {season}.")
    cols = [c for c in ["GP", "MIN", "PTS", "REB", "AST", "STL", "BLK", "TOV", "FG_PCT", "FG3_PCT", "PLUS_MINUS"]
            if c in df.columns]
    rows = []
    for _, r in df.iterrows():
        rows.append({"opponent_on_court": str(r.get("COURT_STATUS", "")), **{c: _num(r[c], c) for c in cols}})
    return {"player": disp, "opponent": odisp, "season": season, "rows": rows,
            "note": f"season totals: {disp}'s stats with {odisp} on the court vs off it, in games between their teams"}


def tool_on_off(team=None, player_1=None, player_2=None, season=None):
    t = resolve_team(team)
    season = _season(season)
    r1, r2 = resolve_player(player_1), resolve_player(player_2)
    p1, p2 = r1["full_name"], r2["full_name"]
    combos = nba_data.get_team_lineup_combos(t["id"], season, group_quantity=2, measure_type="Advanced")
    if combos is None or "GROUP_NAME" not in combos.columns:
        raise ToolError("Couldn't load lineup data for that team/season.")
    if "GROUP_ID" in combos.columns:
        ids = (f"-{r1['id']}-", f"-{r2['id']}-")
        match = combos[combos["GROUP_ID"].astype(str).map(lambda g: all(i in f"-{g.strip('-')}-" for i in ids))]
    else:
        lasts = [_fold(p.split()[-1]) for p in (p1, p2)]
        match = combos[combos["GROUP_NAME"].map(lambda g: all(ln in _fold(g).split() for ln in lasts))]
    if match.empty:
        raise ToolError(f"No minutes found with {p1} and {p2} on the court together for {t['full_name']} in {season}.")
    r = match.iloc[0]
    team_df = nba_data.get_team_stats(season, per_mode="PerGame")
    tr = team_df[team_df["TEAM_ID"] == t["id"]]
    cols = [c for c in ["MIN", "OFF_RATING", "DEF_RATING", "NET_RATING", "PACE", "TS_PCT"] if c in match.columns]
    base = {c: _num(tr.iloc[0][c], c) for c in ["OFF_RATING", "DEF_RATING", "NET_RATING", "PACE"] if not tr.empty and c in tr}
    return {"team": t["full_name"], "season": season, "pair": [p1, p2],
            "together": {c: _num(r[c], c) for c in cols}, "team_season": base}


def tool_web_search(query=None):
    if not query:
        raise ToolError("No search query.")
    client = CTX.get("client")
    if client is None:
        raise ToolError("Web search isn't available right now.")
    try:
        resp = client.chat.completions.create(
            model=SEARCH_MODEL, max_tokens=900,
            messages=[{"role": "user", "content": f"Search the web and answer briefly and factually, naming your "
                                                  f"sources and dates: {query}"}])
        return {"query": query, "result": (resp.choices[0].message.content or "")[:4000]}
    except Exception as e:  # noqa: BLE001
        raise ToolError(f"Web search failed ({type(e).__name__}). Answer from your own knowledge and say it may be "
                        f"out of date.")


DATA_TOOLS = {
    "season_stats": tool_season_stats, "career_stats": tool_career_stats, "game_log": tool_game_log,
    "league_leaders": tool_league_leaders, "shot_zones": tool_shot_zones, "special_stats": tool_special_stats,
    "passing": tool_passing, "lineups": tool_lineups, "head_to_head": tool_head_to_head, "on_off": tool_on_off,
    "web_search": tool_web_search, "quarter_stats": tool_quarter_stats,
}


# ================================================================ visualizations

CHART_TYPES = ["leaderboard", "scatter", "shot_chart", "heat_map", "hex_shot_chart", "zone_map", "animated_shot_chart",
               "comparison", "career_trend", "game_trend", "radar", "distribution", "clutch_clock", "trade"]
COURT_STYLES = {"shot_chart": "Shot chart", "heat_map": "Heat map", "hex_shot_chart": "Hex shot chart",
                "zone_map": "Zone map", "animated_shot_chart": "Animated shot chart"}
QUARTER_OPTIONS = [None, 1, 2, 3, 4, 5]
BAR_STYLES = ["Vertical bars", "Horizontal bars", "Dot plot"]
PER_MODE_LABELS = {"PerGame": "Per game", "Totals": "Totals", "Per36": "Per 36"}


def _color(spec):
    """The chart's colour: the picked one, else the subject's own team colour, else the app default."""
    pick = spec.get("color")
    resolve = CTX["resolve_color_input"]
    if pick and pick != "Auto":
        return resolve(pick)
    p = spec["params"]
    names = p.get("names") or []
    if spec["kind"] in ("leaderboard", "scatter", "distribution") or not names:
        return "#D4AF37"            # league-wide charts: the site's gold
    try:
        mode, rec, sid, disp, _ = _subject(p.get("subject_type"), names[0])
        team = CTX["default_color_team"](mode, disp if mode == "team" else CTX["strip_accents"](disp),
                                         _season(p.get("season")))
        return resolve(team) if team else CTX["DEFAULT_COLOR"]
    except Exception:  # noqa: BLE001
        return CTX["DEFAULT_COLOR"]


def _image_url(mode, sid):
    return get_player_headshot_url(sid) if mode == "player" else get_team_logo_url(sid)


def _viz_leaderboard(p, color):
    t = _rank_table(p.get("subject_type"), p.get("stat"), p.get("season"), p.get("per_mode"), p.get("top_n", 10),
                    p.get("ascending"), p.get("filters"))
    top = t["top"]
    if top.empty:
        raise ToolError("Nobody qualifies for that ranking -- loosen a filter.")
    mode = t["subject_type"]
    lb = pd.DataFrame({"name": top[t["name_col"]].astype(str).values, "player_id": top[t["id_col"]].values,
                       "value": top[t["field"]].astype(float).values})
    lb["image_url"] = [_image_url(mode, i) for i in lb["player_id"]]
    lb["is_included"] = True
    is_pct = _is_pct(t["field"])
    style = p.get("style") or "Vertical bars"
    # the chart's own title adds "per game" for a counting stat; say "totals" / "per 36" instead when that's the mode
    shown_label, source = t["label"], "base"
    if t["per_mode"] != "PerGame" and not is_pct:
        shown_label, source = f"{t['label']} ({PER_MODE_LABELS[t['per_mode']].lower()})", "bio"
    if style == "Dot plot":
        fig = visuals.build_dot_plot(lb, stat_display_name=shown_label, season=t["season"], top_n=len(lb),
                                     team_color=color, included_names=[], stat_source=source, is_percentage=is_pct,
                                     rank_ascending=t["ascending"])
        hs = []
    else:
        orient = "vertical" if style == "Vertical bars" else "horizontal"
        fig = visuals.build_bar_chart(lb, stat_display_name=shown_label, season=t["season"], top_n=len(lb),
                                      team_color=color, included_names=[], orientation=orient, stat_source=source,
                                      is_percentage=is_pct, rank_ascending=t["ascending"])
        drawn = lb.sort_values("value", ascending=(orient == "horizontal")).reset_index(drop=True)
        hs = hover.bar_chart_hotspots(fig.axes[0], drawn["name"].tolist(), drawn["value"].tolist(), t["label"],
                                      orientation=orient, rank_ascending=t["ascending"], is_pct=is_pct)
    summary = {"stat": t["field"], "season": t["season"], "per_mode": t["per_mode"], "qualification": t["notes"],
               "ranked": [{"rank": i + 1, "name": n, "value": _num(v, t["field"])}
                          for i, (n, v) in enumerate(zip(lb["name"], lb["value"]))]}
    title = f"{t['label']} leaders, {t['season']}" + (f" ({PER_MODE_LABELS[t['per_mode']].lower()})" if mode == "player" else "")
    return fig, hs, summary, title


def _viz_scatter(p, color):
    subject_type = "team" if p.get("subject_type") == "team" else "player"
    season, per_mode = _season(p.get("season")), _per_mode(p.get("per_mode"))
    df, name_col, id_col = _table(subject_type, season, per_mode)
    xf, yf = _resolve_stat(p.get("x_stat"), df.columns), _resolve_stat(p.get("y_stat"), df.columns)
    df = df.copy()
    for f in (xf, yf):
        df[f] = pd.to_numeric(df[f], errors="coerce")
    df = df.dropna(subset=[xf, yf])
    df, _ = _apply_filters(df, p.get("filters"), season, per_mode)
    df, qnotes = _qualify(df, subject_type, per_mode, yf, p.get("filters"))
    top_n = max(3, min(int(p.get("top_n") or 25), 50))
    asc = yf in LOWER_IS_BETTER
    rank_f = _resolve_stat(p.get("rank_by"), df.columns) if p.get("rank_by") else yf
    if rank_f not in (xf, yf):
        df[rank_f] = pd.to_numeric(df[rank_f], errors="coerce")
    top = df.sort_values(rank_f, ascending=rank_f in LOWER_IS_BETTER).head(top_n)
    highlight = set()
    for n in p.get("names") or []:
        try:
            _, rec, sid, _, _ = _subject(subject_type, n)
            highlight.add(sid)
            if sid not in set(top[id_col]):
                top = pd.concat([top, df[df[id_col] == sid]])
        except ToolError:
            pass
    if top.empty:
        raise ToolError("No one to plot with those stats/filters.")
    sd = pd.DataFrame({"name": top[name_col].astype(str).values, "player_id": top[id_col].values,
                       "x_value": top[xf].astype(float).values, "y_value": top[yf].astype(float).values})
    sd["image_url"] = [_image_url(subject_type, i) for i in sd["player_id"]]
    sd["is_included"] = sd["player_id"].isin(highlight) if highlight else False
    pics = p.get("pictures")
    sd["show_image"] = sd["name"].isin(pics) if pics is not None else True
    xl, yl = stat_label(xf), stat_label(yf)
    fig, recs = visuals.build_scatter_plot(sd, stat_label_y=yl, stat_label_x=xl, dot_color=color,
                                           return_hotspot_data=True)
    hs = hover.criteria_scatter_hotspots(fig.axes[0], recs, xl, yl, stripe_color=color, noun=subject_type,
                                         x_higher_better=xf not in LOWER_IS_BETTER, y_higher_better=not asc)
    corr = sd["x_value"].corr(sd["y_value"]) if len(sd) > 2 else None
    summary = {"x": xf, "y": yf, "season": season, "per_mode": per_mode, "plotted": len(sd), "qualification": qnotes,
               "correlation": _num(corr, "X_PCT") if corr is not None else None,
               "top_by_y": sd.nlargest(3, "y_value")[["name", "y_value", "x_value"]].round(3).to_dict("records"),
               "top_by_x": sd.nlargest(3, "x_value")[["name", "x_value", "y_value"]].round(3).to_dict("records")}
    return fig, hs, summary, f"{yl} vs {xl}, {season}", sd["name"].tolist()


def _viz_court(p, color, kind):
    mode, rec, sid, disp, short = _subject(p.get("subject_type"), (p.get("names") or [None])[0])
    season = _season(p.get("season"))
    shots = _shots(mode, sid, season)
    ax_hs = []
    if kind == "shot_chart":
        fig = visuals.build_shot_chart(shots, color)
        ax_hs = hover.shot_chart_hotspots(fig.axes[0], shots, CTX["game_lookup"](mode, sid, season), mode == "team")
    elif kind == "heat_map":
        fig = visuals.build_heat_map(shots, color)
        lg = nba_data.get_zone_league_averages(season, **({"player_id": sid} if mode == "player" else {"team_id": sid}))
        ax_hs = hover.heat_map_hotspots(fig.axes[0], shots, lg, short)
    elif kind == "hex_shot_chart":
        league_shots = nba_data.get_league_shots(season)
        fig, hex_records = visuals.build_hex_shot_chart(shots, league_shots, color, return_hotspot_data=True)
        ax_hs = hover.hex_chart_hotspots(fig.axes[0], hex_records, short)
    else:
        fig = visuals.build_court_zone_map(shots, disp, "FG%")
    made = pd.to_numeric(shots["SHOT_MADE_FLAG"], errors="coerce")
    summary = {"subject": disp, "season": season, "total_FGA": int(len(shots)), "FG_PCT": _num(made.mean(), "FG_PCT"),
               "zones": _zone_table(shots)}
    return fig, ax_hs, summary, f"{disp} -- {COURT_STYLES[kind]}, {season}"


def _viz_comparison(p, color):
    subject_type = "team" if p.get("subject_type") == "team" else "player"
    season, per_mode = _season(p.get("season")), _per_mode(p.get("per_mode"))
    df, name_col, id_col = _table(subject_type, season, per_mode)
    wanted = p.get("stats") or (["PTS", "REB", "AST", "STL", "BLK", "TS_PCT"] if subject_type == "player"
                                else ["PTS", "REB", "AST", "OFF_RATING", "DEF_RATING", "NET_RATING"])
    fields = []
    for s in wanted[:8]:
        f = _resolve_stat(s, df.columns)
        if f not in fields:
            fields.append(f)
    names, values, rows = [], [], []
    for n in (p.get("names") or [])[:6]:
        mode, rec, sid, disp, short = _subject(subject_type, n)
        r = df[df[id_col] == sid]
        if r.empty:
            continue
        r = r.iloc[0]
        names.append(disp)
        values.append([None if pd.isna(r[f]) else float(r[f]) for f in fields])
        rows.append({"name": disp, **{f: _num(r[f], f) for f in fields}})
    if len(names) < 1:
        raise ToolError(f"None of those {subject_type}s have {season} stats.")
    labels = [stat_label(f) for f in fields]
    fig, recs = visuals.build_comparison_bars(names, labels, values, color, [_is_pct(f) for f in fields],
                                              return_hotspot_data=True)
    ax = fig.axes[0]
    hs = []
    for r in recs:
        f = fields[labels.index(r["stat"])]
        others = [(names[i], values[i][fields.index(f)]) for i in range(len(names))]
        tip = interactive.stat_line_tip(r["name"], [f"{r['stat']}: {_fmt(r['value'], f)}"] +
                                        [f"{n}: {_fmt(v, f)}" for n, v in others if n != r["name"]])
        hs.append({"ax": ax, "shape": "rect", "x0": r["x0"], "x1": r["x1"], "y0": r["y0"], "y1": r["y1"], "tooltip": tip})
    return fig, hs, {"season": season, "per_mode": per_mode, "rows": rows}, " vs ".join(names) + f", {season}"


def _viz_career_trend(p, color):
    per_mode = _per_mode(p.get("per_mode"))
    stat = p.get("stat") or "PTS"
    series, all_seasons, field, rows = [], set(), None, {}
    for n in (p.get("names") or [])[:6]:
        _, rec, pid, disp, _ = _subject("player", n)
        seasons, _ = _career_rows(pid, per_mode)
        if seasons.empty:
            continue
        field = field or _resolve_stat(stat, seasons.columns)
        vals = {str(r["SEASON_ID"]): (None if pd.isna(r[field]) else float(r[field])) for _, r in seasons.iterrows()}
        all_seasons.update(vals)
        series.append((disp, vals))
        rows[disp] = {k: _num(v, field) for k, v in vals.items()}
    if not series:
        raise ToolError("No career data for those players.")
    xs = sorted(all_seasons)
    fig, pts = visuals.build_multi_line_chart(xs, [(n, [v.get(s) for s in xs]) for n, v in series],
                                              f"{stat_label(field)} ({PER_MODE_LABELS[per_mode].lower()})", color,
                                              is_percentage=_is_pct(field), return_hotspot_data=True)
    ax = fig.axes[0]
    hs = [{"ax": ax, "shape": "circle", "x": q["x"], "y": q["y"], "r_px": 9,
           "tooltip": interactive.stat_line_tip(q["name"], [f"{q['label']}: {_fmt(q['y'], field)} {stat_label(field)}"])}
          for q in pts]
    return fig, hs, {"stat": field, "per_mode": per_mode, "by_season": rows}, \
        f"{stat_label(field)} by season -- " + ", ".join(n for n, _ in series)


def _viz_game_trend(p, color):
    mode, rec, sid, disp, short = _subject(p.get("subject_type"), (p.get("names") or [None])[0])
    season = _season(p.get("season"))
    q = _quarter(p.get("quarter"))
    log = _period_log(mode, sid, season, q) if q else _game_log(mode, sid, season)
    if log.empty:
        raise ToolError(f"No games found for {disp} in {season}" + (f" ({QUARTER_NAMES[q]})." if q else "."))
    field = _resolve_stat(p.get("stat") or "PTS", log.columns)
    series = pd.to_numeric(log[field], errors="coerce")
    if _is_pct(field):
        keep = series.notna()
        log, series = log[keep].reset_index(drop=True), series[keep].reset_index(drop=True)
        if log.empty:
            raise ToolError(f"No games with attempts for {stat_label(field)}.")
    vals = series.fillna(0).tolist()
    dates = log["GAME_DATE"].tolist()
    is_pct = _is_pct(field)
    shown_label = stat_label(field) + (f" ({QUARTER_NAMES[q]})" if q else "")
    fig = visuals.build_line_chart(dates, vals, stat_display_name=shown_label, subject_name=disp, season=season,
                                   team_color=color, is_percentage=is_pct, rolling_window=5)
    hs = hover.season_trend_hotspots(fig.axes[0], list(range(len(vals))), dates, vals, shown_label,
                                     CTX["game_lookup"](mode, sid, season), display_values=vals, is_pct=is_pct)
    s = pd.Series(vals)
    i_hi, i_lo = int(s.idxmax()), int(s.idxmin())
    summary = {"subject": disp, "season": season, "stat": field, "games": len(vals), "average": _num(s.mean(), field),
               "last_5_average": _num(s.tail(5).mean(), field),
               "high": {"value": _num(s[i_hi], field), "date": str(dates[i_hi]), "matchup": log.loc[i_hi].get("MATCHUP")},
               "low": {"value": _num(s[i_lo], field), "date": str(dates[i_lo]), "matchup": log.loc[i_lo].get("MATCHUP")}}
    if q:
        summary["stats_are_from"] = QUARTER_NAMES[q] + " only"
    return fig, hs, summary, f"{disp} -- {shown_label} game by game, {season}"


def _viz_radar(p, color):
    subject_type = "team" if p.get("subject_type") == "team" else "player"
    season, per_mode = _season(p.get("season")), _per_mode(p.get("per_mode"))
    df, name_col, id_col = _table(subject_type, season, per_mode)
    df = df.copy()
    need = {"PTS", "AST", "REB", "STL", "BLK", "TS_PCT"}
    if not need.issubset(df.columns):
        raise ToolError("The stats this profile needs aren't in the data.")
    pool, _ = _qualify(df, subject_type, per_mode, "PTS", {})
    pool = pool.copy()
    pool["_DEF"] = pool["STL"] + pool["BLK"]
    df["_DEF"] = df["STL"] + df["BLK"]
    cats = [("Scoring", "PTS"), ("Playmaking", "AST"), ("Rebounding", "REB"), ("Defense", "_DEF"), ("Efficiency", "TS_PCT")]
    subjects = []
    for n in (p.get("names") or [])[:2]:
        mode, rec, sid, disp, _ = _subject(subject_type, n)
        r = df[df[id_col] == sid]
        if r.empty:
            continue
        r = r.iloc[0]
        pcts = [float((pool[c] < r[c]).mean() * 100) for _, c in cats]
        subjects.append((disp, sid, r, pcts))
    if not subjects:
        raise ToolError(f"No {season} stats for that {subject_type}.")
    (d1, s1, r1, p1) = subjects[0]
    second = subjects[1] if len(subjects) > 1 else None
    fig = visuals.build_radar_chart([c for c, _ in cats], p1, d1, color,
                                    second_percentiles=second[3] if second else None,
                                    second_name=second[0] if second else None,
                                    image_url=_image_url(subject_type, s1),
                                    second_image_url=_image_url(subject_type, second[1]) if second else None)
    lines = [[f"{r1['PTS']:.1f} PTS"], [f"{r1['AST']:.1f} AST"], [f"{r1['REB']:.1f} REB"],
             [f"{r1['STL']:.1f} STL + {r1['BLK']:.1f} BLK"], [f"{r1['TS_PCT']:.1%} TS%"]]
    hs = hover.radar_hotspots(fig.axes[0], [c for c, _ in cats], p1, lines)
    summary = {"season": season, "percentiles_vs_league": {d: {c: round(v) for (c, _), v in zip(cats, pc)}
                                                           for d, _, _, pc in subjects}}
    return fig, hs, summary, f"{' vs '.join(s[0] for s in subjects)} -- profile, {season}"


def _viz_distribution(p, color):
    subject_type = "team" if p.get("subject_type") == "team" else "player"
    season, per_mode = _season(p.get("season")), _per_mode(p.get("per_mode"))
    df, name_col, id_col = _table(subject_type, season, per_mode)
    field = _resolve_stat(p.get("stat"), df.columns)
    df = df.copy()
    df[field] = pd.to_numeric(df[field], errors="coerce")
    df = df.dropna(subset=[field])
    pool, qnotes = _qualify(df, subject_type, per_mode, field, p.get("filters"))
    vals = pool[field].astype(float).tolist()
    if len(vals) < 3:
        raise ToolError("Not enough qualified players to show a distribution.")
    is_pct = _is_pct(field)
    # the league is drawn in the chosen colour (a muted grey by default) so the marked players' lines stand out
    bars = color if spec_color_picked(p) else "#6f6f6f"
    fig = visuals.build_histogram(vals, stat_label(field), season, bars, is_percentage=is_pct)
    ax = fig.axes[0]
    ymax = ax.get_ylim()[1]
    hs, marks = [], []
    palette = [c for c in ["#D4AF37", "#5AA9E6", "#E07A5F", "#81B29A", "#C77DFF", "#FFFFFF"]
               if c.lower() != str(bars).lower()]
    for k, n in enumerate((p.get("names") or [])[:5]):
        try:
            mode, rec, sid, disp, short = _subject(subject_type, n)
        except ToolError:
            continue
        r = df[df[id_col] == sid]
        if r.empty:
            continue
        v = float(r.iloc[0][field])
        pct = float((pd.Series(vals) < v).mean() * 100)
        rank = _league_rank(pool, field, v, field not in LOWER_IS_BETTER)
        c = palette[k % len(palette)]
        ax.axvline(v, color=c, linewidth=2.2, zorder=4)
        ax.text(v, ymax * (0.88 - 0.07 * k), f" {short} ", color="#111111", fontsize=9, fontweight="bold",
                ha="center", va="center", zorder=5, bbox=dict(boxstyle="round,pad=0.25", fc=c, ec="none"))
        tip = interactive.stat_line_tip(disp, [f"{stat_label(field)}: {_fmt(v, field)}",
                                               f"Better than {pct:.0f}% of the league"] + ([f"Rank {rank}"] if rank else []))
        hs.append({"ax": ax, "shape": "path", "points": [(v, 0), (v, ymax)], "stroke_px": 14, "tooltip": tip})
        marks.append({"name": disp, "value": _num(v, field), "percentile": round(pct), "rank": rank})
    summary = {"stat": field, "season": season, "per_mode": per_mode, "qualified": len(vals), "qualification": qnotes,
               "league_mean": _num(np.mean(vals), field), "league_median": _num(np.median(vals), field), "marked": marks}
    return fig, hs, summary, f"{stat_label(field)} across the league, {season}"


def spec_color_picked(p):
    return bool(p.get("_color_picked"))


def _viz_clutch_clock(p, color):
    mode, rec, sid, disp, short = _subject(p.get("subject_type"), (p.get("names") or [None])[0])
    season = _season(p.get("season"))
    bq = nba_data.get_player_stats_by_quarter(sid, season) if mode == "player" else nba_data.get_team_stats_by_quarter(sid, season)
    if bq is None or bq.empty or len(bq) < 4 or not {"PTS", "FG_PCT", "PLUS_MINUS"}.issubset(bq.columns):
        raise ToolError(f"Couldn't load quarter-by-quarter stats for {disp} in {season}.")
    bq = bq.sort_values("QUARTER")
    qs = [{"PTS": float(r["PTS"]), "FG_PCT": float(r["FG_PCT"]), "PLUS_MINUS": float(r["PLUS_MINUS"])} for _, r in bq.iterrows()]
    fig = visuals.build_impact_clock(qs, disp, color)
    try:
        logs = nba_data.get_quarter_game_logs(mode, sid, season)
    except Exception:  # noqa: BLE001
        logs = {}
    hs = hover.clutch_clock_hotspots(fig.axes[0], qs, logs)
    return fig, hs, {"subject": disp, "season": season, "by_quarter": qs}, f"{disp} -- by quarter, {season}"


def _viz_trade(p, color):
    t1, t2 = resolve_team(p.get("team_1")), resolve_team(p.get("team_2"))
    season = _season(p.get("season"))
    stats = nba_data.get_player_stats(season, per_mode="PerGame")
    sends_a = [resolve_player(n)["full_name"] for n in (p.get("team_1_sends") or [])]
    sends_b = [resolve_player(n)["full_name"] for n in (p.get("team_2_sends") or [])]
    ids = {CTX["strip_accents"](r["full_name"]): r["id"] for r in CTX["PLAYER_NAME_TO_RECORD"].values()}
    ids.update({r["full_name"]: r["id"] for r in CTX["PLAYER_NAME_TO_RECORD"].values()})
    fig = visuals.build_trade_breakdown_image(t1["full_name"], t2["full_name"], sends_a=sends_a, sends_b=sends_b,
                                              stats_df=stats, player_ids=ids, salary_data=CTX["load_salary_data"]())
    lines = {}
    for n in sends_a + sends_b:
        r = stats[stats["PLAYER_ID"] == ids.get(n)]
        if not r.empty:
            lines[n] = {f: _num(r.iloc[0][f], f) for f in ("PTS", "REB", "AST", "TS_PCT") if f in r.columns}
    return fig, [], {"season": season, "team_1_sends": sends_a, "team_2_sends": sends_b, "per_game": lines}, \
        f"Trade: {t1['nickname']} ↔ {t2['nickname']}"


def build_animated(spec):
    """-> (GIF bytes, summary, title): every shot of the season appearing in game order (the Animated Shot Chart)."""
    p = spec["params"]
    mode, rec, sid, disp, _ = _subject(p.get("subject_type"), (p.get("names") or [None])[0])
    season = _season(p.get("season"))
    shots = _shots(mode, sid, season)
    need = {"GAME_DATE", "PERIOD", "MINUTES_REMAINING", "SECONDS_REMAINING", "LOC_X", "LOC_Y", "SHOT_MADE_FLAG"}
    if not need.issubset(shots.columns):
        raise ToolError("The shot data is missing the game clock this animation needs.")
    buf = visuals.build_animated_shot_chart(shots, _color(spec))
    made = pd.to_numeric(shots["SHOT_MADE_FLAG"], errors="coerce")
    summary = {"subject": disp, "season": season, "shots": int(len(shots)), "FG_PCT": round(float(made.mean()), 3)}
    return buf.getvalue(), summary, f"{disp} -- every shot in order, {season}"


def _render_gif(spec, chart_id):
    """The animated chart's GIF -- kept per chart and only rebuilt when one of its settings changes."""
    h = _spec_hash(spec)
    hit = st.session_state.get("ai_gif", {}).get(chart_id)
    if hit and hit[0] == h:
        return hit[1]
    gif, summary, title = build_animated(spec)
    spec["title"] = spec["params"].get("title") or title
    cache = st.session_state.setdefault("ai_gif", {})
    cache.pop(chart_id, None)
    cache[chart_id] = (h, gif)
    while len(cache) > 4:
        cache.pop(next(iter(cache)))
    return gif


def build_chart(spec):
    """-> (fig, hotspots, summary, title, extra) for a chart spec."""
    kind = spec["kind"]
    if kind == "animated_shot_chart":
        raise ToolError("(the animated shot chart is a GIF, drawn by build_animated)")
    p = dict(spec["params"], _color_picked=bool(spec.get("color") and spec.get("color") != "Auto"))
    color = _color(spec)
    extra = None
    if kind == "leaderboard":
        fig, hs, summary, title = _viz_leaderboard(p, color)
    elif kind == "scatter":
        fig, hs, summary, title, extra = _viz_scatter(p, color)
    elif kind in COURT_STYLES:
        fig, hs, summary, title = _viz_court(p, color, kind)
    elif kind == "comparison":
        fig, hs, summary, title = _viz_comparison(p, color)
    elif kind == "career_trend":
        fig, hs, summary, title = _viz_career_trend(p, color)
    elif kind == "game_trend":
        fig, hs, summary, title = _viz_game_trend(p, color)
    elif kind == "radar":
        fig, hs, summary, title = _viz_radar(p, color)
    elif kind == "distribution":
        fig, hs, summary, title = _viz_distribution(p, color)
    elif kind == "clutch_clock":
        fig, hs, summary, title = _viz_clutch_clock(p, color)
    elif kind == "trade":
        fig, hs, summary, title = _viz_trade(p, color)
    else:
        raise ToolError(f"Unknown chart_type '{kind}'. Use one of: {', '.join(CHART_TYPES)}.")
    return fig, hs or [], summary, p.get("title") or title, extra


def _spec_hash(spec):
    return hashlib.md5(json.dumps({"k": spec["kind"], "p": spec["params"], "c": spec.get("color")},
                                  sort_keys=True, default=str).encode()).hexdigest()


def _html_from(fig, hs, title, chart_id):
    """fig -> the chart's interactive page. Always white chart text here (the chat is dark), whatever "Chart Color"
    another page was left on."""
    prev = st.session_state.get("_global_chart_text_color")
    try:
        st.session_state["_global_chart_text_color"] = "white"
        ui_hooks.prepare_figure(fig)
        name = f"bradley-analytics-{re.sub(r'[^a-z0-9]+', '-', str(title).lower()).strip('-')[:60] or 'chart'}.png"
        return interactive.build_html_doc(fig, hs, f"ai_{chart_id}", file_name=name,
                                          fallback_sizing=not hasattr(st, "iframe"))
    finally:
        if prev is None:
            st.session_state.pop("_global_chart_text_color", None)
        else:
            st.session_state["_global_chart_text_color"] = prev
        plt.close(fig)


def _store_html(chart_id, h, html, height):
    cache = st.session_state.setdefault("ai_html", {})
    cache.pop(chart_id, None)
    cache[chart_id] = (h, html, height)
    while len(cache) > HTML_CACHE_SIZE:
        cache.pop(next(iter(cache)))


def _render_html(spec, chart_id):
    """The chart's interactive page -- kept per chart, and only redrawn when one of its settings changes."""
    h = _spec_hash(spec)
    hit = st.session_state.get("ai_html", {}).get(chart_id)
    if hit and hit[0] == h:
        return hit[1], hit[2]
    fig, hs, summary, title, extra = build_chart(spec)
    spec["title"] = title
    if extra is not None:
        spec["_names"] = extra
    html, height = _html_from(fig, hs, title, chart_id)
    _store_html(chart_id, h, html, height)
    return html, height


def tool_create_visualization(**args):
    kind = (args.pop("chart_type", None) or "").strip()
    kind = {"bar": "leaderboard", "bar_chart": "leaderboard", "ranking": "leaderboard", "shotchart": "shot_chart",
            "heatmap": "heat_map", "hex": "hex_shot_chart", "zones": "zone_map", "compare": "comparison",
            "career": "career_trend", "trend": "game_trend", "line": "game_trend", "histogram": "distribution",
            "impact_clock": "clutch_clock", "quarters": "clutch_clock", "season_trend": "game_trend",
            "animated": "animated_shot_chart", "animation": "animated_shot_chart",
            "animated_shots": "animated_shot_chart"}.get(kind, kind)
    if kind not in CHART_TYPES:
        raise ToolError(f"chart_type must be one of: {', '.join(CHART_TYPES)}.")
    color = args.pop("color", None)
    note = str(args.pop("note", None) or "").strip()
    params = {k: v for k, v in args.items() if v not in (None, "", [])}
    if "quarter" in params:
        params["quarter"] = _quarter(params["quarter"])
        if params["quarter"] is None:
            params.pop("quarter")
    if "name" in params and "names" not in params:
        params["names"] = [params.pop("name")]
    if isinstance(params.get("names"), str):
        params["names"] = [params["names"]]
    if kind not in ("career_trend", "trade"):
        params["season"] = _season(params.get("season"))
    if kind in ("leaderboard", "scatter", "comparison", "career_trend", "radar", "distribution"):
        params["per_mode"] = _per_mode(params.get("per_mode"))
    if kind in ("leaderboard", "scatter"):
        try:
            n = int(float(params.get("top_n") or (10 if kind == "leaderboard" else 25)))
        except (TypeError, ValueError):
            n = 10 if kind == "leaderboard" else 25
        params["top_n"] = max(3, min(n, 50))
    if kind == "leaderboard":
        params.setdefault("style", "Vertical bars")
    spec = {"kind": kind, "params": params, "color": color if color else "Auto"}
    if note:
        spec["note"] = note[:300]
    chart_id = uuid.uuid4().hex[:10]
    if kind == "animated_shot_chart":
        # checked now (a clear error for a bad name or season); the GIF itself takes a while, so it is drawn when the
        # answer is shown, not while the model waits
        mode, rec, sid, disp, _ = _subject(params.get("subject_type"), (params.get("names") or [None])[0])
        shots = _shots(mode, sid, params["season"])
        made = pd.to_numeric(shots["SHOT_MADE_FLAG"], errors="coerce")
        spec["title"] = params.get("title") or f"{disp} -- every shot in order, {params['season']}"
        st.session_state.setdefault("ai_charts", {})[chart_id] = spec
        return {"status": "animated chart created; it is shown to the user under your answer", "title": spec["title"],
                "data": {"subject": disp, "season": params["season"], "shots": int(len(shots)),
                         "FG_PCT": round(float(made.mean()), 3)}}, chart_id
    fig, hs, summary, title, extra = build_chart(spec)     # validates + gives the model the numbers
    spec["title"] = title
    if extra is not None:
        spec["_names"] = extra
    try:                                                   # ...and the same drawing is what gets shown
        html, height = _html_from(fig, hs, title, chart_id)
        _store_html(chart_id, _spec_hash(spec), html, height)
    except Exception:  # noqa: BLE001 -- it is simply drawn again when shown
        plt.close(fig)
    st.session_state.setdefault("ai_charts", {})[chart_id] = spec
    return {"status": "chart created and shown to the user under your answer", "title": title, "data": summary}, chart_id


# ================================================================ model tool definitions

def _fn(name, desc, props, required=()):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": list(required)}}}


_S = {"type": "string"}
_SEASON = {"type": "string", "description": "YYYY-YY, e.g. 2024-25"}
_SUBJ = {"type": "string", "enum": ["player", "team"]}
_NAMES = {"type": "array", "items": {"type": "string"}}
_PERMODE = {"type": "string", "enum": ["PerGame", "Totals", "Per36"]}
_STATS = {"type": "array", "items": {"type": "string"}, "description": "stat field names, e.g. PTS, FG3_PCT, TS_PCT"}
_QUARTER = {"type": "string", "description": "1, 2, 3, 4 or OT -- only that quarter's stats; leave out for whole games"}
_FILTERS = {"type": "object", "description": "optional player filters", "properties": {
    "position": {"type": "string", "description": "G, F or C"}, "team": _S,
    "min_age": {"type": "number"}, "max_age": {"type": "number"},
    "min_height_inches": {"type": "number"}, "max_height_inches": {"type": "number"},
    "min_games": {"type": "number"},
    "stat_filters": {"type": "array", "items": {"type": "object", "properties": {
        "stat": _S, "min": {"type": "number"}, "max": {"type": "number"}}}}}}

TOOLS = [
    _fn("ask_clarifying_questions",
        "Ask the user for missing details BEFORE answering (e.g. which season). Put every question in ONE call, "
        "each with 2-5 short clickable options.",
        {"questions": {"type": "array", "items": {"type": "object", "properties": {
            "question": _S, "options": {"type": "array", "items": _S}}, "required": ["question"]}}}, ["questions"]),
    _fn("season_stats", "Season stats (and league ranks) for specific players or teams.",
        {"subject_type": _SUBJ, "names": _NAMES, "season": _SEASON, "per_mode": _PERMODE, "stats": _STATS},
        ["names", "season"]),
    _fn("career_stats", "A player's season-by-season and career stats (regular season, or playoffs).",
        {"player": _S, "per_mode": _PERMODE, "stats": _STATS, "playoffs": {"type": "boolean"}}, ["player"]),
    _fn("game_log", "Game-by-game results/stats for a player or team in a season, plus averages and record. Set "
        "quarter (1-4, or OT) for the stats from that quarter only in every game.",
        {"subject_type": _SUBJ, "name": _S, "season": _SEASON, "last_n": {"type": "integer"}, "stats": _STATS,
         "quarter": _QUARTER}, ["name", "season"]),
    _fn("quarter_stats", "A player's or team's per-game stats inside each quarter (1st-4th) of a season, and which "
        "quarter is best by points, FG% and plus-minus. Use for 'best quarter', 'fourth-quarter scoring' etc.",
        {"subject_type": _SUBJ, "name": _S, "season": _SEASON}, ["name", "season"]),
    _fn("league_leaders", "Rank all players or teams by one stat, with optional filters (position, age, height, "
        "stat ranges, team). Sensible minimums apply automatically.",
        {"subject_type": _SUBJ, "stat": _S, "season": _SEASON, "per_mode": _PERMODE, "top_n": {"type": "integer"},
         "ascending": {"type": "boolean", "description": "true = lowest first"}, "filters": _FILTERS,
         "show_stats": _STATS}, ["stat", "season"]),
    _fn("shot_zones", "Where a player/team shoots from: attempts, share and FG% by court zone vs league average.",
        {"subject_type": _SUBJ, "name": _S, "season": _SEASON}, ["name", "season"]),
    _fn("special_stats", "League tables: clutch (last 5 min, within 5 pts), hustle (deflections, charges, screen "
        "assists), defense (opponent FG% when guarded), playtype (isolation, pick and roll, spot up, post up, "
        "transition, cut...). Filter by names or sort.",
        {"kind": {"type": "string", "enum": ["clutch", "hustle", "defense", "playtype"]}, "season": _SEASON,
         "names": _NAMES, "sort_by": _S, "top_n": {"type": "integer"}, "play_type": _S, "stats": _STATS},
        ["kind", "season"]),
    _fn("passing", "Who a player passes to most, and the shots those teammates take right after.",
        {"player": _S, "season": _SEASON, "top_n": {"type": "integer"}}, ["player", "season"]),
    _fn("lineups", "A team's best/worst 2- to 5-man lineups (net/off/def rating, minutes).",
        {"team": _S, "season": _SEASON, "size": {"type": "integer"}, "sort_by": _S,
         "min_minutes": {"type": "number"}, "top_n": {"type": "integer"}}, ["team", "season"]),
    _fn("on_off", "How a team does with two specific teammates on the floor together (ratings, minutes).",
        {"team": _S, "player_1": _S, "player_2": _S, "season": _SEASON}, ["team", "player_1", "player_2", "season"]),
    _fn("head_to_head", "A player's stats with a specific opposing player on vs off the court.",
        {"player": _S, "opponent": _S, "season": _SEASON}, ["player", "opponent", "season"]),
    _fn("web_search", "Search the web: news, injuries, trades, contracts, awards, history, rules, anything recent or "
        "not in the stats tools.", {"query": _S}, ["query"]),
    _fn("create_visualization",
        "Draw the chart that answers the question; it is shown under your answer with controls for colour, style, "
        "season and more. Types: leaderboard (rank one stat; stat, top_n, filters), scatter (x_stat vs y_stat; "
        "names = highlight), shot_chart / heat_map / hex_shot_chart / zone_map (where one player/team shoots), "
        "comparison (2-6 names across several stats), career_trend (one stat across a player's seasons, up to 6 "
        "players), game_trend (one stat game by game in a season; set quarter for one quarter's numbers, e.g. 4th-"
        "quarter points), radar (all-round profile, 1-2 names), distribution (one stat across the league, names "
        "marked), clutch_clock (a player/team by quarter), animated_shot_chart (every shot of a season appearing in "
        "order), trade. If no type answers the question exactly, draw the closest one and say so in note.",
        {"chart_type": {"type": "string", "enum": CHART_TYPES}, "subject_type": _SUBJ, "names": _NAMES,
         "season": _SEASON, "stat": _S, "stats": _STATS, "x_stat": _S, "y_stat": _S,
         "rank_by": {"type": "string", "description": "scatter: stat that picks the top_n plotted (default y_stat), "
                                                         "e.g. PTS for 'top 30 scorers'"},
         "per_mode": _PERMODE,
         "top_n": {"type": "integer"}, "ascending": {"type": "boolean"}, "filters": _FILTERS,
         "team_1": _S, "team_2": _S, "team_1_sends": _NAMES, "team_2_sends": _NAMES, "quarter": _QUARTER,
         "title": _S,
         "note": {"type": "string", "description": "one short sentence shown above the chart -- REQUIRED when this "
                                                   "is only the closest chart to what was asked, saying what it shows "
                                                   "instead"}}, ["chart_type"]),
]


def _allow_null(schema):
    """Groq checks every generated tool call against its schema, and models often send an explicit null for an optional
    argument they aren't using -- which fails the whole request unless null is allowed. So every optional argument
    (at any depth) also accepts null."""
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    for name, prop in props.items():
        if prop.get("type") == "object":
            _allow_null(prop)
        if prop.get("type") == "array" and isinstance(prop.get("items"), dict) and prop["items"].get("type") == "object":
            _allow_null(prop["items"])
        if name not in required and isinstance(prop.get("type"), str):
            prop["type"] = [prop["type"], "null"]
            if "enum" in prop and None not in prop["enum"]:
                prop["enum"] = list(prop["enum"]) + [None]
    return schema


for _t in TOOLS:   # (a deep copy each: the property dicts above are shared between tools)
    _t["function"]["parameters"] = _allow_null(json.loads(json.dumps(_t["function"]["parameters"])))


def system_prompt():
    path = os.path.join(os.path.dirname(__file__), "..", "ai_assistant", "system_prompt.md")
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        text = "You are Bradley, an NBA analytics assistant. Today is {TODAY}; the current season is {CURRENT_SEASON}."
    cur = stats_config.current_season()
    y = int(cur[:4])
    return (text.replace("{TODAY}", stats_config._today_eastern().strftime("%B %d, %Y"))
                .replace("{CURRENT_SEASON}", cur).replace("{LAST_SEASON}", f"{y - 1}-{str(y)[-2:]}")
                .replace("{NEXT_SEASON}", f"{y + 1}-{str(y + 2)[-2:]}"))


# ================================================================ the model loop

def _make_client(api_key):
    from groq import Groq
    return Groq(api_key=api_key)


def _history_for_model(messages, limit=14):
    out = []
    for m in messages[-limit:]:
        text = m.get("content") or ""
        if m["role"] == "assistant":
            if m.get("questions"):
                text += "\n" + "\n".join(f"- {q.get('question')}" + (
                    f" (options: {', '.join(str(o) for o in (q.get('options') or []))})" if q.get("options") else "")
                    for q in m["questions"])
            titles = [st.session_state.get("ai_charts", {}).get(c, {}).get("title") for c in m.get("charts", [])]
            if any(titles):
                text += "\n[Charts shown: " + "; ".join(t for t in titles if t) + "]"
        out.append({"role": m["role"], "content": text or "(empty)"})
    return out


class RequestTooLarge(Exception):
    pass


def _model_error_text(e):
    import groq as groq_module
    if isinstance(e, groq_module.RateLimitError):
        return "Groq's rate limit was hit -- wait about a minute and ask again."
    if isinstance(e, RequestTooLarge):
        return ("this question needed more text than the Groq plan allows per minute -- ask a narrower question, or "
                "start a New chat.")
    if isinstance(e, groq_module.AuthenticationError):
        return "Groq rejected the API key -- double-check GROQ_API_KEY in the app's secrets."
    if isinstance(e, groq_module.NotFoundError):
        return (f"Groq no longer offers the model `{MODEL}` -- update MODEL in streamlit/ai_search.py to a current "
                "tool-calling model from console.groq.com/docs/models.")
    return f"{type(e).__name__}: {e}"


def _shrink(messages, limit):
    """Shortens the longest tool results so a request fits the plan's per-request size."""
    for m in messages:
        if m.get("role") == "tool" and len(m.get("content") or "") > limit:
            m["content"] = m["content"][:limit] + ' ..."(trimmed)"'


def _call_model(client, messages, tool_choice="auto"):
    """One model call. A rate limit is waited out (twice at most); a tool call the model wrote badly (Groq's
    "tool_use_failed") is simply asked again. tool_choice: "auto", "none" (text only) or one tool forced."""
    import groq as groq_module
    waits, max_tokens, shrunk = 0, 3500, 0
    for attempt in range(6):
        try:
            return client.chat.completions.create(model=MODEL, max_tokens=max_tokens, messages=messages, tools=TOOLS,
                                                  tool_choice=tool_choice)
        except groq_module.RateLimitError as e:
            waits += 1
            if waits > 2:
                raise
            m = re.search(r"try again in (?:(\d+)m)?([\d.]+)(m?s)", str(e))
            if m:
                wait = float(m.group(1) or 0) * 60 + float(m.group(2)) / (1000 if m.group(3) == "ms" else 1)
            else:
                wait = 10.0
            time.sleep(min(max(wait, 1.0), 25.0))
        except groq_module.BadRequestError as e:
            if "tool_use_failed" not in str(e) and "tool call validation" not in str(e).lower():
                raise
            if attempt >= 3:
                raise
        except groq_module.APIStatusError as e:
            if getattr(e, "status_code", None) != 413 and "too large" not in str(e).lower():
                raise
            shrunk += 1
            if shrunk > 2:
                raise RequestTooLarge() from e
            _shrink(messages, 3000 if shrunk == 1 else 1200)
            max_tokens = 2000 if shrunk == 1 else 1400
    raise RuntimeError("The AI service didn't answer.")


_LIST_ARGS = ("names", "stats", "show_stats", "team_1_sends", "team_2_sends")


def _clean_args(args):
    """Model arguments as the tools expect them: a lone name where a list belongs becomes a one-item list."""
    if not isinstance(args, dict):
        return {}
    out = dict(args)
    for k in _LIST_ARGS:
        v = out.get(k)
        if isinstance(v, str):
            out[k] = [v] if v.strip() else []
        elif isinstance(v, (list, tuple)):
            out[k] = [str(x) for x in v if x not in (None, "")]
    if isinstance(out.get("questions"), list):
        out["questions"] = [q if isinstance(q, dict) else {"question": str(q)} for q in out["questions"]]
    return out


_NO_CHART_TOOLS = {"web_search"}
_FORCE_CHART = ("Now draw the chart for this answer: call create_visualization with the chart type that best answers "
                "the question, using the players/teams/seasons/stats you just looked up. If no chart type answers it "
                "exactly, draw the closest one and set note to one short sentence saying what the chart shows "
                "instead. Do not call any other tool.")


def _fallback_chart_args(used):
    """If the model still drew nothing: the closest chart to the last data it looked up, with a note saying so."""
    for name, args in reversed(used):
        a = dict(args or {})
        season = a.get("season")
        if name == "quarter_stats" and a.get("name"):
            return {"chart_type": "clutch_clock", "subject_type": a.get("subject_type"), "names": [a["name"]],
                    "season": season}
        if name == "game_log" and a.get("name"):
            return {"chart_type": "game_trend", "subject_type": a.get("subject_type"), "names": [a["name"]],
                    "season": season, "stat": (a.get("stats") or ["PTS"])[0], "quarter": a.get("quarter")}
        if name == "career_stats" and a.get("player"):
            return {"chart_type": "career_trend", "names": [a["player"]], "stat": (a.get("stats") or ["PTS"])[0],
                    "per_mode": a.get("per_mode")}
        if name == "league_leaders" and a.get("stat"):
            return {"chart_type": "leaderboard", "subject_type": a.get("subject_type"), "stat": a["stat"],
                    "season": season, "per_mode": a.get("per_mode"), "top_n": a.get("top_n"),
                    "ascending": a.get("ascending"), "filters": a.get("filters")}
        if name == "shot_zones" and a.get("name"):
            return {"chart_type": "zone_map", "subject_type": a.get("subject_type"), "names": [a["name"]],
                    "season": season}
        if name == "season_stats" and a.get("names"):
            names = a["names"]
            if len(names) >= 2:
                return {"chart_type": "comparison", "subject_type": a.get("subject_type"), "names": names[:6],
                        "season": season, "stats": a.get("stats"), "per_mode": a.get("per_mode")}
            return {"chart_type": "radar", "subject_type": a.get("subject_type"), "names": names, "season": season}
        if name in ("passing", "head_to_head") and a.get("player"):
            return {"chart_type": "radar", "names": [a["player"]], "season": season,
                    "note": "The closest chart here: this player's all-round profile for the season."}
        if name in ("lineups", "on_off") and a.get("team"):
            return {"chart_type": "radar", "subject_type": "team", "names": [a["team"]], "season": season,
                    "note": "The closest chart here: the team's all-round profile for the season."}
    return None


def _run_calls(calls, conversation, charts, used):
    """Runs one round of the model's tool calls. -> questions asked (or None)."""
    questions = None
    for tc in calls:
        name = tc.function.name
        try:
            args = _clean_args(json.loads(tc.function.arguments or "{}") or {})
        except (json.JSONDecodeError, TypeError):
            args = {}
        try:
            if name == "ask_clarifying_questions":
                questions = [q for q in (args.get("questions") or []) if isinstance(q, dict) and q.get("question")]
                result = {"status": "questions shown to the user; wait for their reply"}
            elif name == "create_visualization":
                result, chart_id = tool_create_visualization(**args)
                charts.append(chart_id)
            elif name in DATA_TOOLS:
                result = DATA_TOOLS[name](**args)
                if name not in _NO_CHART_TOOLS:
                    used.append((name, args))
            else:
                result = {"error": f"Unknown tool {name}."}
        except ToolError as e:
            result = {"error": str(e)}
        except TypeError as e:
            result = {"error": f"Bad arguments for {name}: {e}"}
        except Exception as e:  # noqa: BLE001 -- a data hiccup is reported to the model, never a crash
            result = {"error": f"{name} failed: {CTX['friendly_error'](e)}"}
        conversation.append({"role": "tool", "tool_call_id": tc.id,
                             "content": json.dumps(result, default=str)[:8000]})
    return questions or None


def _assistant_turn(msg, calls):
    return {"role": "assistant", "content": msg.content or "",
            "tool_calls": [tc.model_dump() if hasattr(tc, "model_dump") else tc for tc in calls]}


def run_turn(client, messages):
    """
    Answers the latest user message. -> {"content", "charts", "questions"}

    Every answer that used NBA data ends with a chart: if the model answers without drawing one, it is asked once more
    to draw the chart (the closest one, with a note, when no chart answers the question exactly), and if it still
    doesn't, the closest chart to the last data it looked up is drawn for it. An answer never ends without text.
    """
    conversation = [{"role": "system", "content": system_prompt()}] + _history_for_model(messages)
    charts, questions, final_text, used = [], None, "", []
    finished = False
    for _ in range(MAX_ROUNDS):
        try:
            resp = _call_model(client, conversation)
        except Exception as e:  # noqa: BLE001
            if not (charts or final_text.strip()):
                raise
            # keep what's already done (the charts are real); say the rest didn't finish
            final_text = (final_text.strip() + "\n\n" if final_text.strip() else "") + \
                f"_(I couldn't finish the rest of this answer: {_model_error_text(e)})_"
            finished = True
            break
        msg = resp.choices[0].message
        if msg.content:
            final_text = msg.content
        calls = msg.tool_calls or []
        if not calls:
            finished = True
            break
        conversation.append(_assistant_turn(msg, calls))
        questions = _run_calls(calls, conversation, charts, used) or questions
        if questions:
            finished = True
            break

    if not finished and not final_text.strip():
        # ran out of rounds mid-way: ask for the written answer from what's been gathered so far
        try:
            conversation.append({"role": "user", "content": "Write your answer now from the data you have."})
            resp = _call_model(client, conversation, tool_choice="none")
            final_text = resp.choices[0].message.content or final_text
        except Exception:  # noqa: BLE001
            pass

    if not questions and not charts and used:
        # the answer used NBA data but drew nothing: ask for the chart (closest one + note if nothing fits exactly)
        try:
            conversation.append({"role": "user", "content": _FORCE_CHART})
            resp = _call_model(client, conversation,
                               tool_choice={"type": "function", "function": {"name": "create_visualization"}})
            msg = resp.choices[0].message
            calls = [c for c in (msg.tool_calls or []) if c.function.name == "create_visualization"]
            if calls:
                conversation.append(_assistant_turn(msg, calls))
                _run_calls(calls, conversation, charts, used)
            if not final_text.strip() and msg.content:
                final_text = msg.content
        except Exception:  # noqa: BLE001
            pass
        if not charts:
            args = _fallback_chart_args(used)
            if args:
                args.setdefault("note", "The closest chart to this question, from the data looked up above.")
                try:
                    _result, chart_id = tool_create_visualization(**_clean_args(args))
                    charts.append(chart_id)
                except Exception:  # noqa: BLE001
                    pass

    if questions and not final_text.strip():
        final_text = "A quick question before I dig in:" if len(questions) == 1 else "A few quick questions before I dig in:"
    if not final_text.strip() and not charts:
        final_text = "I couldn't put an answer together for that -- try rephrasing it, or name the player, team and season."
    return {"content": final_text.strip(), "charts": charts, "questions": questions}


# ================================================================ page

_CSS = """
<style>
/* the conversation reads light-on-dark (the app runs on Streamlit's light base theme under its own dark styling) */
div[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] :is(p, li, td, th, strong, em, h1, h2, h3, h4) {
  color: #e8e8e8 !important; -webkit-text-fill-color: #e8e8e8 !important; }
div[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] :is(td, th) { border-color: #333 !important; }
div[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] th { background: rgba(212,175,55,0.08) !important; }
div[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] code { color: #F5D370 !important;
  background: rgba(255,255,255,0.06) !important; }
/* an answer with a chart uses the full width */
div[data-testid="stChatMessage"]:has(iframe) div[data-testid="stChatMessageContent"],
div[data-testid="stChatMessage"]:has([class*="st-key-ai_tb_"]) div[data-testid="stChatMessageContent"] {
  max-width: 100% !important; flex-grow: 1 !important; }
/* the controls on top of every chart */
[class*="st-key-ai_tb_"] { background: rgba(255,255,255,0.03); border: 1px solid #2a2a2a; border-radius: 10px;
  padding: 8px 10px 2px !important; gap: 0.5rem !important; flex-wrap: wrap !important; }
[class*="st-key-ai_tb_"] > div { flex: 1 1 130px !important; min-width: 120px !important; }
[class*="st-key-ai_tb_"] [data-testid="stWidgetLabel"] p { font-size: 0.78rem !important; }
.ai-chart-title { font-weight: 700; color: #f0f0f0; margin: 6px 0 4px; font-size: 1.0rem; }
.ai-chart-note { color: #e6d9a8; font-size: 0.9rem; margin: 8px 0 4px; padding: 6px 10px; border-left: 2px solid #D4AF37;
  background: rgba(212,175,55,0.06); border-radius: 0 6px 6px 0; }
/* one-click answers to Bradley's questions */
[class*="st-key-ai_qs_"] { border-left: 2px solid #D4AF37; padding-left: 12px !important; }
[class*="st-key-ai_qs_"] button[data-variant="pills"] { background: rgba(255,255,255,0.04) !important;
  border: 1px solid #3a3a3a !important; }
[class*="st-key-ai_qs_"] button[data-variant="pills"] p { color: #e6e6e6 !important; -webkit-text-fill-color: #e6e6e6 !important; }
[class*="st-key-ai_qs_"] button[data-variant="pills"][aria-checked="true"] { border-color: #D4AF37 !important;
  background: rgba(212,175,55,0.16) !important; }
[class*="st-key-no_icon_ai_suggest_"] button { justify-content: flex-start !important; text-align: left !important;
  min-height: 2.6rem; }
[class*="st-key-no_icon_ai_suggest_"] button p { text-align: left !important; }
</style>
"""

SUGGESTIONS = [
    "Who were the best 3-point shooters last season (at least 5 attempts a game)?",
    "Compare Nikola Jokić and Joel Embiid's 2022-23 seasons",
    "Where does Stephen Curry take his shots from?",
    "How has LeBron James' scoring changed over his career?",
    "Which teams had the best net rating this season?",
    "Plot usage rate vs true shooting for the top 30 scorers",
]


def _color_options():
    teams_sorted = sorted(CTX["TEAM_NAME_TO_RECORD"])
    return ["Auto", "Gold", "White", "Black"] + teams_sorted


def _toolbar(chart_id, spec):
    """The controls on top of a chart. Changing one redraws the chart straight away."""
    kind, p = spec["kind"], spec["params"]
    changed = False

    def _init(key, value):
        if key not in st.session_state:
            st.session_state[key] = value

    with st.container(key=f"ai_tb_{chart_id}", horizontal=True):
        if kind != "trade":
            ck = f"ai_{chart_id}_color"
            opts = _color_options()
            _init(ck, spec.get("color") if spec.get("color") in opts else "Auto")
            val = st.selectbox("Color", opts, key=ck, format_func=lambda o: "Automatic" if o == "Auto" else o)
            if val != spec.get("color"):
                spec["color"], changed = val, True
        if kind in COURT_STYLES:
            sk = f"ai_{chart_id}_court"
            _init(sk, kind)
            val = st.selectbox("Chart", list(COURT_STYLES), key=sk, format_func=COURT_STYLES.get)
            if val != kind:
                spec["kind"], changed = val, True
        if kind == "leaderboard":
            sk = f"ai_{chart_id}_style"
            _init(sk, p.get("style") or "Vertical bars")
            val = st.selectbox("Style", BAR_STYLES, key=sk)
            if val != p.get("style"):
                p["style"], changed = val, True
        if kind in ("leaderboard", "scatter"):
            nk = f"ai_{chart_id}_top"
            _init(nk, max(3, min(int(p.get("top_n") or 10), 50)))
            val = st.number_input("Show top", min_value=3, max_value=50, step=1, key=nk)
            if int(val) != int(p.get("top_n") or 10):
                p["top_n"], changed = int(val), True
        if kind == "game_trend":
            qk = f"ai_{chart_id}_quarter"
            _init(qk, p.get("quarter"))
            val = st.selectbox("Quarter", QUARTER_OPTIONS, key=qk,
                               format_func=lambda q: "Whole game" if q is None else QUARTER_NAMES[q].capitalize())
            if val != p.get("quarter"):
                if val is None:
                    p.pop("quarter", None)
                else:
                    p["quarter"] = val
                changed = True
        if kind in ("leaderboard", "scatter", "comparison", "career_trend", "radar", "distribution"):
            pk = f"ai_{chart_id}_pm"
            _init(pk, p.get("per_mode") or "PerGame")
            val = st.selectbox("Per", list(PER_MODE_LABELS), key=pk, format_func=PER_MODE_LABELS.get)
            if val != p.get("per_mode"):
                p["per_mode"], changed = val, True
        if kind not in ("career_trend",):
            sk = f"ai_{chart_id}_season"
            seasons = list(stats_config.ALL_SEASONS)
            cur = p.get("season") or seasons[0]
            if cur not in seasons:
                seasons = [cur] + seasons
            _init(sk, cur)
            val = st.selectbox("Season", seasons, key=sk)
            if val != p.get("season"):
                p["season"], changed = val, True
    if kind == "scatter" and spec.get("_names"):
        pics = pickers.picture_picker(spec["_names"], key=f"ai_pics_{chart_id}",
                                      noun="players" if p.get("subject_type") != "team" else "teams")
        new = sorted(pics)
        old = sorted(p["pictures"]) if p.get("pictures") is not None else sorted(spec["_names"])
        if new != old:
            p["pictures"] = new
            changed = True
    return changed


def _show_chart(chart_id):
    spec = st.session_state.get("ai_charts", {}).get(chart_id)
    if not spec:
        return
    _toolbar(chart_id, spec)
    if spec.get("note"):
        # "the closest chart to your question" -- said right above the chart, as asked
        st.markdown(f'<div class="ai-chart-note">{html_escape(str(spec["note"]))}</div>', unsafe_allow_html=True)
    if spec["kind"] == "animated_shot_chart":
        try:
            with CTX["code_loading_animation"]("Animating every shot of the season (this takes a minute)"):
                gif = _render_gif(spec, chart_id)
        except ToolError as e:
            st.warning(str(e))
            return
        except Exception as e:  # noqa: BLE001
            st.warning(f"Couldn't draw this chart with those settings: {CTX['friendly_error'](e)}")
            return
        if spec.get("title"):
            st.markdown(f'<div class="ai-chart-title">{html_escape(str(spec["title"]))}</div>', unsafe_allow_html=True)
        st.image(gif, width="stretch")
        return
    try:
        with CTX["code_loading_animation"]("Drawing the chart"):
            html, height = _render_html(spec, chart_id)
    except ToolError as e:
        st.warning(str(e))
        return
    except Exception as e:  # noqa: BLE001
        st.warning(f"Couldn't draw this chart with those settings: {CTX['friendly_error'](e)}")
        return
    if spec.get("title") and spec["kind"] not in ("leaderboard", "distribution", "game_trend"):
        # (those three already print their own title on the chart)
        st.markdown(f'<div class="ai-chart-title">{html_escape(str(spec["title"]))}</div>', unsafe_allow_html=True)
    if hasattr(st, "iframe"):
        try:
            st.iframe(html, height="content")
            return
        except Exception:  # noqa: BLE001
            pass
    components.html(html, height=height, scrolling=False)


def _questions_form(msg_index, questions):
    """One-click answers for the model's clarifying questions (typing an answer in the box works too)."""
    with st.container(key=f"ai_qs_{msg_index}"):
        keys = []
        for qi, q in enumerate(questions):
            text = str(q.get("question") or "").strip() or f"Question {qi + 1}"
            opts = list(dict.fromkeys(str(o).strip() for o in (q.get("options") or []) if str(o).strip()))[:6]
            key = f"ai_q_{msg_index}_{qi}"
            if opts:
                st.pills(text, opts, key=key, selection_mode="single")
                st.text_input("Or type your own", key=key + "_txt", label_visibility="collapsed",
                              placeholder="...or type your own answer")
            else:
                st.text_input(text, key=key + "_txt")
            keys.append((text, key))

        def _send():
            parts = []
            for text, key in keys:
                typed = str(st.session_state.get(key + "_txt") or "").strip()
                picked = st.session_state.get(key)
                answer = typed or picked
                if answer:
                    parts.append(f"{text} -> {answer}")
            if parts:
                st.session_state["ai_pending_input"] = "; ".join(parts)

        with st.container(key=f"no_icon_ai_q_send_{msg_index}"):
            st.button("Send answers", key=f"ai_q_send_{msg_index}", on_click=_send)


def render(ctx):
    CTX.update(ctx)
    st.title("AI Search")
    st.caption("Ask Bradley anything about basketball -- stats, comparisons, history, rules, news. You get a written "
               "answer and a chart you can restyle.")
    st.markdown(_CSS, unsafe_allow_html=True)
    ctx["info_card"]("Disclaimer",
                     "Bradley is an AI assistant built on real, live NBA data -- but like any AI, it can occasionally "
                     "misread a request, pick the wrong player or season, or make a mistake summarizing a result. The "
                     "charts and numbers come straight from the NBA's own data, but double-check anything that matters "
                     "against the raw data (Search by Player / Team / Criteria) before relying on it.")

    try:
        api_key = st.secrets.get("GROQ_API_KEY", None)
    except Exception:  # noqa: BLE001
        api_key = None
    api_key = api_key or os.environ.get("GROQ_API_KEY")

    msgs = st.session_state.setdefault("ai_chat", [])

    if not api_key:
        ctx["info_card"]("AI Setup Required",
                         'Bradley isn\'t live yet -- no Groq API key is configured. Groq is free: get a key at '
                         '<a href="https://console.groq.com/keys" target="_blank">console.groq.com</a>, no credit '
                         'card required.<ul style="margin: 8px 0 0 0; padding-left: 20px;">'
                         '<li><strong>Local run:</strong> create <code>.streamlit/secrets.toml</code> in the project '
                         'root with <code>GROQ_API_KEY = "your-key-here"</code></li>'
                         '<li><strong>Streamlit Community Cloud:</strong> add <code>GROQ_API_KEY</code> under your '
                         'deployed app\'s Settings → Secrets</li></ul>')

    top = st.columns([1, 0.22])
    with top[1], st.container(key="no_icon_ai_clear_wrap"):
        if msgs and st.button("New chat", key="ai_clear", use_container_width=True):
            st.session_state["ai_chat"] = []
            st.session_state["ai_charts"] = {}
            st.session_state["ai_html"] = {}
            st.rerun()

    if not msgs:
        st.markdown("**Try asking:**")
        cols = st.columns(2)
        for i, s in enumerate(SUGGESTIONS):
            with cols[i % 2]:
                with st.container(key=f"no_icon_ai_suggest_{i}"):
                    st.button(s, key=f"ai_sugg_btn_{i}", use_container_width=True,
                              on_click=lambda s=s: st.session_state.__setitem__("ai_pending_input", s))

    answer_idx = [i for i, m in enumerate(msgs) if m["role"] == "assistant"]
    live = set(answer_idx[-LIVE_ANSWERS:])
    for i, m in enumerate(msgs):
        with st.chat_message(m["role"]):
            if m.get("content"):
                # "$" would otherwise switch Streamlit's markdown into math mode ("a $50M deal ... $10M")
                st.markdown(re.sub(r"(?<!\\)\$", r"\\$", m["content"]))
            if m["role"] == "assistant":
                for cid in m.get("charts", []):
                    if i in live:
                        _show_chart(cid)
                    else:   # older answers: drawn only when asked for, so a long chat stays fast
                        title = st.session_state.get("ai_charts", {}).get(cid, {}).get("title") or "chart"
                        if st.toggle(f"Show chart: {title}", key=f"ai_show_{cid}"):
                            _show_chart(cid)
                if m.get("questions") and i == len(msgs) - 1:
                    _questions_form(i, m["questions"])
                elif m.get("questions"):
                    st.markdown("\n".join(f"- {q.get('question')}" for q in m["questions"]))

    # the ask box: pinned to the bottom of the screen, like any chat
    # a question left without an answer (e.g. the page was clicked while Bradley was thinking) can be answered now
    if msgs and msgs[-1]["role"] == "user":
        with st.container(key="no_icon_ai_retry_wrap"):
            if st.button("Answer this question", key="ai_retry"):
                st.session_state["ai_retry"] = True
    typed = st.chat_input("Ask Bradley anything about basketball.", key="ai_chat_input")
    user_input = typed.strip() if typed and typed.strip() else None
    if not user_input and st.session_state.get("ai_pending_input"):
        user_input = st.session_state.pop("ai_pending_input")
    retry = bool(st.session_state.pop("ai_retry", False)) and msgs and msgs[-1]["role"] == "user"
    if not user_input and not retry:
        return

    if user_input:
        msgs.append({"role": "user", "content": user_input})
    user_input = msgs[-1]["content"]
    if not api_key:
        msgs.append({"role": "assistant", "content": "I can't answer yet -- no Groq API key is set up (see the note "
                                                     "above; it's free).", "charts": []})
        st.rerun()
    import groq as groq_module
    try:
        client = _make_client(api_key)
        CTX["client"] = client
        with st.chat_message("user"):
            st.markdown(user_input)
        with st.chat_message("assistant"):
            with ctx["code_loading_animation"]("Thinking"):
                reply = run_turn(client, msgs)
    except (groq_module.GroqError, RequestTooLarge) as e:
        reply = {"content": _model_error_text(e), "charts": []}
    except Exception as e:  # noqa: BLE001
        reply = {"content": f"Something went wrong: {_model_error_text(e)}", "charts": []}
    msgs.append({"role": "assistant", **reply})
    st.rerun()
