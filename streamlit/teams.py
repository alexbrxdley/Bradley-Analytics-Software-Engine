"""
teams.py

Team color, ID, and logo-abbreviation lookups, extracted programmatically
from python/bradley_analytics.py and python/scatter_data.py to guarantee
an exact match rather than a manually retyped copy.
"""

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
    "1610612737": "atl",
    "1610612738": "bos",
    "1610612751": "bkn",
    "1610612766": "cha",
    "1610612741": "chi",
    "1610612739": "cle",
    "1610612742": "dal",
    "1610612743": "den",
    "1610612765": "det",
    "1610612744": "gs",
    "1610612745": "hou",
    "1610612754": "ind",
    "1610612746": "lac",
    "1610612747": "lal",
    "1610612763": "mem",
    "1610612748": "mia",
    "1610612749": "mil",
    "1610612750": "min",
    "1610612740": "no",
    "1610612752": "ny",
    "1610612760": "okc",
    "1610612753": "orl",
    "1610612755": "phi",
    "1610612756": "phx",
    "1610612757": "por",
    "1610612758": "sac",
    "1610612759": "sa",
    "1610612761": "tor",
    "1610612762": "utah",
    "1610612764": "wsh"
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


def get_player_headshot_url(player_id: int) -> str:
    return f"https://cdn.nba.com/headshots/nba/latest/1040x760/{player_id}.png"


def get_team_logo_url(team_id: int) -> str:
    abbrev = TEAM_ESPN_ABBREV.get(team_id)
    if abbrev is None:
        return None
    return f"https://a.espncdn.com/i/teamlogos/nba/500/{abbrev}.png"


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
