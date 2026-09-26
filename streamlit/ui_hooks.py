"""
ui_hooks.py -- process-wide Streamlit hooks: chart text colour + team-logo badges.

WHY THIS IS A MODULE AND NOT CODE AT THE TOP OF app.py
  Streamlit re-runs the whole script on every click, in a fresh namespace, but the `streamlit` package itself is
  imported once per SERVER PROCESS and shared by every visitor. Wrapping st.pyplot / st.selectbox from inside the
  script therefore stacked one more wrapper on every rerun -- from every visitor, permanently -- until Python's
  ~1000-call limit was reached and every chart and every picker raised RecursionError until the server restarted.
  (Confirmed with a minimal app: the wrapper depth grew by exactly one per rerun and was shared across visitors.)

  These hooks are installed exactly once per process. They keep no state of their own and never read the script's
  globals: everything that belongs to one visitor lives in st.session_state, so two people using the dashboard at
  the same moment cannot see each other's team logos.
"""

import functools
import re
import time
import unicodedata
import uuid

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

import data_availability as da
from team_grid import begin_run as _grid_begin_run, team_grid_multi, team_grid_radio
from teams import _player_meta, get_team_logo_url, team_records_by_name
from visuals import figure_has_images, recolor_white_text, stamp_team_logos

_PICKS_KEY = "_ba_team_picks"                                   # teams picked so far in THIS visitor's current run
_STAMP_CATEGORIES = ("Search by Team", "On/Off Lineup Network")  # pages whose charts get a logo header strip
_HOOKS_VERSION = 5
_CTX_KEY = "_ba_ctx"                                              # what this visitor has picked so far in THIS run


def begin_run():
    """Call once at the top of every script run: this visitor's team picks start empty."""
    st.session_state[_PICKS_KEY] = []
    st.session_state[_CTX_KEY] = {"viz": None, "sources": [], "season": None, "subject": None}
    _grid_begin_run()


def _is_team_list(options) -> bool:
    """True if `options` is the app's list of NBA teams (compared by content: Streamlit hands each run a fresh copy)."""
    try:
        return isinstance(options, (list, tuple)) and set(options) == set(team_records_by_name())
    except TypeError:
        return False


def _maybe_stamp_team_logos(fig):
    picks = list(dict.fromkeys(st.session_state.get(_PICKS_KEY, [])))
    if not (1 <= len(picks) <= 2) or getattr(fig, "_ba_badged", False):
        return
    if st.session_state.get("category_radio") not in _STAMP_CATEGORIES:
        return
    try:
        if figure_has_images(fig):                # the chart already draws logos/headshots of its own
            return
        records = team_records_by_name()
        stamp_team_logos(fig, [get_team_logo_url(records[t]["id"]) for t in picks if t in records])
    except Exception:
        pass                                      # a logo is decoration: never let it break a chart


def prepare_figure(fig):
    """Everything the st.pyplot hook does to a chart before it is shown (the team-logo header strip and the White/Black
    chart text colour) -- shared with app.py's interactive (hover) chart renderer, so a chart looks the same either way."""
    if fig is not None and hasattr(fig, "findobj"):
        _maybe_stamp_team_logos(fig)
        recolor_white_text(fig, st.session_state.get("_global_chart_text_color", "white"))


def _install_pyplot(true_pyplot):
    def pyplot_with_text_color(fig=None, *args, **kwargs):
        if fig is not None and hasattr(fig, "findobj"):
            prepare_figure(fig)
        if st.session_state.get("_global_chart_text_color") == "black":
            # A soft white glow around the chart image for black-text mode, applied as a display-time CSS filter (so it is
            # never baked into a downloaded image). Fresh uuid key: a shared counter would collide across visitors.
            glow_key = f"chart_glow_{uuid.uuid4().hex}"
            st.markdown(
                f"<style>.st-key-{glow_key} img {{ filter: drop-shadow(0 0 10px rgba(255, 255, 255, 0.75)); }}</style>",
                unsafe_allow_html=True,
            )
            with st.container(key=glow_key):
                return true_pyplot(fig, *args, **kwargs)
        return true_pyplot(fig, *args, **kwargs)
    pyplot_with_text_color._ba_hook = True
    st.pyplot = pyplot_with_text_color


def _ctx():
    c = st.session_state.get(_CTX_KEY)
    if c is None:
        c = st.session_state[_CTX_KEY] = {"viz": None, "sources": [], "season": None, "subject": None}
    return c


@functools.lru_cache(maxsize=1)
def _stat_maps():
    """({stat label: data source}, {stat category: {data sources}}) from stats_config, for both player and team mode."""
    import stats_config
    label_src, cat_src = {}, {}
    for mode in ("player", "team"):
        try:
            cats = stats_config.get_stats_for_mode(mode, exclude_bradley_rating=True)
        except Exception:
            continue
        for cat, stats in cats:
            for t in stats:
                src = da.STAT_SOURCE_MAP.get(t[2], "season_stats")
                label_src[t[1]] = src
                cat_src.setdefault(cat, set()).add(src)
    return label_src, cat_src


