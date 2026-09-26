"""
org_sections.py -- shared scaffolding for the "Front Office" and
"Coaching" sidebar sections.

Both sections work the same way: pick a team first (a full logo grid,
via team_grid.py), then a compact header (that team's logo, a white
down-arrow, then "| Front Office" / "| Coaching" in the same title style
as every other page) with a row of sub-section tabs across the top.
Clicking the logo or the arrow opens the compact team switcher.

The switcher uses a plain st.button + manual session-state toggle
rather than st.popover -- a popover's own internal structure proved
unreliable to style consistently (a duplicate arrow kept appearing
that a button, a much simpler primitive with no internal chrome of
its own, can't produce).

The two sections share ONE "which team" state -- picking a team in
either one carries over to the other, since they're both just
different views onto the same organization.
"""

import streamlit as st

import team_grid

_SHARED_TEAM_KEY = "_org_team_shared"
_DROPDOWN_OPEN_KEY = "_org_switcher_open"


def _tab_key(section):
    return f"_org_tab_{section}"


def render_section_header(section_name, sub_tabs, subtitle=None):
    """Shows the team picker (first visit) or the compact header + tab
    row (once a team is chosen). Returns (team_name, chosen_tab), or
    (None, None) while still waiting on a team pick -- callers should
    render nothing else in that case, since there's no team context yet."""
    selected = st.session_state.get(_SHARED_TEAM_KEY)

    if not selected:
        st.title(section_name)
        if subtitle:
            st.caption(subtitle)
        st.markdown(f"#### Select a team to open its {section_name.lower()}")
        picked = team_grid.team_grid_radio("Team:", key="_org_pick_shared", index=None, label_visibility="collapsed")
        if picked:
            st.session_state[_SHARED_TEAM_KEY] = picked
            st.session_state[_tab_key(section_name)] = sub_tabs[0]
            st.rerun()
        return None, None

    logo_uri = team_grid._logo_uri(selected)

    def _toggle_switcher():
        st.session_state[_DROPDOWN_OPEN_KEY] = not st.session_state.get(_DROPDOWN_OPEN_KEY, False)

    def _switched():
        picked = st.session_state.get("_org_switch_shared")
        st.session_state[_DROPDOWN_OPEN_KEY] = False
        if picked and picked != st.session_state.get(_SHARED_TEAM_KEY):
            st.session_state[_SHARED_TEAM_KEY] = picked
            st.session_state[_tab_key(section_name)] = sub_tabs[0]

    # Header row: [team logo + down arrow] | Front Office. The logo and the arrow are ONE big invisible button (the
    # logo and a white chevron are its two background pictures), so clicking anywhere on either opens -- and clicking
    # again closes -- the team switcher. The title is a real st.title, so it matches every other page's header.
    toggle = '.st-key-_org_header_row [class*="st-key-ba_dd_toggle_org"] div[data-testid="stButton"] button'
    st.markdown(
        f"""<style>
        .st-key-_org_header_row {{ align-items: center !important; gap: 0 !important; flex-wrap: nowrap !important; }}
        .st-key-_org_header_row div[data-testid="stElementContainer"],
        .st-key-_org_header_row div[data-testid="stButton"] {{ width: auto !important; flex: 0 0 auto !important; }}
        {toggle}, {toggle}:hover, {toggle}:focus, {toggle}:focus-visible, {toggle}:active {{
            width: 97px !important; min-width: 97px !important; height: 64px !important; min-height: 64px !important;
            padding: 0 !important; margin: 0 !important; border: none !important; box-shadow: none !important;
            outline: none !important; cursor: pointer; background-color: transparent !important;
            background-image: url("{logo_uri}"), url("{team_grid._CHEVRON}") !important;
            background-repeat: no-repeat, no-repeat !important;
            background-position: left center, right center !important;
            background-size: 64px 64px, 28px 28px !important;
        }}
        {toggle}::before, {toggle}::after, {toggle} p::before {{ display: none !important; content: none !important; }}
        {toggle} p {{ visibility: hidden; }}
        div[data-testid="stMainBlockContainer"] .st-key-_org_header_row h1 {{
            margin: 0 !important; padding: 0 !important; white-space: nowrap;
        }}
        /* The "|" divider: a bar centred on the logo/arrow line, as tall as the title, with the arrow exactly halfway
           between the logo and it. */
        .st-key-_org_header_row div[data-testid="stElementContainer"]:has(h1) {{
            display: flex !important; align-items: center !important;
        }}
        .st-key-_org_header_row div[data-testid="stElementContainer"]:has(h1)::before {{
            content: ""; flex: 0 0 auto; width: 2px; height: 2.5rem; background: #f0f0f0; border-radius: 1px;
            margin: 0 0.9rem 0 5px;
        }}
        @media (min-width: 641px) {{ .st-key-_org_header_row {{ margin-top: 24px; }} }}
        /* On a phone the logo + arrow + a full-size page title don't fit on one line, so only here the logo is a bit
           smaller and the title scales with the screen (it stays on one line instead of running off the edge). */
        @media (max-width: 640px) {{
            {toggle}, {toggle}:hover, {toggle}:focus, {toggle}:active {{
                width: 79px !important; min-width: 79px !important; height: 48px !important; min-height: 48px !important;
                background-size: 48px 48px, 26px 26px !important;
            }}
            .st-key-_org_header_row h1 {{ font-size: min(2.75rem, 9.5vw) !important; }}
            .st-key-_org_header_row div[data-testid="stElementContainer"]:has(h1)::before {{
                height: 2rem; margin-right: 0.6rem;
            }}
        }}
        div[data-testid="stElementContainer"]:has([data-testid="stRadio"]) {{
            margin-top: -8px !important; margin-bottom: -8px !important;
        }}
        {team_grid.dropdown_panel_css("org", 72)}
        </style>""",
        unsafe_allow_html=True,
    )
    with st.container(key="_org_header_row", horizontal=True, vertical_alignment="center", gap=None):
        with st.container(key="ba_dd_toggle_org", width="content"):
            st.button(" ", key="_org_switch_toggle", on_click=_toggle_switcher)
        st.title(section_name, anchor=False)

    # The switcher: all 30 teams in a 5 x 6 grid, the panel sized to exactly that grid, the current team circled by a
    # spinning gold ring. Picking a team switches to it and closes the panel; clicking the logo/arrow again, clicking
    # the current team, or clicking anywhere outside the panel also closes it (the last two via the page script in
    # app.py, which pairs "ba_dd_panel_org" with the "ba_dd_toggle_org" button).
    if st.session_state.get(_DROPDOWN_OPEN_KEY):
        with st.container(key="ba_dd_panel_org"):
            team_grid.team_grid_radio("Team:", key="_org_switch_shared", default=selected, label_visibility="collapsed",
                                      on_change=_switched)

    chosen_tab = st.radio(
        "Section:", sub_tabs, key=_tab_key(section_name), horizontal=True, label_visibility="collapsed",
    )
    st.markdown("<hr style='margin:2px 0 6px;'>", unsafe_allow_html=True)
    return selected, chosen_tab


def coming_soon(feature_name, needs):
    """A clearly-labeled placeholder for a sub-section that needs a
    real data source this app doesn't have wired up yet, rather than
    filling the space with invented numbers."""
    st.info(
        f"**{feature_name} isn't built out yet.** This needs {needs}, which isn't part of the data "
        "this app currently pulls from. Once there's a real source for it, this tab is exactly where it belongs."
    )
