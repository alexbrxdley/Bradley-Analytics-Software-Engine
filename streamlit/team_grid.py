"""
team_grid.py -- team pickers drawn as a grid of logos instead of a dropdown of team names.

Every one of the 30 teams is a circular logo, in alphabetical order by TEAM name (76ers, Bucks, Bulls, ... Wizards),
3 rows x 10 columns on a wide screen (it reflows to 5 across on a phone so each logo stays tappable). Each logo sits
inside a ring in that team's colour -- the same colour the visualizations use (teams.get_team_color) -- and the chosen
team gets one thick, glowing ring. Hovering a logo only makes it bigger.

It is still a native Streamlit widget underneath (st.radio for one team, st.pills for several), restyled with CSS, so
keyboard use, session state and the returned value (the team's full name) are exactly what a dropdown returned.
Logos come from 2kratings.com first (then the NBA's CDN, then ESPN -- see teams.get_team_logo_url), are fetched once
on the server and embedded in the page as small images, so visitors' browsers never have to reach those sites.
"""

import base64
import io
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import streamlit as st
from PIL import Image, ImageDraw

import teams
import visuals

GRID_COLUMNS = 10
_LOGO_PX = 112
_OK_SECONDS, _FAIL_SECONDS, _FALLBACK_SECONDS = 24 * 3600, 120, 300          # a logo is re-fetched daily, so a rebrand shows up on its own
_CSS_FLAG = "_ba_team_grid_css_emitted"               # per visitor, reset at the start of every run
_lock = threading.Lock()
_logo_cache = {}                                       # team full name -> (expires_at, data_uri)
_css_cache = {"expires": 0.0, "css": ""}
_SOURCES = {}                                           # team -> how its logo was obtained (shown by ?logos=debug)
_DEBUG_FLAG = "_ba_team_grid_debug_shown"

# Extra non-team choices some pickers offer (the visualization colour picker): name -> (fill css, ring colour)
SPECIAL_SWATCHES = {
    "White": ("#FFFFFF", "#FFFFFF", "#FFFFFF"),
    "Black": ("#000000", "#404040", "#5c5c5c"),
    "Gold": ("linear-gradient(135deg, #B8860B, #F5D370, #B8860B)", "#D4AF37", "#D4AF37"),
}
_ITEM = 'label[data-testid="stRadioOption"], {root} button[data-variant="pills"]'


def begin_run():
    st.session_state[_CSS_FLAG] = False
    st.session_state[_DEBUG_FLAG] = False