def _record_stats(value):
    """Remember which data source any stat (or stat category) picked so far needs, so the Season list can follow it."""
    try:
        label_src, cat_src = _stat_maps()
        for v in (value if isinstance(value, (list, tuple)) else [value]):
            if isinstance(v, str):
                if v in label_src:
                    _ctx()["sources"].append(label_src[v])
                elif v in cat_src:
                    _ctx()["sources"].extend(cat_src[v])
    except Exception:
        pass


def _fold(name):
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()


_spans_cache = {"at": 0.0, "val": {}}


def _spans_by_name():
    """{accent-free player name: (first season year, last season year)}; {} if career data is unavailable (nobody is hidden)."""
    now = time.time()
    if _spans_cache["val"] and now - _spans_cache["at"] < 3600:
        return _spans_cache["val"]
    if not _spans_cache["val"] and now - _spans_cache["at"] < 60:
        return {}
    _spans_cache["at"] = now
    try:
        import nba_data
        spans = nba_data.get_player_spans()
    except Exception:
        spans = {}
    out = {}
    for pid, (nm, _active) in _player_meta().items():
        sp = spans.get(pid)
        if sp:
            k = _fold(nm)
            cur = out.get(k)
            out[k] = (min(cur[0], sp[0]), max(cur[1], sp[1])) if cur else sp
    _spans_cache["val"] = out
    return out


def _sources_now(key=None):
    ctx = _ctx()
    return da.required_sources(category=st.session_state.get("category_radio"), viz=ctx["viz"],
                               adv_category=st.session_state.get("adv_category"), stat_sources=ctx["sources"], key=key)


def _pick_team_ids():
    recs = team_records_by_name()
    return [recs[n]["id"] for n in dict.fromkeys(st.session_state.get(_PICKS_KEY, [])) if n in recs]


def _drop_stale(key, keep):
    """A remembered choice that is no longer offered (e.g. a season the new visualization has no data for) is dropped, not kept."""
    if key and key in st.session_state and st.session_state[key] not in keep and st.session_state[key] is not None:
        try:
            del st.session_state[key]
        except Exception:
            pass


def _clamp_index(args, kwargs, n):
    args = list(args)
    idx = args[0] if args else kwargs.get("index", 0)
    if isinstance(idx, int) and idx >= n:
        if args:
            args[0] = 0
        else:
            kwargs = dict(kwargs, index=0)
    return tuple(args), kwargs


_PLAYER_LABEL = re.compile(r"\b(player|players|versus)\b", re.I)


def _is_player_pool(label, options):
    return (isinstance(label, str) and bool(_PLAYER_LABEL.search(label)) and isinstance(options, (list, tuple))
            and len(options) > 1000 and isinstance(options[0], str))


# Every player search bar matches the typed text against the START of a first or last name (or any later part of the
# name) -- "lebron" finds LeBron James and nobody else, "james" finds LeBron James and James Harden. Streamlit's own
# filters can't do that ("fuzzy" matches any letters in order, which is why Jaylen Brown came up for "lebron";
# "prefix" only matches the start of the whole name). So each option's label carries an invisible marker (U+2063,
# drawn as nothing) and the page's filter treats a marked label as "does any word start with what was typed" -- see
# the String.prototype.startsWith patch installed in the page by app.py. The value returned is the plain name.
WORD_PREFIX_MARK = "\u2063"


def _is_player_picker(label, options):
    return (isinstance(label, str) and bool(_PLAYER_LABEL.search(label)) and isinstance(options, (list, tuple))
            and len(options) > 0 and all(isinstance(o, str) for o in options[:50]))


def _word_prefix_kwargs(kwargs):
    kwargs = dict(kwargs)
    inner = kwargs.get("format_func") or str
    kwargs["format_func"] = lambda o, _f=inner: f"{_f(o)}{WORD_PREFIX_MARK}"
    kwargs["filter_mode"] = "prefix"
    return kwargs


def _call_word_prefix(true_call, label, options, args, kwargs):
    try:
        return true_call(label, options, *args, **_word_prefix_kwargs(kwargs))
    except TypeError:                               # a Streamlit without filter_mode: plain behaviour
        return true_call(label, options, *args, **kwargs)


def _filter_player_pool(options):
    """Only players with data for what has been picked: their career overlaps the visualization's data range (and the chosen season, if any)."""
    spans = _spans_by_name()
    if not spans:
        return list(options)
    ctx = _ctx()
    lo = da.min_start_year(_sources_now())
    season_year = da.season_start(ctx["season"]) if ctx["season"] else None
    keep = [n for n in options if da.player_eligible(spans.get(n), lo, season_year)]
    return keep or list(options)


def _season_call(true_call, label, options, args, kwargs):
    ctx = _ctx()
    sources = _sources_now(kwargs.get("key"))
    team_ids = _pick_team_ids()
    keep = da.filter_seasons(options, sources, team_ids)
    if len(keep) == len(options):
        value = true_call(label, options, *args, **kwargs)
    elif not keep:
        st.warning(da.explain_empty(sources, ctx.get("subject"), team_ids))
        return None
    else:
        args, kwargs = _clamp_index(args, kwargs, len(keep))
        _drop_stale(kwargs.get("key"), keep)
        value = true_call(label, keep, *args, **kwargs)
    if value:
        ctx["season"] = value
    return value


