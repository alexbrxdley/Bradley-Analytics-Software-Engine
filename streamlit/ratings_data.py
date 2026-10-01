"""
ratings_data.py -- the Bradley Ratings and Tendencies of every player we have them for.

Two spreadsheets, filled in by hand from the 2K player screens, one row per player (each team's players under the
previous team's):

    data/Ratings.csv      Team, Name, Position, Age, Player Rating, Driving Layup, ... Potential  (the "Bradley Ratings")
    data/Tendencies.csv   Team, Name, Position, Age, Player Rating, Shot Tendency, ... Contest Shot Tendency

The numbers are this season's: they are used for both 2025-26 and 2026-27 (SEASONS) -- any other season has none.
Not every player has them yet; a player without a row shows N/A.

Names in the spreadsheets are written the 2K way ("T. Maxey"). data/ratings_player_names.csv gives each one's full
name ("Tyrese Maxey"); a row added later without an entry there is matched on its own -- first initial + last name
(accents, periods and Jr./III ignored), on the same team when there are two (Jalen and Jaylin Williams), then age and
position.

Adding players or new columns to either spreadsheet needs no code change: every column after Team, Name, Position and
Age is offered in the dashboard's "Bradley rating:" / "Tendency:" menus automatically. "Potential" is a letter grade;
for sorting, charts and formulas it counts as the points in GRADE_POINTS (A+ = 97 ... F = 50), and tables show the
letter.
"""

import csv
import functools
import os
import unicodedata

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.normpath(os.path.join(_HERE, "..", "data"))
RATINGS_CSV = os.path.join(_DATA, "Ratings.csv")
TENDENCIES_CSV = os.path.join(_DATA, "Tendencies.csv")
NAMES_CSV = os.path.join(_DATA, "ratings_player_names.csv")

SEASONS = ("2026-27", "2025-26")            # the seasons these numbers stand for
ID_COLS = ("Team", "Name", "Position", "Age")
GRADE_POINTS = {"A+": 97, "A": 93, "A-": 90, "B+": 87, "B": 83, "B-": 80, "C+": 77, "C": 73, "C-": 70,
                "D+": 67, "D": 63, "D-": 60, "F": 50}
RATINGS, TENDENCIES = "ratings", "tendencies"
SOURCE_OF = {RATINGS: "bradley_rating_csv", TENDENCIES: "tendency_csv"}     # the "source" in a stat tuple
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def available(season) -> bool:
    """True for a season these numbers stand for (2025-26 and 2026-27)."""
    return str(season) in SEASONS


def _fold(s) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s or "")) if unicodedata.category(c) != "Mn").lower()


def _key_full(full_name):
    """'Jaime Jaquez Jr.' -> ('jaime', 'jaquez', True): first name, last name(s), whether it has a Jr./III."""
    toks = _fold(full_name).replace(".", "").split()
    if not toks:
        return "", "", False
    rest = toks[1:]
    return toks[0], " ".join(t for t in rest if t not in _SUFFIXES), any(t in _SUFFIXES for t in rest)


def _key_abbr(name):
    """'V.J. Edgecombe' -> ('vj', 'edgecombe', False): the initial(s), last name(s), whether it has a Jr./III."""
    first, _, rest = _fold(name).partition(" ")
    toks = rest.replace(".", "").split()
    return first.replace(".", ""), " ".join(t for t in toks if t not in _SUFFIXES), any(t in _SUFFIXES for t in toks)


def name_matches(abbr_name, full_name) -> bool:
    """'T. Maxey' is 'Tyrese Maxey'."""
    i, last, _ = _key_abbr(abbr_name)
    f, flast, _ = _key_full(full_name)
    return bool(last) and last == flast and f.startswith(i)


def _pos_letter(pos):
    return {"PG": "G", "SG": "G", "SF": "F", "PF": "F", "C": "C"}.get(str(pos).strip().upper(), "")


def _read(path):
    if not os.path.exists(path):
        return pd.DataFrame()
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return pd.DataFrame()
    head, body = rows[0], [r + [""] * (len(rows[0]) - len(r)) for r in rows[1:] if any(c.strip() for c in r)]
    return pd.DataFrame(body, columns=head)