def _placeholder(abbrev: str, color: str) -> Image.Image:
    """Shown only if no source has the logo: the team's abbreviation in its own colour, so a picker is never blank."""
    im = Image.new("RGBA", (_LOGO_PX, _LOGO_PX), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((6, 6, _LOGO_PX - 6, _LOGO_PX - 6), fill=color)
    try:
        w = d.textlength(abbrev)
    except Exception:
        w = 8 * len(abbrev)
    d.text(((_LOGO_PX - w) / 2, _LOGO_PX / 2 - 5), abbrev, fill="#FFFFFF")
    return im


def _to_data_uri(im: Image.Image) -> str:
    im = im.convert("RGBA")
    im.thumbnail((_LOGO_PX, _LOGO_PX))
    canvas = Image.new("RGBA", (_LOGO_PX, _LOGO_PX), (0, 0, 0, 0))
    canvas.paste(im, ((_LOGO_PX - im.width) // 2, (_LOGO_PX - im.height) // 2), im)
    buf = io.BytesIO()
    canvas.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _logo_uri(name: str) -> str:
    """The page-ready image for one team's logo (a data URI). A logo from the preferred source (2kratings) is kept a day; a
    fallback is retried within minutes, so one failed request can't leave the wrong logo up for a day."""
    now = time.time()
    hit = _logo_cache.get(name)
    if hit and hit[0] > now:
        return hit[1]
    rec = teams.team_records_by_name()[name]
    try:
        res = visuals.fetch_logo_source(teams.get_team_logo_url(rec["id"]))
    except Exception:
        res = None
    if res:
        kind, payload, source, index = res
        uri = ("data:image/svg+xml;base64," + base64.b64encode(payload).decode()) if kind == "svg" else _to_data_uri(Image.open(io.BytesIO(payload)))
        ttl = _OK_SECONDS if index == 0 else _FALLBACK_SECONDS
        info = {"source": source, "kind": kind, "bytes": len(payload), "fallback": index != 0}
    else:
        uri = _to_data_uri(_placeholder(rec["abbreviation"], teams.get_team_color(name)))
        ttl = _FAIL_SECONDS
        info = {"source": "(no source reachable)", "kind": "placeholder", "bytes": 0, "fallback": True}
    with _lock:
        _logo_cache[name] = (now + ttl, uri)
        _SOURCES[name] = info
    return uri


def _all_logo_uris(names) -> dict:
    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(zip(names, pool.map(_logo_uri, names)))


def _grid_css(names) -> str:
    now = time.time()
    if _css_cache["expires"] > now and _css_cache["css"]:
        return _css_cache["css"]
    uris = _all_logo_uris(names)
    cols = GRID_COLUMNS
    def scoped(inner_radio, inner_pills):
        return f'[class*="st-key-ba_team_grid_"] {inner_radio}, [class*="st-key-ba_team_pills_"] {inner_pills}'

    css = [f'''
[class*="st-key-ba_team_grid_"], [class*="st-key-ba_team_pills_"], {scoped('[data-testid="stElementContainer"]', '[data-testid="stElementContainer"]')},
{scoped('[data-testid="stRadio"]', '[data-testid="stButtonGroup"]')} {{ width: 100% !important; }}
{scoped('div[data-testid="stRadioGroup"]', 'div[role="toolbar"]')} {{
  display: grid !important; grid-template-columns: repeat({cols}, minmax(0, 1fr)) !important;
  gap: 14px 8px !important; width: 100% !important; padding: 8px 4px 10px !important; align-items: center;
}}
{scoped('label[data-testid="stRadioOption"]', 'button[data-variant="pills"]')} {{
  position: relative; display: block !important; box-sizing: border-box; width: 100% !important; max-width: 84px;
  min-height: 0 !important; height: auto !important; justify-self: center; aspect-ratio: 1 / 1;
  margin: 0 !important; padding: 0 !important; border-radius: 50% !important;
  background-color: #0b0b0b !important; background-repeat: no-repeat !important; background-position: center !important;
  background-size: 68% !important; border: 3px solid var(--ring, #555) !important;
  box-shadow: 0 0 0 1px rgba(255,255,255,.14) !important; opacity: .84; cursor: pointer; overflow: visible !important;
  transition: transform .12s ease, opacity .12s ease, box-shadow .12s ease;
}}
/* the radio dot / pill text stay in the page for screen readers but are not drawn */
{scoped('label[data-testid="stRadioOption"] > div', 'button[data-variant="pills"] > div')} {{
  position: absolute !important; width: 1px !important; height: 1px !important; overflow: hidden !important; clip: rect(0 0 0 0) !important;
}}
/* hover: the logo only gets bigger -- no label, no other change */
{scoped('label[data-testid="stRadioOption"]:hover', 'button[data-variant="pills"]:hover')} {{ transform: scale(1.09); }}
/* selected: ONE thick ring in the team's colour (the 3px border plus 4px more), glowing */
{scoped('label[data-selected="true"]', 'button[aria-pressed="true"]')} {{
  opacity: 1 !important; transform: scale(1.07);
  box-shadow: 0 0 0 4px var(--ring, #fff), 0 0 22px 7px var(--glow, var(--ring, #fff)) !important;
}}
{scoped('label[data-selected="true"]:hover', 'button[aria-pressed="true"]:hover')} {{ transform: scale(1.12); }}
/* no separate keyboard-focus outline: it read as a second ring, and in a radio group the selected (glowing) ring already marks focus */
{scoped('label[data-testid="stRadioOption"]:has(input:focus-visible)', 'button[data-variant="pills"]:focus-visible')} {{ outline: none; }}
/* the app's own radio styling draws a gold underline under a selected option; a logo needs none */
{scoped('label[data-testid="stRadioOption"]::before, [class*="st-key-ba_team_grid_"] label[data-testid="stRadioOption"]::after', 'button[data-variant="pills"]::before, [class*="st-key-ba_team_pills_"] button[data-variant="pills"]::after')} {{ content: none !important; display: none !important; }}
@media (max-width: 640px) {{
  {scoped('div[data-testid="stRadioGroup"]', 'div[role="toolbar"]')} {{ grid-template-columns: repeat(5, minmax(0, 1fr)) !important; gap: 12px 6px !important; }}
  {scoped('label[data-testid="stRadioOption"]', 'button[data-variant="pills"]')} {{ max-width: 62px; border-width: 2.5px !important; }}
}}
''']
    LABEL, BTN = 'label[data-testid="stRadioOption"]', 'button[data-variant="pills"]'
    TEAMS_ONLY = '[class*="st-key-ba_team_grid_"]:not([class*="st-key-ba_team_grid_color_"])'
    COLOR = '[class*="st-key-ba_team_grid_color_"]'
    PILLS = '[class*="st-key-ba_team_pills_"]'
    for i, name in enumerate(names, start=1):
        ring = teams.get_team_color(name)
        # in the colour picker the three swatches come first, so its teams sit three places later
        for scope, kind, idx in ((TEAMS_ONLY, LABEL, i), (COLOR, LABEL, i + 3), (PILLS, BTN, i)):
            css.append(f'{scope} {kind}:nth-of-type({idx}) {{ --ring: {ring}; background-image: url("{uris[name]}") !important; }}')
    for j, (name, (fill, ring, glow)) in enumerate(SPECIAL_SWATCHES.items(), start=1):
        css.append(f'{COLOR} {LABEL}:nth-of-type({j}) {{ --ring: {ring}; --glow: {glow}; background: {fill} !important; background-clip: content-box !important; '
                   f'box-shadow: inset 0 0 0 5px #0b0b0b, 0 0 0 1px rgba(255,255,255,.14) !important; }}')
    # a selected swatch keeps the dark gap between its ring and its fill, with the same single thick glowing ring
    css.append(f'{COLOR} {LABEL}:nth-of-type(-n+3)[data-selected="true"] {{ box-shadow: inset 0 0 0 5px #0b0b0b, 0 0 0 4px var(--ring), 0 0 22px 7px var(--glow, var(--ring)) !important; }}')
    # White / Black / Gold fill the first line by themselves; the first team starts the next line (10 across, or 5 on a phone)
    css.append(f'{COLOR} {LABEL}:nth-of-type(4) {{ grid-column-start: 1 !important; }}')
    out = "\n".join(css)
    _css_cache.update(expires=min(_logo_cache[n][0] for n in names), css=out)         # rebuilt as soon as any logo's entry expires
    return out


def _debug_panel(names):
    """Add ?logos=debug to the dashboard's address to see where each team's logo actually came from."""
    try:
        if str(st.query_params.get("logos", "")).lower() != "debug" or st.session_state.get(_DEBUG_FLAG):
            return
    except Exception:
        return
    st.session_state[_DEBUG_FLAG] = True
    rows = ["| Team | Chosen source | Logo came from | Format | Size |", "|---|---|---|---|---|"]
    recs = teams.team_records_by_name()
    for n in names:
        info = _SOURCES.get(n, {})
        host = re.sub(r"^https?://([^/]+).*", r"\1", info.get("source", "?"))
        rows.append(f"| {n} | {teams.logo_source_for(recs[n]['id'])} | {host}{' (FALLBACK)' if info.get('fallback') else ''} | {info.get('kind', '?')} | {info.get('bytes', 0) / 1024:.1f} KB |")
    with st.expander("Logo sources (debug)", expanded=True):
        st.markdown("\n".join(rows))
        st.caption("Each team's source is set in teams.py (TEAM_LOGO_SOURCE): ESPN for every team except the Celtics. FALLBACK means the chosen source could not be loaded from the server for that team, so the next one is being used until the next retry.")


def _emit_css_once(names):
    if not st.session_state.get(_CSS_FLAG):
        st.markdown(f"<style>{_grid_css(names)}</style>", unsafe_allow_html=True)
        st.session_state[_CSS_FLAG] = True
    _debug_panel(names)


def _safe(key, label) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", str(key or f"auto_{label}"))


def team_grid_radio(label, key=None, *, index=None, default=None, extras=(), extras_first=False, disabled=False, label_visibility="visible",
                    help=None, on_change=None, args=None, kwargs=None):
    """Pick ONE team from the logo grid. Returns the team's full name, or None. `extras` adds colour swatches (White/Black/Gold)."""
    names = teams.teams_alphabetical()
    options = (list(extras) + names) if extras_first else (names + list(extras))
    if default is not None:
        index = options.index(default) if default in options else None
    _emit_css_once(names)
    with st.container(key=f"ba_team_grid_{'color_' if extras_first else ''}{_safe(key, label)}"):
        common = dict(index=index, key=key, horizontal=True, disabled=disabled, label_visibility=label_visibility,
                      help=help, on_change=on_change, args=args, kwargs=kwargs)
        try:
            return st.radio(label, options, width="stretch", **common)
        except TypeError:                                   # a Streamlit without the width option: the CSS below does the job
            return st.radio(label, options, **common)


def team_grid_multi(label, key=None, *, default=None, max_selections=None, disabled=False, label_visibility="visible", help=None,
                    on_change=None, args=None, kwargs=None):
    """Pick SEVERAL teams from the logo grid. Returns a list of full names (in the order they were clicked)."""
    names = teams.teams_alphabetical()
    _emit_css_once(names)
    with st.container(key=f"ba_team_pills_{_safe(key, label)}"):
        common = dict(selection_mode="multi", default=[d for d in (default or []) if d in names], key=key, disabled=disabled,
                      label_visibility=label_visibility, help=help, on_change=on_change, args=args, kwargs=kwargs)
        try:
            chosen = st.pills(label, names, width="stretch", **common)
        except TypeError:
            chosen = st.pills(label, names, **common)
    chosen = list(chosen or [])
    if max_selections and len(chosen) > max_selections:
        st.warning(f"Pick up to {max_selections} teams -- showing the first {max_selections}.")
        chosen = chosen[:max_selections]
    return chosen


# ---------------------------------------------------------------- team dropdowns (a closed box that opens a 5 x 6 grid)
# The page script in app.py closes an open panel when someone clicks outside it, or clicks the team that's already
# chosen: it pairs every container keyed "ba_dd_panel_<id>" with the button inside "ba_dd_toggle_<id>".

_CHEVRON = ("data:image/svg+xml;base64,"
            "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PHBhdGggZD0iTTYgOS41bDYgNiA2LTYiIGZp"
            "bGw9Im5vbmUiIHN0cm9rZT0iI2ZmZmZmZiIgc3Ryb2tlLXdpZHRoPSIyLjQiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2lu"
            "PSJyb3VuZCIvPjwvc3ZnPg==")
PANEL_COLUMNS = 5


def dropdown_panel_css(panel_id, logo_px, mobile_logo_px=52, gap_px=6, pad_px=6):
    """CSS for the open panel "ba_dd_panel_<panel_id>": all 30 logos in a 5 x 6 grid, the panel exactly as wide as that
    grid, compact spacing, and the currently chosen team circled by a spinning gold ring."""
    grid = f'[class*="st-key-ba_dd_panel_{panel_id}"] [class*="st-key-ba_team_grid_"]'
    panel = f'[class*="st-key-ba_dd_panel_{panel_id}"]'

    def width(px):
        return PANEL_COLUMNS * px + (PANEL_COLUMNS - 1) * gap_px + 2 * pad_px + 2 * 4 + 2

    return f"""
    {panel} {{
        width: {width(logo_px)}px !important; max-width: 100% !important; flex: 0 0 auto !important;
        background: linear-gradient(135deg, #1A1A1A 0%, #070707 73%) !important;
        border: 1px solid #2a2a2a !important; border-radius: 8px; padding: 4px !important; gap: 0 !important;
    }}
    {grid} div[data-testid="stRadioGroup"] {{
        grid-template-columns: repeat({PANEL_COLUMNS}, {logo_px}px) !important; justify-content: start !important;
        gap: {gap_px}px !important; padding: {pad_px}px !important;
    }}
    {grid} label[data-testid="stRadioOption"] {{
        width: {logo_px}px !important; max-width: {logo_px}px !important; border-color: transparent !important;
        box-shadow: none !important; background-color: transparent !important; background-size: 84% !important;
    }}
    @keyframes _baRingSpin {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate(360deg); }} }}
    {grid} label[data-testid="stRadioOption"][data-selected="true"] {{
        box-shadow: none !important; transform: none !important; opacity: 1 !important;
    }}
    /* (The app-wide radio style gives every option's ::after a 2px-high, scaleX(0) underline -- the ring undoes both.) */
    {grid} label[data-testid="stRadioOption"][data-selected="true"]::after {{
        content: '' !important; display: block !important; position: absolute !important;
        top: -4px !important; left: -4px !important; right: -4px !important; bottom: -4px !important;
        width: auto !important; height: auto !important; box-sizing: border-box !important;
        transform: rotate(0deg); transform-origin: 50% 50% !important; transition: none !important;
        border-radius: 50%; padding: 3px;
        background: conic-gradient(from 0deg, #8a6410, #F5D370, #fff0b8, #F5D370, #8a6410, #8a6410);
        -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
        -webkit-mask-composite: xor; mask-composite: exclude;
        animation: _baRingSpin 3s linear infinite; pointer-events: none;
    }}
    @media (max-width: 640px) {{
        {panel} {{ width: {width(mobile_logo_px)}px !important; }}
        {grid} div[data-testid="stRadioGroup"] {{ grid-template-columns: repeat({PANEL_COLUMNS}, {mobile_logo_px}px) !important; }}
        {grid} label[data-testid="stRadioOption"] {{ width: {mobile_logo_px}px !important; max-width: {mobile_logo_px}px !important; }}
    }}
    """


def team_dropdown(label, key, *, logo_px=60, placeholder="Select a team", on_select=None):
    """
    A team picker that behaves like a dropdown: a closed box (like the app's other dropdowns) showing the chosen team's
    logo and name with a down arrow; clicking it opens a 5 x 6 grid of all 30 logos right under it. Picking a team
    closes it; so does clicking the box again, clicking the team that's already chosen, or clicking anywhere outside.
    The chosen team is kept in st.session_state[key] (full team name) and returned (None until one is picked).
    """
    open_key, grid_key = f"_ba_dd_open_{key}", f"_ba_dd_grid_{key}"
    current = st.session_state.get(key)
    names = teams.teams_alphabetical()
    if current not in names:
        current = None

    def _toggle():
        st.session_state[open_key] = not st.session_state.get(open_key, False)

    def _picked():
        st.session_state[key] = st.session_state.get(grid_key)
        st.session_state[open_key] = False
        if on_select:
            on_select()

    logo_css = f'background-image: url("{_logo_uri(current)}"), url("{_CHEVRON}") !important;' if current else \
        f'background-image: url("{_CHEVRON}") !important;'
    toggle = f'[class*="st-key-ba_dd_toggle_{key}"]'
    # The label and this dropdown's CSS are ONE element, so two dropdowns side by side line up exactly. Every line is
    # flattened (no indentation, no blank lines) so markdown keeps it all as HTML -- an indented line after </style>
    # would otherwise show up as a code block.
    html = f"""<style>
        {toggle} div[data-testid="stButton"] button {{
            width: 100% !important; min-height: 2.5rem !important; justify-content: flex-start !important;
            padding: 0.25rem 2.4rem 0.25rem {'2.6rem' if current else '0.75rem'} !important;
            background-color: rgba(255, 255, 255, 0.04) !important; border: 1px solid #2a2a2a !important;
            border-radius: 0.5rem !important; box-shadow: none !important;
            background-repeat: no-repeat, no-repeat !important;
            background-position: {'0.55rem center, ' if current else ''}right 0.6rem center !important;
            background-size: {'1.6rem 1.6rem, ' if current else ''}1.1rem 1.1rem !important;
            {logo_css}
        }}
        {toggle} div[data-testid="stButton"] button::before {{ display: none !important; }}
        {toggle} div[data-testid="stButton"] button:hover {{ border-color: #D4AF37 !important; box-shadow: none !important; }}
        {toggle} div[data-testid="stButton"] button p {{
            background: none !important; -webkit-background-clip: border-box !important; background-clip: border-box !important;
            color: {'#f0f0f0' if current else '#9a9a9a'} !important; -webkit-text-fill-color: currentColor !important;
            animation: none !important; font-weight: 400 !important; justify-content: flex-start !important;
            text-align: left !important; margin: 0 !important; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }}
        {toggle} div[data-testid="stButton"] button > div,
        {toggle} div[data-testid="stButton"] button [data-testid="stMarkdownContainer"] {{
            width: 100% !important; justify-content: flex-start !important; text-align: left !important;
            min-width: 0 !important;
        }}
        {toggle} div[data-testid="stButton"] button p::before {{ display: none !important; }}
        {dropdown_panel_css(key, logo_px)}
        </style>
        <div class="ba-dd-label" style="font-size:0.875rem; font-weight:bold; color:#888888; margin:0 0 7px 0;">{label}</div>"""
    st.markdown("\n".join(ln.strip() for ln in html.splitlines() if ln.strip()), unsafe_allow_html=True)
    with st.container(key=f"ba_dd_toggle_{key}"):
        st.button(current or placeholder, key=f"_ba_dd_btn_{key}", on_click=_toggle, width="stretch")
    if st.session_state.get(open_key):
        with st.container(key=f"ba_dd_panel_{key}"):
            team_grid_radio("Team", key=grid_key, default=current, label_visibility="collapsed", on_change=_picked)
    return current
