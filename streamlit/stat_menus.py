"""
stat_menus.py

Every stat menu in the dashboard lists its stats under section headings -- OFFENSE, PLAYMAKING, REBOUNDING, DEFENSE,
OVERALL (stats_config.STAT_SECTIONS) -- in bold grey Arial, with a thin grey line above each heading after the first.

A heading is an entry of the menu itself whose text starts with HEAD (two invisible characters): the dashboard page
(app.py's _PAGE_WATCH_JS) finds those entries in an open menu and styles them as headings, and they can't be clicked.
Should one be picked anyway (the keyboard can reach it), the first stat under it is picked instead.
"""

import streamlit as st

from stats_config import STAT_SECTIONS, get_stat_sections, stat_section

HEAD = "⁣⁣"


def is_head(value):
    return isinstance(value, str) and value.startswith(HEAD)


def head(section):
    return HEAD + str(section).upper()


def with_headers(items):
    """items: [(value, section), ...] -> the menu's options: each section's heading, then its values (sections in
    STAT_SECTIONS order, values in the order given)."""
    options = []
    for sec in STAT_SECTIONS:
        vals = [v for v, s in items if s == sec]
        if vals:
            options.append(head(sec))
            options.extend(vals)
    return options


def _first_after(options, i):
    for o in options[i + 1:]:
        if not is_head(o):
            return o
    for o in options:
        if not is_head(o):
            return o
    return None


def _label(format_func):
    def show(v):
        if is_head(v):
            return v
        return format_func(v) if format_func else v
    return show


def select(label, items, key, value=None, format_func=None, **kwargs):
    """A single-choice stat menu. items: [(value, section)]; value: the one picked at first (default: the first)."""
    options = with_headers(items)
    if not options:
        return None

    def fix():
        v = st.session_state.get(key)
        if is_head(v):
            st.session_state[key] = _first_after(options, options.index(v))

    if key in st.session_state and st.session_state[key] in options and not is_head(st.session_state[key]):
        index = 0                                     # (its own choice wins; 0 means "no default given")
    else:
        if key in st.session_state:
            del st.session_state[key]
        start = value if value in options else _first_after(options, -1)
        index = options.index(start)
    choice = st.selectbox(label, options, index=index, key=key, on_change=fix, format_func=_label(format_func), **kwargs)
    if is_head(choice):
        choice = _first_after(options, options.index(choice))
    return choice


def select_optional(label, items, key, value=None, placeholder=None, on_change=None, format_func=None, **kwargs):
    """A single-choice menu that can also have nothing picked (None) -- e.g. the "Stat:" / "Bradley rating:" /
    "Tendency:" trio, where picking in one empties the other two. items: [(value, section)] (a section of None: a
    plain list without headings); value: the one picked at first (None: nothing)."""
    plain = all(sec is None for _v, sec in items)
    options = [v for v, _s in items] if plain else with_headers(items)
    if not options:
        return None

    def changed():
        v = st.session_state.get(key)
        if is_head(v):
            st.session_state[key] = _first_after(options, options.index(v))
        if on_change:
            on_change()

    extra = {}
    if key in st.session_state:
        cur = st.session_state[key]
        if cur is not None and (cur not in options or is_head(cur)):
            st.session_state[key] = None
    else:
        extra["index"] = options.index(value) if value in options else None
    choice = st.selectbox(label, options, key=key, on_change=changed, placeholder=placeholder,
                          format_func=_label(format_func), **extra, **kwargs)
    if is_head(choice):
        choice = _first_after(options, options.index(choice))
    return choice


