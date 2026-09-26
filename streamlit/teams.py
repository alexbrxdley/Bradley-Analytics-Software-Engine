"""
teams.py

Team color, ID, and logo-abbreviation lookups, extracted programmatically
from python/bradley_analytics.py and python/scatter_data.py to guarantee
an exact match rather than a manually retyped copy.
"""

import functools
import re
import time
import unicodedata

TEAM_COLORS = {
    "hawks": "#E03A3E",
    "celtics": "#007A33",
    "nets": "#808080",
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
    "spurs": "#808080",
    "raptors": "#CE1141",
    "jazz": "#002B5C",
    "wizards": "#002B5C"
}

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
    "wizards": 1610612764
}

# Maps team_id -> ESPN logo abbreviation, used to build team logo URLs
TEAM_ESPN_ABBREV = {
    1610612737: "atl",
    1610612738: "bos",
    1610612751: "bkn",
    1610612766: "cha",
    1610612741: "chi",
    1610612739: "cle",
    1610612742: "dal",
    1610612743: "den",
    1610612765: "det",
    1610612744: "gs",
    1610612745: "hou",
    1610612754: "ind",
    1610612746: "lac",
    1610612747: "lal",
    1610612763: "mem",
    1610612748: "mia",
    1610612749: "mil",
    1610612750: "min",
    1610612740: "no",
    1610612752: "ny",
    1610612760: "okc",
    1610612753: "orl",
    1610612755: "phi",
    1610612756: "phx",
    1610612757: "por",
    1610612758: "sac",
    1610612759: "sa",
    1610612761: "tor",
    1610612762: "utah",
    1610612764: "wsh"
}

DEFAULT_COLOR = "#FFFFFF"


def get_team_color(team_name: str) -> str:
    """
    Exact match first, then a word-boundary partial match, matching
    bradley_analytics.py's lookup logic -- word-boundary rather than a
    raw substring check specifically because a raw substring check
    matches "nets" inside "hornets" (h-o-r-NETS), which was silently
    returning the Nets' black instead of the Hornets' own purple/teal
    for any input like "Charlotte Hornets" that isn't an exact
    dictionary key.
    """
    import re
    key = team_name.lower().strip()
    if key in TEAM_COLORS:
        return TEAM_COLORS[key]
    for name, color in TEAM_COLORS.items():
        if re.search(rf"\b{re.escape(name)}\b", key):
            return color
    return DEFAULT_COLOR


# ---------------------------------------------------------------------------
# Image sources
#
# A "URL" returned by the two functions below can carry SEVERAL candidate
# addresses joined by IMAGE_SEP, best first. visuals._fetch_image() tries them in
# order and uses the first that loads, so a chart never ends up with a blank
# because one source is down, blocks servers, or spells a name differently.
# (For a browser <img> -- st.image() -- use first_working_url() to pick one.)
# ---------------------------------------------------------------------------
IMAGE_SEP = "||"
_USER_AGENT = "BradleyAnalytics/1.0 (NBA analytics dashboard)"
_TWOK_UPLOADS = "https://www.2kratings.com/wp-content/uploads/"


@functools.lru_cache(maxsize=1)
def _player_meta() -> dict:
    """{player_id: (full_name, is_active)} for every player nba_api knows -- current AND retired, back to 1946."""
    try:
        from nba_api.stats.static import players as _players
        return {int(p["id"]): (p["full_name"], bool(p.get("is_active", True))) for p in _players.get_players()}
    except Exception:
        return {}


def _player_names_by_id() -> dict:
    return {i: m[0] for i, m in _player_meta().items()}


@functools.lru_cache(maxsize=1)
def team_records_by_name() -> dict:
    """{full team name: nba_api team record (id, abbreviation, ...)} for the 30 current teams."""
    try:
        from nba_api.stats.static import teams as _teams
        return {t["full_name"]: t for t in _teams.get_teams()}
    except Exception:
        return {}


def is_current_player(player_id) -> bool:
    """Active in nba_api's list -- or absent from it (a rookie newer than the installed list is far likelier current than retired)."""
    meta = _player_meta().get(int(player_id))
    return True if meta is None else meta[1]