@functools.lru_cache(maxsize=1)
def _static_players():
    """Every player nba_api knows: (folded full name -> [(id, full name, active)])."""
    out = {}
    try:
        from nba_api.stats.static import players as _p
        for p in _p.get_players():
            out.setdefault(_fold(p["full_name"]), []).append((int(p["id"]), p["full_name"], bool(p.get("is_active"))))
    except Exception:
        pass
    return out


def _full_name_for(team, name, names_map, static_by_key):
    """A spreadsheet row's full name: the names file, else the only active player with that initial + last name."""
    full = names_map.get((team, name))
    if full:
        return full
    i, last, suf = _key_abbr(name)
    cands = static_by_key.get(last, [])
    cands = [c for c in cands if c[0].startswith(i) and c[3]]
    if len(cands) > 1:
        cands = [c for c in cands if c[2] == suf] or cands
    return cands[0][1] if len(cands) == 1 else None


@functools.lru_cache(maxsize=4)
def _table(kind, _mtime=None):
    """The spreadsheet as a DataFrame, plus FULL_NAME and PLAYER_ID (None where nba_api doesn't know the player yet,
    e.g. a new rookie) and every number column as numbers (Potential as grade points; POTENTIAL_GRADE keeps the
    letter)."""
    df = _read(RATINGS_CSV if kind == RATINGS else TENDENCIES_CSV)
    if df.empty:
        return df
    names_map = {}
    nm = _read(NAMES_CSV)
    if not nm.empty and {"Team", "Name", "Full Name"} <= set(nm.columns):
        names_map = {(t, n): f for t, n, f in zip(nm["Team"], nm["Name"], nm["Full Name"]) if str(f).strip()}
    static = _static_players()
    by_key = {}
    for folded, recs in static.items():
        f, last, suf = _key_full(folded)
        for pid, full, active in recs:
            by_key.setdefault(last, []).append((f, full, suf, active))
    fulls, ids = [], []
    for team, name in zip(df["Team"], df["Name"]):
        full = _full_name_for(team, name, names_map, by_key)
        recs = static.get(_fold(full), []) if full else []
        recs = sorted(recs, key=lambda r: not r[2])           # an active player before a retired namesake
        fulls.append(full or name)
        ids.append(recs[0][0] if recs else None)
    df.insert(2, "FULL_NAME", fulls)
    df.insert(3, "PLAYER_ID", pd.array(ids, dtype="Int64"))
    for c in df.columns:
        if c in ID_COLS[:3] or c in ("FULL_NAME", "PLAYER_ID"):
            continue
        if c == "Potential":
            df["POTENTIAL_GRADE"] = df[c].astype(str).str.strip()
            df[c] = df["POTENTIAL_GRADE"].map(GRADE_POINTS)
        else:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _mtime(kind):
    try:
        return (os.path.getmtime(RATINGS_CSV if kind == RATINGS else TENDENCIES_CSV),
                os.path.getmtime(NAMES_CSV) if os.path.exists(NAMES_CSV) else 0)
    except OSError:
        return None


def table(kind) -> pd.DataFrame:
    """The whole spreadsheet (re-read when the file changes). Columns: Team, Name, FULL_NAME, PLAYER_ID, Position,
    Age, then the numbers."""
    return _table(kind, _mtime(kind)).copy()


def columns(kind) -> list:
    """The columns offered in the "Bradley rating:" / "Tendency:" menus, in the spreadsheet's order: every column after
    Team, Name, Position and Age (for Tendencies only the ... Tendency columns -- its Player Rating is the same
    number as the Bradley Ratings' one)."""
    df = _table(kind, _mtime(kind))
    if df.empty:
        return []
    skip = set(ID_COLS) | {"FULL_NAME", "PLAYER_ID", "POTENTIAL_GRADE"}
    cols = [c for c in df.columns if c not in skip]
    if kind == TENDENCIES:
        cols = [c for c in cols if c.lower().endswith("tendency")]
    return cols


