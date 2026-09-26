"""
pickers.py

Small, reusable pickers shared by the dashboard pages and AI Search.

picture_picker(): the "Show pictures for" dropdown under a scatter plot. It opens a checklist with "Select all" (or
"Select top N" when at most N can be drawn) and
"Select none" at the very top, a divider line, then every name on the plot; each chosen name has a gold check next
to it. "Select all" is checked exactly when every name is chosen, and "Select none" is the only checked line when no
name is. Players who are checked are drawn as their picture (headshot / logo); everyone else as a plain dot.
"""

import hashlib

import streamlit as st

_CSS_DONE_KEY = "_ba_picture_picker_css"

_CSS = """
<style>
/* the closed box: looks like the app's other dropdowns (full width, text on the left, arrow on the right) */
[class*="st-key-ba_picsbtn_"] [data-testid="stPopoverButton"] {
    width: 100% !important; min-height: 2.5rem !important; justify-content: space-between !important;
    background-color: rgba(255, 255, 255, 0.04) !important; border: 1px solid #2a2a2a !important;
    border-radius: 0.5rem !important; box-shadow: none !important; padding: 0.25rem 0.75rem !important;
}
[class*="st-key-ba_picsbtn_"] [data-testid="stPopoverButton"]:hover { border-color: #D4AF37 !important; }
[class*="st-key-ba_picsbtn_"] [data-testid="stPopoverButton"] > div { width: 100% !important; justify-content: space-between !important; }
[class*="st-key-ba_picsbtn_"] [data-testid="stPopoverButton"] > div > div:first-child {
    flex: 1 1 auto !important; justify-content: flex-start !important; text-align: left !important; min-width: 0;
}
[class*="st-key-ba_picsbtn_"] [data-testid="stPopoverButton"] p {
    color: #f0f0f0 !important; -webkit-text-fill-color: #f0f0f0 !important; background: none !important;
    animation: none !important; font-weight: 400 !important; text-align: left !important;
}
[class*="st-key-ba_picsbtn_"] [data-testid="stPopoverButton"] p::before,
[class*="st-key-ba_picsbtn_"] [data-testid="stPopoverButton"]::before { display: none !important; }
/* the open list: compact rows, thin edges, scrolls when long */
[data-testid="stPopoverBody"]:has([class*="st-key-ba_pics_"]) {
    max-height: min(60vh, 520px); overflow-y: auto; min-width: 240px; padding: 6px 10px 6px 6px !important;
    background: linear-gradient(135deg, #1A1A1A 0%, #070707 73%) !important; border: 1px solid #2a2a2a !important;
    color: #e6e6e6 !important;
}
[class*="st-key-ba_pics_"] { gap: 0 !important; padding: 0 !important; }
[class*="st-key-ba_pics_"] [data-testid="stElementContainer"] { margin: 0 !important; }
[class*="st-key-ba_pics_"] [data-testid="stCheckbox"] label {
    padding: 4px 4px !important; width: 100%; cursor: pointer; gap: 6px !important;
    background: none !important; box-shadow: none !important;
}
/* the divider: a line under "Select none", exactly halfway between it and the first name */
[class*="st-key-ba_pics_"] [class*="st-key-_pp_none_"] {
    border-bottom: 1px solid #3a3730 !important; padding-bottom: 5px !important; margin-bottom: 5px !important;
    width: 100% !important; align-self: stretch !important;
}
/* no box -- just a gold check beside a chosen name (an empty space of the same width beside the others) */
[class*="st-key-ba_pics_"] [data-testid="stCheckbox"] label > div:not([data-testid]) {
    background: transparent !important; border: none !important; box-shadow: none !important;
    width: 14px !important; min-width: 14px !important; height: 16px !important; margin: 0 !important;
}
[class*="st-key-ba_pics_"] [data-testid="stCheckbox"] label > div:not([data-testid]) svg { width: 14px; height: 12px; }
[class*="st-key-ba_pics_"] [data-testid="stCheckbox"] label > div:not([data-testid]) svg polyline {
    stroke: #D4AF37 !important; stroke-width: 2.2px !important; fill: none !important;
}
[class*="st-key-ba_pics_"] [data-testid="stCheckbox"] label:not([data-selected="true"]) > div:not([data-testid]) svg {
    visibility: hidden;
}
[class*="st-key-ba_pics_"] [data-testid="stCheckbox"] p {
    font-weight: 400 !important; font-size: 0.95rem !important; color: #d9d9d9 !important;
    -webkit-text-fill-color: #d9d9d9 !important; background: none !important; animation: none !important;
}
[class*="st-key-ba_pics_"] [data-testid="stCheckbox"] label[data-selected="true"] p {
    color: #ffffff !important; -webkit-text-fill-color: #ffffff !important;
}
</style>
"""