def twok_headshot_urls(full_name: str) -> list:
    """
    2kratings.com serves each player's image at /wp-content/uploads/{First-Last}-2K-Rating.png (the file name has no
    game edition in it, so it survives a new 2K release). WordPress file names drop accents, apostrophes and commas
    and turn spaces into hyphens; whether a period survives ("V.J." vs "VJ") isn't guaranteed, so both are offered.
    """
    if not full_name:
        return []
    ascii_name = unicodedata.normalize("NFKD", full_name).encode("ascii", "ignore").decode()
    stem = re.sub(r"\s+", "-", re.sub(r"[\u2019'`,]", "", ascii_name).strip())
    if not stem:
        return []
    variants = [stem] + ([stem.replace(".", "")] if "." in stem else [])
    return [f"{_TWOK_UPLOADS}{v}-2K-Rating.png" for v in variants]


def get_player_headshot_url(player_id: int) -> str:
    """
    Where a player's picture comes from, best source first (the first that loads is used):
      current player: 2kratings.com image, then the NBA's official headshot
      retired player: the NBA's official headshot (the one on nba.com/stats/player/<id>), then 2kratings.com
    The player ID (from nba_api, which lists every player in NBA history) is all that is needed -- no separate
    id/name/image glossary to maintain.
    """
    pid = int(player_id)
    name = _player_meta().get(pid, ("", True))[0]
    nba = f"https://cdn.nba.com/headshots/nba/latest/1040x760/{pid}.png"
    twok = twok_headshot_urls(name)
    return IMAGE_SEP.join(twok + [nba] if is_current_player(pid) else [nba] + twok)


# 2kratings.com spells each team like this (its own team pages use the same names); keyed by NBA abbreviation.
_TWOK_TEAM_NAMES = {
    "ATL": "Atlanta Hawks", "BOS": "Boston Celtics", "BKN": "Brooklyn Nets", "CHA": "Charlotte Hornets", "CHI": "Chicago Bulls",
    "CLE": "Cleveland Cavaliers", "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets", "DET": "Detroit Pistons",
    "GSW": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers", "LAC": "Los Angeles Clippers",
    "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies", "MIA": "Miami Heat", "MIL": "Milwaukee Bucks",
    "MIN": "Minnesota Timberwolves", "NOP": "New Orleans Pelicans", "NYK": "New York Knicks", "OKC": "Oklahoma City Thunder",
    "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns", "POR": "Portland Trail Blazers",
    "SAC": "Sacramento Kings", "SAS": "San Antonio Spurs", "TOR": "Toronto Raptors", "UTA": "Utah Jazz", "WAS": "Washington Wizards",
}


def twok_team_logo_urls(team_id: int) -> list:
    """
    2kratings.com's logo for a team: /wp-content/uploads/{Team-Name}-Current-Logo.svg (e.g. Boston-Celtics-Current-Logo.svg,
    read off the site's own Celtics page). "Current" is part of the file name, so a rebrand replaces the file in place.
    """
    rec = next((t for t in team_records_by_name().values() if int(t["id"]) == int(team_id)), None)
    name = _TWOK_TEAM_NAMES.get(rec["abbreviation"]) if rec else None
    if not name:
        return []
    slug = "-".join(name.split())
    return [f"{_TWOK_UPLOADS}{slug}-Current-Logo.svg"]


# ---------------------------------------------------------------------------
# WHICH SOURCE EACH TEAM'S LOGO COMES FROM: "espn", "nba" or "2kratings".
# Every team uses ESPN's logo except the Celtics, who use 2kratings' current logo (the one on their team page): the original
# code recorded that ESPN serves the Celtics' alternate logo rather than their primary one. To change a team, add or edit a
# line in TEAM_LOGO_SOURCE (by full team name); anything not listed uses DEFAULT_LOGO_SOURCE. If the chosen source can't be
# loaded, the other two are tried in the order espn, nba, 2kratings, so a logo is never blank.
# ---------------------------------------------------------------------------
DEFAULT_LOGO_SOURCE = "espn"
TEAM_LOGO_SOURCE = {
    "Boston Celtics": "2kratings",
}
LOGO_SOURCES = ("espn", "nba", "2kratings")


def logo_source_for(team_id: int) -> str:
    """The source chosen for this team (see TEAM_LOGO_SOURCE)."""
    for name, rec in team_records_by_name().items():
        if int(rec["id"]) == int(team_id):
            src = TEAM_LOGO_SOURCE.get(name, DEFAULT_LOGO_SOURCE)
            return src if src in LOGO_SOURCES else DEFAULT_LOGO_SOURCE
    return DEFAULT_LOGO_SOURCE