def _route_selectbox(true_call, label, options, args, kwargs, container=None):
    """Every selectbox in the app goes through here: team lists become the logo grid; season lists and player lists are cut
    down to what has data; and what was picked is remembered (visualization, stats, subject) so later pickers can follow it."""
    if isinstance(label, str) and re.search(r"\bteams?\b", label, re.I) and _is_team_list(options):
        index = args[0] if args else kwargs.get("index", 0)
        default = options[index] if isinstance(index, int) and 0 <= index < len(options) else None
        def grid():
            return team_grid_radio(label, kwargs.get("key"), default=default, disabled=kwargs.get("disabled", False),
                                   label_visibility=kwargs.get("label_visibility", "visible"), help=kwargs.get("help"),
                                   on_change=kwargs.get("on_change"), args=kwargs.get("args"), kwargs=kwargs.get("kwargs"))
        if container is not None:
            with container:
                value = grid()
        else:
            value = grid()
        if value:
            st.session_state.setdefault(_PICKS_KEY, []).append(value)
        return value
    if da.is_season_list(options):
        value = _season_call(true_call, label, options, args, kwargs)
    elif _is_player_pool(label, options):
        keep = _filter_player_pool(options)
        _drop_stale(kwargs.get("key"), keep)
        value = _call_word_prefix(true_call, label, keep, args, kwargs)
        if value:
            _ctx()["subject"] = value
    elif _is_player_picker(label, options):
        value = _call_word_prefix(true_call, label, options, args, kwargs)
    else:
        value = true_call(label, options, *args, **kwargs)
    if label == "Visualization:" and value:
        _ctx()["viz"] = value
    _record_stats(value)
    return value


def _route_multiselect(true_call, label, options, args, kwargs, container=None):
    if isinstance(label, str) and re.search(r"\bteams?\b", label, re.I) and _is_team_list(options):
        default = args[0] if args else kwargs.get("default")
        def grid():
            return team_grid_multi(label, kwargs.get("key"), default=default if isinstance(default, (list, tuple)) else None,
                                   max_selections=kwargs.get("max_selections"), disabled=kwargs.get("disabled", False),
                                   label_visibility=kwargs.get("label_visibility", "visible"), help=kwargs.get("help"),
                                   on_change=kwargs.get("on_change"), args=kwargs.get("args"), kwargs=kwargs.get("kwargs"))
        if container is not None:
            with container:
                return grid()
        return grid()
    if _is_player_pool(label, options):
        keep = _filter_player_pool(options)
        _drop_stale(kwargs.get("key"), keep)
        return _call_word_prefix(true_call, label, keep, args, kwargs)
    if _is_player_picker(label, options):
        return _call_word_prefix(true_call, label, options, args, kwargs)
    value = true_call(label, options, *args, **kwargs)
    _record_stats(value)
    return value


def _install_selectbox(true_selectbox, true_multiselect):
    def selectbox_hook(label, options, *args, **kwargs):
        return _route_selectbox(true_selectbox, label, options, args, kwargs)

    def multiselect_hook(label, options, *args, **kwargs):
        return _route_multiselect(true_multiselect, label, options, args, kwargs)

    # pickers placed inside columns / containers / the sidebar (c1.selectbox(...)) do not go through st.selectbox
    def dg_selectbox(self, label, options, *args, **kwargs):
        return _route_selectbox(lambda l, o, *a, **k: DeltaGenerator._ba_true_selectbox(self, l, o, *a, **k), label, options, args, kwargs, container=self)

    def dg_multiselect(self, label, options, *args, **kwargs):
        return _route_multiselect(lambda l, o, *a, **k: DeltaGenerator._ba_true_multiselect(self, l, o, *a, **k), label, options, args, kwargs, container=self)

    for fn in (selectbox_hook, multiselect_hook, dg_selectbox, dg_multiselect):
        fn._ba_hook = True
    st.selectbox, st.multiselect = selectbox_hook, multiselect_hook
    DeltaGenerator.selectbox, DeltaGenerator.multiselect = dg_selectbox, dg_multiselect


def install():
    """Idempotent: does real work only the first time in a server process, whichever visitor gets there first."""
    if getattr(st, "_ba_hooks_version", None) == _HOOKS_VERSION:
        return
    # Remember the genuine Streamlit functions once; hooks always call THESE, never each other.
    for name in ("pyplot", "selectbox", "multiselect"):
        if not hasattr(st, f"_ba_true_{name}"):
            setattr(st, f"_ba_true_{name}", getattr(st, name))
    for name in ("selectbox", "multiselect"):
        if not hasattr(DeltaGenerator, f"_ba_true_{name}"):
            setattr(DeltaGenerator, f"_ba_true_{name}", getattr(DeltaGenerator, name))
    _install_pyplot(st._ba_true_pyplot)
    _install_selectbox(st._ba_true_selectbox, st._ba_true_multiselect)
    st._ba_hooks_version = _HOOKS_VERSION