def _emit_css():
    st.markdown(_CSS, unsafe_allow_html=True)


def picture_picker(names, key, noun="players", label="Show pictures for:", default=None, none_text="None (dots only)",
                   max_pick=None, total=None):
    """
    The "Show pictures for" dropdown. names: every name on the plot (in the order to list them). Returns the set of
    names that should show their picture. Starts with everyone chosen (or just `default`, when given), and starts over
    whenever the set of names changes -- e.g. a new RUN with different filters. The same checklist also picks which
    results to draw in Search by Criteria's other tools.

    max_pick: at most this many can be chosen (e.g. 30 lineups in one chart). When the list is longer, a line under
    the label says so, "Select all" becomes "Select top N" (the first N names), and checking one more name than that is
    refused. total: how many results there are in all, when `names` only lists the first of them.
    """
    names = list(dict.fromkeys(str(n) for n in names))
    capped = bool(max_pick) and len(names) > int(max_pick)
    top = names[:int(max_pick)] if capped else names
    safe = hashlib.md5(key.encode()).hexdigest()[:10]
    sel_key, sig_key = f"_pp_sel_{safe}", f"_pp_sig_{safe}"
    all_key, none_key = f"_pp_all_{safe}", f"_pp_none_{safe}"
    warn_key = f"_pp_warn_{safe}"
    name_keys = [f"_pp_n_{safe}_{i}" for i in range(len(names))]
    sig = hashlib.md5("␟".join(names).encode()).hexdigest()

    def _sync(selected):
        chosen = set(selected)
        for k, n in zip(name_keys, names):
            st.session_state[k] = n in chosen
        st.session_state[all_key] = len(names) > 0 and (chosen == set(top))
        st.session_state[none_key] = len(chosen) == 0
        st.session_state[sel_key] = [n for n in names if n in chosen]

    if st.session_state.get(sig_key) != sig:
        st.session_state[sig_key] = sig
        _sync(top if default is None else [n for n in names if n in set(map(str, default))][:len(top)])
    elif any(k not in st.session_state for k in name_keys + [all_key, none_key]):
        # Streamlit forgets a checkbox's state once it isn't drawn (e.g. after visiting another page), while the saved
        # selection is kept -- put the checkboxes back in line with it before drawing them
        _sync(st.session_state.get(sel_key, top))

    def _on_all():
        _sync(top if st.session_state.get(all_key) else [])

    def _on_none():
        # checking "Select none" clears everything; unchecking it while nothing is chosen leaves it checked
        _sync([] if st.session_state.get(none_key) else st.session_state.get(sel_key, []))

    def _on_name():
        picked = [n for k, n in zip(name_keys, names) if st.session_state.get(k)]
        if capped and len(picked) > int(max_pick):
            st.session_state[warn_key] = True                  # one too many: that last check is undone
            _sync(st.session_state.get(sel_key, []))
            return
        st.session_state[warn_key] = False
        _sync(picked)

    selected = st.session_state.get(sel_key, top)
    if not names:
        summary = f"No {noun}"
    elif len(selected) == len(names):
        summary = f"All {len(names)} {noun}"
    elif capped and set(selected) == set(top):
        summary = f"Top {len(top)} of {len(names)} {noun}"
    elif not selected:
        summary = none_text
    else:
        summary = f"{len(selected)} of {len(names)} {noun}"

    _emit_css()
    st.markdown(f'<div style="font-size:0.875rem;font-weight:bold;color:#888888;margin:0 0 7px 0;">{label}</div>',
                unsafe_allow_html=True)
    if capped:
        count = max(int(total or 0), len(names))
        more = (f" (the top {len(names)} are in this list)" if count > len(names) else "")
        st.markdown(f'<div style="font-size:0.8rem;color:#9d9d9d;margin:-3px 0 7px 0;">You can select up to '
                    f'{int(max_pick)} of the {count} {noun} to display in the visualization{more}.</div>',
                    unsafe_allow_html=True)
    with st.container(key=f"ba_picsbtn_{safe}"):
        try:
            pop = st.popover(summary, width="stretch")
        except TypeError:
            pop = st.popover(summary, use_container_width=True)
    with pop:
        with st.container(key=f"ba_pics_{safe}"):
            if st.session_state.get(warn_key):
                st.markdown(f'<div style="font-size:0.8rem;color:#F5D370;margin:2px 4px 4px;">Only {int(max_pick)} '
                            f'can be displayed at once -- uncheck one first.</div>', unsafe_allow_html=True)
            st.checkbox(f"Select top {len(top)}" if capped else "Select all", key=all_key, on_change=_on_all)
            st.checkbox("Select none", key=none_key, on_change=_on_none)
            for k, n in zip(name_keys, names):
                st.checkbox(n, key=k, on_change=_on_name)
    return set(st.session_state.get(sel_key, top))