def get_team_logo_url(team_id: int) -> str:
    """The team's logo addresses, the chosen source first (see TEAM_LOGO_SOURCE), then the others as fallbacks."""
    tid = int(team_id)
    abbrev = TEAM_ESPN_ABBREV.get(tid)
    per_source = {
        "espn": [f"https://a.espncdn.com/i/teamlogos/nba/500/{abbrev}.png"] if abbrev else [],
        "nba": [f"https://cdn.nba.com/logos/nba/{tid}/global/L/logo.svg", f"https://cdn.nba.com/logos/nba/{tid}/primary/L/logo.svg"],
        "2kratings": list(twok_team_logo_urls(tid)),
    }
    first = logo_source_for(tid)
    order = [first] + [x for x in LOGO_SOURCES if x != first]
    return IMAGE_SEP.join(u for x in order for u in per_source[x])


def teams_alphabetical() -> list:
    """The 30 teams' full names in alphabetical order by TEAM name (nickname): 76ers, Bucks, Bulls, Cavaliers, ... Wizards."""
    recs = team_records_by_name()
    return sorted(recs, key=lambda n: recs[n]["nickname"].casefold())


_WORKING_URL_CACHE = {}


def first_working_url(candidates: str, timeout: float = 3.0) -> str:
    """One URL a browser can load: the first candidate the server can fetch (cached), else the first candidate."""
    urls = [u for u in candidates.split(IMAGE_SEP) if u]
    if len(urls) <= 1:
        return urls[0] if urls else ""
    hit = _WORKING_URL_CACHE.get(candidates)
    if hit and hit[1] > time.time():
        return hit[0]
    chosen = None
    try:
        import requests
        for u in urls:
            try:
                r = requests.get(u, timeout=timeout, stream=True, headers={"User-Agent": _USER_AGENT})
                ok = r.status_code == 200 and (r.headers.get("content-type", "").startswith("image") or u.endswith(".svg"))
                r.close()
                if ok:
                    chosen = u
                    break
            except Exception:
                continue
    except ImportError:
        pass
    _WORKING_URL_CACHE[candidates] = (chosen or urls[0], time.time() + (3600 if chosen else 120))
    return chosen or urls[0]


_EMOJI_SWATCHES = {
    "🟥": (196, 30, 58), "🟧": (237, 125, 49), "🟨": (255, 214, 10),
    "🟩": (52, 168, 83), "🟦": (13, 71, 161), "🟪": (123, 31, 162),
    "🟫": (121, 85, 72), "⬛": (20, 20, 20), "⬜": (245, 245, 245),
}


def _hex_to_rgb(hex_color: str) -> tuple:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def nearest_color_swatch(hex_color: str) -> str:
    """
    Streamlit's native selectbox only renders plain text for its
    options -- no HTML, no inline color swatches -- so this maps a
    team's real hex color to whichever colored-square emoji is
    closest, giving a genuine (if approximate, given only 9 emoji
    colors exist to choose from) visual color hint next to each team
    name in the dropdown without needing a custom component.

    Matches by hue rather than raw RGB distance for anything with real
    saturation -- plain RGB distance was classifying dark, saturated
    team colors (e.g. the Bucks' near-black-looking #00471B) as
    "black" rather than "green", since a very dark green really is
    numerically closer to black than to a bright green swatch, even
    though a person looking at it would call it green. Only truly
    low-saturation or extreme-brightness colors fall back to
    black/white/brown.
    """
    import colorsys
    try:
        r, g, b = _hex_to_rgb(hex_color)
    except (ValueError, IndexError):
        return "⬜"

    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)

    if v < 0.18:
        return "⬛"
    if s < 0.15:
        return "⬜" if v > 0.6 else "⬛"

    hue_degrees = h * 360
    if hue_degrees < 15 or hue_degrees >= 345:
        return "🟥"
    elif hue_degrees < 45:
        return "🟧"
    elif hue_degrees < 70:
        return "🟨"
    elif hue_degrees < 170:
        return "🟩"
    elif hue_degrees < 250:
        return "🟦"
    elif hue_degrees < 300:
        return "🟪"
    else:
        return "🟥"