def multiselect(label, items, key, default=None, format_func=None, **kwargs):
    """A multiple-choice stat menu. items: [(value, section)]; default: the values picked at first."""
    options = with_headers(items)

    def fix():
        st.session_state[key] = [v for v in st.session_state.get(key, []) if not is_head(v)]

    if key in st.session_state:
        kept = [v for v in st.session_state[key] if v in options and not is_head(v)]
        if kept != st.session_state[key]:
            st.session_state[key] = kept
        chosen = st.multiselect(label, options, key=key, on_change=fix, format_func=_label(format_func), **kwargs)
    else:
        start = [v for v in (default or []) if v in options and not is_head(v)]
        chosen = st.multiselect(label, options, default=start, key=key, on_change=fix, format_func=_label(format_func),
                                **kwargs)
    return [v for v in chosen if not is_head(v)]


# ---------------------------------------------------------------- the dashboard's own stat lists
def stat_items(mode, include_salary=False, exclude_bradley_rating=True, exclude_fields=()):
    """[(label, section)] for every stat of this mode, plus {label: (field, label, source, modes)}."""
    items, by_label = [], {}
    for sec, stats in get_stat_sections(mode, exclude_bradley_rating=exclude_bradley_rating, include_salary=include_salary):
        for s in stats:
            if s[0] in exclude_fields:
                continue
            items.append((s[1], sec))
            by_label[s[1]] = s
    return items, by_label


def stat_select(label, mode, key, include_salary=False, value_field=None, exclude_fields=(), **kwargs):
    """Pick one of the dashboard's stats: returns its (field, label, source, modes)."""
    items, by_label = stat_items(mode, include_salary=include_salary, exclude_fields=exclude_fields)
    start = next((lbl for lbl, s in by_label.items() if s[0] == value_field), None) if value_field else None
    return by_label.get(select(label, items, key=f"{key}_{mode}", value=start, **kwargs))


def stat_multiselect(label, mode, key, include_salary=False, default_n=0, exclude_fields=(), **kwargs):
    """Pick several of the dashboard's stats: returns [(field, label, source, modes), ...]."""
    items, by_label = stat_items(mode, include_salary=include_salary, exclude_fields=exclude_fields)
    default = [lbl for lbl, _sec in items[:default_n]] if default_n else None
    return [by_label[v] for v in multiselect(label, items, key=f"{key}_{mode}", default=default, **kwargs) if v in by_label]


def lineup_items(stats):
    """[(label, section)] for a list of lineup stats [(field, label, lower_is_better), ...]."""
    return [(lbl, stat_section(f, "advanced")) for f, lbl, _low in stats]


# ---------------------------------------------------------------- stats named only by a column (Upload Stats)
_NAME_SECTIONS = [
    ("Defense", ("OPP", "DEF_RATING", "DEF_RTG", "DRTG", "STL", "STEAL", "BLK", "BLOCK", "PF", "FOUL", "D_FG", "CONTEST",
                 "DEFLECT", "CHARGE")),
    ("Rebounding", ("REB", "ORB", "DRB", "TRB", "BOX", "OFF_REB", "DEF_REB", "TOTAL_REB")),
    ("Playmaking", ("AST", "TOV", "=TO", "TURNOVER", "ASSIST", "PASS", "POTENTIAL")),
    ("Offense", ("PTS", "POINT", "FG", "3P", "2P", "FT", "TS", "EFG", "OFF", "USG", "SHOT", "SCOR", "PPS", "PAINT",
                 "FAST", "SECOND", "BENCH")),
]


def name_section(col):
    """A best guess at which section a stat named only by its column belongs in (Overall when unsure)."""
    c = str(col).upper().replace("%", "_PCT").replace(" ", "_").replace("-", "_")
    for sec, keys in _NAME_SECTIONS:
        if any((c == k[1:]) if k.startswith("=") else (c == k or c.startswith(k)) for k in keys):
            return sec
    field = {"MINUTES": "MIN", "PLUS_MINUS": "PLUS_MINUS"}.get(c, c)
    return stat_section(field)


def select_names(label, names, key, value=None, **kwargs):
    """A stat menu for stats known only by their names (e.g. an uploaded file's columns)."""
    return select(label, [(n, name_section(n)) for n in names], key=key, value=value, **kwargs)