def stat_tuples(kind) -> list:
    """The columns as the dashboard's (field, label, source) stat tuples."""
    return [(c, c, SOURCE_OF[kind]) for c in columns(kind)]


def is_source(source) -> bool:
    return source in SOURCE_OF.values()


def kind_of_source(source):
    return next((k for k, s in SOURCE_OF.items() if s == source), None)


def league_frame(kind) -> pd.DataFrame:
    """One row per player with numbers, in the shape the dashboard's stat tables have: PLAYER_ID, PLAYER_NAME (full
    name), TEAM_NAME, then every column."""
    df = table(kind)
    if df.empty:
        return pd.DataFrame(columns=["PLAYER_ID", "PLAYER_NAME", "TEAM_NAME"])
    out = df.rename(columns={"FULL_NAME": "PLAYER_NAME", "Team": "TEAM_NAME"})
    keep = ["PLAYER_ID", "PLAYER_NAME", "TEAM_NAME", "Position", "Age"] + columns(kind) + \
        (["POTENTIAL_GRADE"] if "POTENTIAL_GRADE" in out.columns else [])
    return out[[c for c in keep if c in out.columns]].reset_index(drop=True)


def lookup(kind, roster):
    """{index of each roster row: that player's spreadsheet row (a pandas Series) or None}.

    roster: DataFrame with PLAYER (full name), and PLAYER_ID / AGE / POSITION when known (an NBA team roster, or the
    league's stat table renamed). A player is found by id, then by full name, then by "T. Maxey"-style name -- on
    the same team first; two candidates are told apart by age, then position."""
    df = _table(kind, _mtime(kind))
    out = {}
    if df.empty or roster is None or len(roster) == 0:
        return {i: None for i in (roster.index if roster is not None else [])}
    by_id = {int(p): r for p, (_, r) in zip(df["PLAYER_ID"], df.iterrows()) if pd.notna(p)}
    by_name = {}
    for _, r in df.iterrows():
        by_name.setdefault(_fold(r["FULL_NAME"]), []).append(r)
    taken = set()
    for i, row in roster.iterrows():
        pid = row.get("PLAYER_ID")
        hit = by_id.get(int(pid)) if pid is not None and pd.notna(pid) else None
        name = str(row.get("PLAYER") or row.get("PLAYER_NAME") or "")
        if hit is None and name:
            cands = by_name.get(_fold(name), [])
            if not cands:
                cands = [r for _, r in df.iterrows() if name_matches(r["Name"], name)]
            team = row.get("TEAM_NAME")
            if len(cands) > 1 and team:
                cands = [r for r in cands if r["Team"] == team] or cands
            if len(cands) > 1:
                age = pd.to_numeric(pd.Series([row.get("AGE")]), errors="coerce").iloc[0]
                pos = str(row.get("POSITION") or "")
                cands = sorted(cands, key=lambda r: (abs((r["Age"] if pd.notna(r["Age"]) else 0) - (age if pd.notna(age) else 0)),
                                                     _pos_letter(r["Position"]) not in pos))
            cands = [r for r in cands if (r["Team"], r["Name"]) not in taken] or cands
            hit = cands[0] if cands else None
        if hit is not None:
            taken.add((hit["Team"], hit["Name"]))
        out[i] = hit
    return out


def display(value, column) -> str:
    """A number as a table shows it: whole numbers, Potential as its letter grade, N/A when missing."""
    if value is None or (isinstance(value, float) and pd.isna(value)) or value is pd.NA:
        return "N/A"
    if column == "Potential":
        inv = {v: k for k, v in GRADE_POINTS.items()}
        return inv.get(int(round(float(value))), str(value))
    try:
        return str(int(round(float(value))))
    except (TypeError, ValueError):
        return str(value)


def short_label(column) -> str:
    """A column title short enough for a table header: 'Driving Layup' stays, 'Shot Close Left Tendency' -> 'Shot Close
    Left' (every Tendencies column ends in "Tendency")."""
    c = str(column)
    return c[:-len(" Tendency")] if c.endswith(" Tendency") else c
