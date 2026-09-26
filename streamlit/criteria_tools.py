"""
criteria_tools.py

Search by Criteria's "Criteria Tool" options beyond the original Stats (Scatter Plot) search:

- Lineups (Lineup Network): every 2-, 3-, 4- or 5-man lineup in the league, filtered by minutes together and any
  lineup stat, drawn as the same Lineup Network the On/Off page uses (with each lineup's league rank in its pop-up).
- Shots by area (Shot Chart): circle any part of the court (or pick a quick area), set an attempts / makes / FG%
  minimum, and get every player who qualifies -- each drawn as a shot chart zoomed in on exactly that area.
- Passing (Passing Web): players who set up (or finish) a given number of assisted baskets from a given kind of
  shot, drawn as Passing Webs. The search itself is ONE pbpstats.com request (its season totals); pbpstats refuses
  bursts of requests, so the old 30-teams-at-once download failed on the server.

Every tool lists all of its results, then "Chart Color" and RUN, then the checklist of what to draw (up to 30).

app.py hands its shared helpers over in `ctx` (loading animation, RUN button, chart display, name lookups ...), the
same way it does for ai_search.py.
"""

import html
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from nba_api.stats.static import teams as _static_teams

import nba_data
import pickers
import visuals
import hotspots as hover
from teams import get_player_headshot_url

TOOLS = ["Stats (Scatter Plot)", "Lineups (Lineup Network)", "Shots by area (Shot Chart)", "Passing (Passing Web)"]
CAPTIONS = {
    TOOLS[0]: "Filter the whole league by age, height, salary, and any combination of stats, then generate a "
              "scatter plot of the players that fit the criteria.",
    TOOLS[1]: "Every 2, 3, 4 or 5-man lineup in the league, filtered by minutes played together and any lineup stat, "
              "drawn as a Lineup Network.",
    TOOLS[2]: "Circle any area of the court, set an efficiency, attempts and/or makes minimum, and see every player "
              "who qualifies \u2014 each with a shot chart zoomed in on exactly that area.",
    TOOLS[3]: "Players who set up (or finish) assisted baskets from a chosen kind of shot, drawn as Passing Webs.",
}

_court_draw = components.declare_component(
    "court_draw", path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "components", "court_draw"))

_TEAM_ABBR = {t["id"]: t["abbreviation"] for t in _static_teams.get_teams()}
_TEAM_ID_BY_NAME = {t["full_name"]: t["id"] for t in _static_teams.get_teams()}


def _count_line(text):
    """The "N players match" line, in light text whatever theme the viewer's browser uses."""
    st.markdown(f'<div class="crit-count">{html.escape(text)}</div>', unsafe_allow_html=True)


def _note(text, strong=False):
    """A small grey note (st.caption can come out too dark on this page in a light-mode browser)."""
    st.markdown(f'<div class="crit-note{" strong" if strong else ""}">{html.escape(text)}</div>', unsafe_allow_html=True)


def _html_table(df, max_height=380):
    """A compact results table drawn in the dashboard's own dark style (st.dataframe follows the browser's light/dark
    setting, which can put a white table on this dark page). Scrolls inside itself when long."""
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    body = []
    for _, r in df.iterrows():
        cells = []
        for c in df.columns:
            v = r[c]
            num = isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool)
            if num and pd.isna(v):
                txt = "–"
            elif isinstance(v, (float, np.floating)):
                txt = f"{v:,.1f}"
            elif isinstance(v, (int, np.integer)):
                txt = f"{v:,}"
            else:
                txt = html.escape(str(v))
            cells.append(f'<td class="{"num" if num else ""}">{txt}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
    st.markdown(f'<div class="crit-table" style="max-height:{max_height}px"><table><thead><tr>{head}</tr></thead>'
                f'<tbody>{"".join(body)}</tbody></table></div>', unsafe_allow_html=True)


_TABLE_CSS = """
<style>
.crit-count { color:#f0f0f0; font-weight:700; font-size:1.02rem; margin:6px 0 2px; }
.crit-note { color:#9d9d9d; font-size:0.85rem; margin:2px 0 6px; }
.crit-note.strong { color:#d8d8d8; font-size:0.92rem; }
.crit-table { overflow:auto; border:1px solid #2a2a2a; border-radius:10px; background:rgba(255,255,255,0.02); }
.crit-table table { border-collapse:collapse; width:100%; font-size:0.86rem; font-variant-numeric:tabular-nums; }
.crit-table th { position:sticky; top:0; background:#141414; color:#D4AF37; text-align:left; font-weight:600;
  padding:8px 10px; border-bottom:1px solid #3a3326; white-space:nowrap; }
.crit-table td { color:#e6e6e6; padding:7px 10px; border-bottom:1px solid #222; }
.crit-table td.num { text-align:right; white-space:nowrap; }
.crit-table tr:hover td { background:rgba(212,175,55,0.06); }
</style>
"""


def inject_css():
    st.markdown(_TABLE_CSS, unsafe_allow_html=True)


def count_line(text):
    _count_line(text)


def render(tool, season, ctx):
    if tool == TOOLS[1]:
        render_lineups(ctx, season)
    elif tool == TOOLS[2]:
        render_shots_by_area(ctx, season)
    elif tool == TOOLS[3]:
        render_passing(ctx, season)


def range_filters(df, choices, key_prefix):
    """"Add criteria:" -> one range slider per chosen stat (percentages shown as whole percent), applied to df."""
    out = df
    for field, label in choices:
        if field not in out.columns:
            continue
        vals = pd.to_numeric(out[field], errors="coerce")
        if not vals.notna().any():
            continue
        is_pct = field.endswith("_PCT")
        scale = 100 if is_pct else 1
        lo, hi = float(vals.min()) * scale, float(vals.max()) * scale
        if lo >= hi:
            continue
        if is_pct or hi > 10:
            lo, hi, step = int(np.floor(lo)), int(np.ceil(hi)), 1
        else:
            lo, hi, step = round(lo, 1), round(hi, 1), 0.1
        pick = st.slider(label, lo, hi, (lo, hi), step=step, key=f"{key_prefix}_{field}",
                         format="%d%%" if is_pct else None)
        keep = vals.between(pick[0] / scale, pick[1] / scale)
        out = out[keep.reindex(out.index, fill_value=False)]
    return out


def _team_ids(names):
    return {_TEAM_ID_BY_NAME[n] for n in names or [] if n in _TEAM_ID_BY_NAME}


# ================================================================ Lineups (Lineup Network)

_LINEUP_STATS = [("NET_RATING", "Net Rating", False), ("OFF_RATING", "Offensive Rating", False),
                 ("DEF_RATING", "Defensive Rating", True), ("PLUS_MINUS", "Plus-Minus", False),
                 ("MIN", "Minutes Together", False), ("GP", "Games Together", False),
                 ("TS_PCT", "True Shooting %", False), ("EFG_PCT", "Effective FG%", False),
                 ("AST_PCT", "Assist %", False), ("REB_PCT", "Rebound %", False),
                 ("TM_TOV_PCT", "Turnover %", True), ("PACE", "Pace", False)]


LINEUP_STATS = _LINEUP_STATS            # (field, label, lower-is-better) -- also used by the On/Off Lineup Network page
MAX_LINEUPS_DRAWN = 30
PICKER_LIST_MAX = 400                   # longest list a "to draw" checklist shows (the results table shows everything)


def render_lineups(ctx, season):
    size_label = st.radio("Lineup size:", ["Two-Man Lineup", "Three-Man Lineup", "Four-Man Lineup", "Five-Man Lineup"],
                          horizontal=True, index=3, key="crit_lu_size")
    size = {"Two-Man Lineup": 2, "Three-Man Lineup": 3, "Four-Man Lineup": 4, "Five-Man Lineup": 5}[size_label]
    min_minutes = st.number_input("Minimum minutes played together:", min_value=0, max_value=3000, value=100, step=10,
                                  key="crit_lu_min", help="Lineups below this are left out, and every league rank "
                                                          "is counted among the lineups above it.")
    with ctx["code_loading_animation"](f"Downloading every {size}-man lineup in the league",
                                       code=nba_data.get_league_lineup_combos):
        lg = ctx["league_lineups"](season, size)
    if lg is None or lg.empty:
        st.error(f"Couldn't load the league's {size}-man lineups for {season} -- try again in a minute.")
        return
    lg = lg.copy()
    for f, _, _ in _LINEUP_STATS:
        if f in lg.columns:
            lg[f] = pd.to_numeric(lg[f], errors="coerce")
    value_col = "NET_RATING" if "NET_RATING" in lg.columns else ("PLUS_MINUS" if "PLUS_MINUS" in lg.columns else None)
    if value_col is None:
        st.error("The lineup data came back without a net rating or plus-minus column.")
        return
    pool = lg[lg["MIN"].fillna(0) >= float(min_minutes)] if "MIN" in lg.columns else lg
    pool = pool[pool[value_col].notna()].copy()
    # league rank of every qualifying lineup (the pop-up's "#7 best trio in the league") -- counted before the
    # stat criteria, so it is a rank in the whole league
    pool["_LG_RANK"] = pool[value_col].rank(ascending=False, method="min").astype(int)
    pool_size = len(pool)

    stats_here = [(f, lbl, low) for f, lbl, low in _LINEUP_STATS if f in pool.columns]
    labels = [lbl for _, lbl, _ in stats_here]
    chosen = st.multiselect("Add criteria:", labels, key="crit_lu_criteria")
    by_label = {lbl: (f, low) for f, lbl, low in stats_here}
    filtered = range_filters(pool, [(by_label[c][0], c) for c in chosen], f"crit_lu_{size}")
    rank_label = st.selectbox("Rank by:", labels, index=labels.index("Net Rating") if "Net Rating" in labels else 0,
                              key="crit_lu_rank")
    rank_field, low_better = by_label[rank_label]
    filtered = filtered.sort_values(rank_field, ascending=low_better, na_position="last")

    n = len(filtered)
    _count_line(f"{n} lineups match these criteria.")
    if n == 0:
        st.warning("No lineup matches -- lower the minutes or loosen a criterion.")
        return
    names_by_id = ctx["player_name_by_id"]
    rows = []
    seen = set()
    for _, r in filtered.iterrows():
        ids = [int(x) for x in str(r.get("GROUP_ID", "")).strip("-").split("-") if x.strip().isdigit()]
        if not ids:
            continue
        full = [names_by_id.get(i) or f"Player {i}" for i in ids]
        team = _TEAM_ABBR.get(int(r["TEAM_ID"])) if "TEAM_ID" in r and pd.notna(r["TEAM_ID"]) else ""
        label = " · ".join(nm.split()[-1] for nm in full) + (f" ({team})" if team else "")
        base, k = label, 2
        while label in seen:
            label, k = f"{base} #{k}", k + 1
        seen.add(label)
        rows.append({"label": label, "ids": ids, "names": full, "team": team, "row": r})
    # every matching lineup is listed (the table scrolls); up to 30 of them can be drawn at once
    table = pd.DataFrame({
        "#": list(range(1, len(rows) + 1)),
        "Lineup": [", ".join(x["names"]) for x in rows],
        "Team": [x["team"] for x in rows],
        "Min": [int(round(float(x["row"].get("MIN", 0) or 0))) for x in rows],
        rank_label: [x["row"].get(rank_field) for x in rows],
        "Net Rating" if value_col == "NET_RATING" else "Plus-Minus": [x["row"].get(value_col) for x in rows],
        "League rank": [f"#{int(x['row']['_LG_RANK'])} of {pool_size}" for x in rows],
    })
    table = table.loc[:, ~table.columns.duplicated()]
    _html_table(table, max_height=420)
    _note(f"All {len(rows)} matching lineups, ranked by {rank_label}. Up to {MAX_LINEUPS_DRAWN} of them can be drawn "
          f"in the visualization at once.")
    run = ctx["persistent_run_button"](True, key="crit_lineups")
    labels_out = [x["label"] for x in rows][:PICKER_LIST_MAX]     # (a checklist of thousands of duos would crawl)
    picked = pickers.picture_picker(labels_out, key=f"crit_lu_pick_{season}_{size}", noun="lineups",
                                    label="Lineups to draw:", default=labels_out[:9], none_text="None",
                                    max_pick=MAX_LINEUPS_DRAWN, total=len(rows))
    if not run:
        return
    if not picked:
        st.info("Pick at least one lineup to draw.")
        return
    chosen_rows = [x for x in rows if x["label"] in picked][:MAX_LINEUPS_DRAWN]
    images = {}
    for x in chosen_rows:
        for pid, nm in zip(x["ids"], x["names"]):
            images[nm] = get_player_headshot_url(pid)
    net_label = value_col.replace("_", " ").title()
    rank_of = {tuple(x["names"]): (int(x["row"]["_LG_RANK"]), pool_size) for x in chosen_rows}
    if size == 2:
        pair_labels = [tuple(x["names"]) for x in chosen_rows]
        pair_values = [float(x["row"][value_col]) for x in chosen_rows]
        pair_minutes = [float(x["row"]["MIN"]) if "MIN" in x["row"] and pd.notna(x["row"]["MIN"]) else None
                        for x in chosen_rows]
        if len(pair_labels) < 2:
            st.warning("Pick at least two duos -- a network needs more than one connection.")
            return
        with ctx["code_loading_animation"]("Drawing the Lineup Network", code=visuals.build_network_diagram):
            fig, pos, edges, minutes = visuals.build_network_diagram(
                pair_labels, pair_values, player_image_urls=images, value_label=net_label, return_hotspot_data=True,
                pair_minutes=pair_minutes if any(m is not None for m in pair_minutes) else None)
            hs = ctx["hover"](hover.lineup_network_2man_hotspots, fig.axes[0], pos, edges, net_label,
                              minute_edges=minutes, league_ranks={frozenset(k): v for k, v in rank_of.items()})
    else:
        with ctx["code_loading_animation"]("Drawing the Lineup Network", code=visuals.build_lineup_shapes_diagram):
            two = ctx["league_lineups"](season, 2)
            two_man_lookup = {}
            if two is not None and not two.empty and value_col in two.columns and "GROUP_ID" in two.columns:
                wanted = {frozenset((a, b)) for x in chosen_rows for i, a in enumerate(x["ids"]) for b in x["ids"][i + 1:]}
                for gid, v in zip(two["GROUP_ID"], pd.to_numeric(two[value_col], errors="coerce")):
                    ids = frozenset(int(t) for t in str(gid).strip("-").split("-") if t.strip().isdigit())
                    if ids in wanted and pd.notna(v):
                        a, b = tuple(ids)
                        two_man_lookup[frozenset((names_by_id.get(a, f"Player {a}"),
                                                  names_by_id.get(b, f"Player {b}")))] = float(v)
            groups = [(tuple(x["names"]), float(x["row"][value_col]),
                       float(x["row"]["MIN"]) if "MIN" in x["row"] and pd.notna(x["row"]["MIN"]) else None)
                      for x in chosen_rows]
            fig, panels = visuals.build_lineup_shapes_diagram(groups, two_man_lookup, player_image_urls=images,
                                                              value_label=net_label, return_hotspot_data=True)
            hs = ctx["hover"](hover.lineup_network_group_hotspots, panels, two_man_lookup, net_label,
                              league_ranks=rank_of)
    ctx["show_chart"](fig, hs, f"crit_lineups_{size}")
    title = f"Lineup Network -- {size}-man lineups, {season}"
    ctx["add_to_tableau_dashboard"](fig, title, "tableau_crit_lineups")
    ctx["offer_share_to_community"](fig, title, "share_crit_lineups")
    plt.close(fig)


# ================================================================ Shots by area (Shot Chart)

def render_shots_by_area(ctx, season):
    _note("Circle an area of the court (drag to draw), you can circle more than one, or pick quick areas:", strong=True)
    saved = st.session_state.get("_crit_area_value")
    value = _court_draw(key="crit_area_draw", initial=saved, default=None)
    if value:
        st.session_state["_crit_area_value"] = value
    value = value or saved or {}
    areas = [a for a in (value.get("areas") or []) if a and len(a) >= 3]
    area_names = value.get("names") or []

    c1, c2, c3 = st.columns(3)
    min_att = c1.number_input("Minimum attempts there:", min_value=0, max_value=3000, value=25, step=5,
                              key="crit_area_min_att")
    min_made = c2.number_input("Minimum makes there:", min_value=0, max_value=3000, value=0, step=5,
                               key="crit_area_min_made")
    min_pct = c3.number_input("Minimum FG% there:", min_value=0.0, max_value=100.0, value=0.0, step=1.0,
                              key="crit_area_min_pct", format="%.0f")
    sort_by = st.selectbox("Rank players by:", ["FG% there", "Attempts there", "Makes there",
                                                "Share of his shots from there"], key="crit_area_sort")
    color_input = ctx["color_input_with_dropdown"](f"crit_area_color_{season}")
    if not areas:
        st.info("Circle an area on the court (or pick a quick area) to search it.")
        return
    with ctx["code_loading_animation"]("Downloading every shot in the league this season", code=nba_data.get_league_shots):
        try:
            shots = nba_data.get_league_shots(season)
        except Exception as e:  # noqa: BLE001
            st.error(f"Couldn't load the league's shots for {season}: {ctx['friendly_error'](e)}")
            return
    need = {"PLAYER_ID", "PLAYER_NAME", "LOC_X", "LOC_Y", "SHOT_MADE_FLAG"}
    if shots is None or shots.empty or not need.issubset(shots.columns):
        st.error(f"No league shot data for {season}.")
        return
    inside_mask = visuals.points_in_areas(shots["LOC_X"], shots["LOC_Y"], areas)
    inside = shots[inside_mask]
    lg_fga, lg_fgm = len(inside), int(inside["SHOT_MADE_FLAG"].sum())
    where = " + ".join(area_names) if area_names else "the circled area"
    _note(f"League-wide in {where}: {lg_fgm:,}/{lg_fga:,}"
          + (f" ({100 * lg_fgm / lg_fga:.1f}% FG)" if lg_fga else "") + f" in {season}.", strong=True)
    if inside.empty:
        st.warning("Nobody took a shot from there -- circle a bigger area.")
        return
    g = inside.groupby("PLAYER_ID").agg(PLAYER_NAME=("PLAYER_NAME", "first"), FGA=("SHOT_MADE_FLAG", "size"),
                                        FGM=("SHOT_MADE_FLAG", "sum"))
    if "TEAM_ID" in inside.columns:
        g["TEAM"] = inside.groupby("PLAYER_ID")["TEAM_ID"].agg(lambda s: _TEAM_ABBR.get(int(s.iloc[-1]), ""))
    else:
        g["TEAM"] = ""
    totals = shots.groupby("PLAYER_ID").size()
    g["FG_PCT"] = g["FGM"] / g["FGA"]
    g["SHARE"] = g["FGA"] / totals.reindex(g.index)
    ok = (g["FGA"] >= min_att) & (g["FGM"] >= min_made) & (g["FG_PCT"] * 100 >= min_pct)
    res = g[ok].copy()
    order = {"FG% there": "FG_PCT", "Attempts there": "FGA", "Makes there": "FGM",
             "Share of his shots from there": "SHARE"}[sort_by]
    res = res.sort_values([order, "FGA"], ascending=False)
    n = len(res)
    _count_line(f"{n} players match these criteria.")
    if n == 0:
        st.warning("No player matches -- lower a minimum or circle a bigger area.")
        return
    shown = res
    _html_table(pd.DataFrame({
        "Player": shown["PLAYER_NAME"].values, "Team": shown["TEAM"].values,
        "Makes": shown["FGM"].astype(int).values, "Attempts": shown["FGA"].astype(int).values,
        "FG%": (shown["FG_PCT"] * 100).round(1).values, "Share of his shots": (shown["SHARE"] * 100).round(1).values,
    }))
    names = [str(x) for x in shown["PLAYER_NAME"].tolist()][:PICKER_LIST_MAX]
    run = ctx["persistent_run_button"](True, key="crit_area")
    picked = pickers.picture_picker(names, key=f"crit_area_pick_{season}", noun="players", label="Players to show:",
                                    default=names[:6], none_text="None", max_pick=30, total=n)
    if not run:
        return
    chosen = [pid for pid, nm in zip(shown.index, names) if nm in picked]
    if not chosen:
        st.info("Pick at least one player to see his zoomed-in shot chart.")
        return
    chosen = chosen[:30]
    color = ctx["resolve_color_input"](color_input) if color_input else "#D4AF37"
    st.markdown(_CARD_CSS, unsafe_allow_html=True)
    with ctx["code_loading_animation"](f"Drawing {len(chosen)} zoomed-in shot chart{'s' if len(chosen) != 1 else ''}",
                                       code=visuals.build_area_zoom_chart):
        figs = {pid: visuals.build_area_zoom_chart(shots[shots["PLAYER_ID"] == pid], areas, color) for pid in chosen}
    for i in range(0, len(chosen), 2):
        cols = st.columns(2)
        for col, pid in zip(cols, chosen[i:i + 2]):
            r = res.loc[pid]
            with col:
                st.markdown(
                    f'<div class="crit-area-card"><img src="{get_player_headshot_url(int(pid))}" alt="">'
                    f'<div><div class="crit-area-name">{html.escape(str(r["PLAYER_NAME"]))}</div>'
                    f'<div class="crit-area-line">{int(r["FGM"])}/{int(r["FGA"])} · {100 * r["FG_PCT"]:.1f}% FG · '
                    f'{100 * r["SHARE"]:.0f}% of his shots'
                    f'{(" · " + html.escape(str(r["TEAM"]))) if r["TEAM"] else ""}</div></div></div>',
                    unsafe_allow_html=True)
                st.pyplot(figs[pid])
                plt.close(figs[pid])


_CARD_CSS = """
<style>
.crit-area-card { display:flex; align-items:center; gap:10px; margin:14px 0 2px; }
.crit-area-card img { width:58px; height:44px; object-fit:cover; object-position:top; border-radius:8px;
  background:#1a1a1a; border:1px solid #2a2a2a; }
.crit-area-name { font-weight:700; color:#f0f0f0; font-size:1.02rem; line-height:1.2; }
.crit-area-line { color:#a8a8a8; font-size:0.85rem; }
</style>
"""


# ================================================================ Passing (Passing Web)

_AREA_TYPES = [("Any shot", None), ("At the rim", "AtRim"), ("Short mid-range (4-14 ft)", "ShortMidRange"),
               ("Long mid-range (14 ft to the 3-point line)", "LongMidRange"), ("Corner 3", "Corner3"),
               ("Above-the-break 3", "Arc3")]
_ZONE_BASIC_FOR = {"AtRim": ("Restricted Area",), "ShortMidRange": ("In The Paint (Non-RA)",),
                   "LongMidRange": ("Mid-Range",), "Corner3": ("Left Corner 3", "Right Corner 3"),
                   "Arc3": ("Above the Break 3",)}


def _shot_type_mask(shots, col):
    """Which of the league's shots are of pbpstats' shot type `col` -- 2-pointers by distance (at the rim under 4 ft,
    short mid-range 4-13 ft, long mid-range 14 ft+, as pbpstats counts them), 3-pointers by corner / above the break."""
    basic = shots["SHOT_ZONE_BASIC"].astype(str) if "SHOT_ZONE_BASIC" in shots.columns else pd.Series("", index=shots.index)
    if col in ("Corner3", "Arc3"):
        return basic.isin(_ZONE_BASIC_FOR[col])
    if "SHOT_DISTANCE" not in shots.columns:
        return basic.isin(_ZONE_BASIC_FOR[col])
    dist = pd.to_numeric(shots["SHOT_DISTANCE"], errors="coerce")
    two = ~basic.str.contains("3") if "SHOT_TYPE" not in shots.columns else shots["SHOT_TYPE"].astype(str).str.contains("2PT")
    if col == "AtRim":
        return two & (dist < 4)
    if col == "ShortMidRange":
        return two & (dist >= 4) & (dist < 14)
    return two & (dist >= 14)


def render_passing(ctx, season):
    role = st.radio("Search for:", ["Passers (who set up the shots)", "Receivers (who scored off passes)"],
                    horizontal=True, key="crit_pass_role")
    passers = role.startswith("Passers")
    area_label = st.selectbox("Shot location:", [a for a, _ in _AREA_TYPES], key="crit_pass_area")
    col = dict(_AREA_TYPES)[area_label]
    c1, c2, c3 = st.columns(3)
    min_ast = c1.number_input("Minimum assisted baskets there:", min_value=0, max_value=2000,
                              value=60 if passers else 30, step=5, key=f"crit_pass_min_{int(passers)}")
    min_share = c2.number_input("Minimum share of his assisted baskets from there (%):", min_value=0.0,
                                max_value=100.0, value=0.0, step=5.0, key="crit_pass_share", format="%.0f")
    if passers:
        min_total = c3.number_input("Minimum assists overall (any shot):", min_value=0, max_value=2000, value=0,
                                    step=10, key="crit_pass_total")
        min_fg = 0.0
    else:
        min_fg = c3.number_input("Minimum FG% there (his own shooting):", min_value=0.0, max_value=100.0, value=0.0,
                                 step=1.0, key="crit_pass_fg", format="%.0f")
        min_total = 0
    team_pick = st.multiselect("Teams (optional -- leave empty for the whole league):", ctx["ALL_TEAM_NAMES"],
                               key="crit_pass_teams")
    # ONE league-wide request (pbpstats.com's season totals: every player's assists and assisted baskets by kind of
    # shot) -- asking for all 30 teams' assist networks at once gets refused by pbpstats.com
    with ctx["code_loading_animation"]("Downloading the league's assists by shot type (pbpstats.com)",
                                       code=nba_data.get_league_passing_totals):
        try:
            tot = nba_data.get_league_passing_totals(season)
        except Exception as e:  # noqa: BLE001
            st.error(f"Couldn't load the league's assist data for {season}: {ctx['friendly_error'](e)} "
                     f"Try again in a minute.")
            return
    if tot is None or tot.empty:
        st.error(f"No assist data for {season}.")
        return
    if team_pick:
        tot = tot[tot["TEAM_ID"].isin(_team_ids(team_pick))]
    types = [col] if col else list(nba_data.PBPSTATS_SHOT_TYPES)
    res = tot.set_index("PLAYER_ID")
    if passers:
        v = res[[f"{t}_AST" for t in types]].sum(axis=1)
        whole = res["AST"]
    else:
        v = res[[f"{t}_ASTD" for t in types]].sum(axis=1)
        whole = res[[f"{t}_ASTD" for t in nba_data.PBPSTATS_SHOT_TYPES]].sum(axis=1)
        fgm = res[[f"{t}_FGM" for t in types]].sum(axis=1)
        fga = res[[f"{t}_FGA" for t in types]].sum(axis=1)
        res = res.assign(FG_PCT=np.where(fga > 0, fgm / fga.replace(0, np.nan), np.nan))
    res = res.assign(V=v, WHOLE=whole, SHARE=np.where(whole > 0, v / whole.replace(0, np.nan), 0.0))
    ok = (res["V"] >= min_ast) & (res["SHARE"].fillna(0) * 100 >= min_share) & (res["AST"] >= min_total)
    if min_fg > 0:
        ok &= res["FG_PCT"].fillna(0) * 100 >= min_fg
    res = res[ok].sort_values("V", ascending=False)
    n = len(res)
    what = "set up" if passers else "scored"
    _count_line(f"{n} players match these criteria.")
    if n == 0:
        st.warning("No player matches -- lower a minimum or pick another shot location.")
        return
    table = {"Player": res["NAME"].values, "Team": res["TEAM"].values,
             f"Assisted baskets {what} there": res["V"].astype(int).values,
             "Share of his assisted baskets": (res["SHARE"] * 100).round(0).values}
    if passers:
        table["Assists overall"] = res["AST"].astype(int).values
    else:
        table["His FG% there"] = (res["FG_PCT"] * 100).round(1).values
    _html_table(pd.DataFrame(table))
    names = [str(x) for x in res["NAME"].tolist()][:PICKER_LIST_MAX]
    run = ctx["persistent_run_button"](True, key="crit_passing")
    picked = pickers.picture_picker(names, key=f"crit_pass_pick_{season}_{int(passers)}", noun="players",
                                    label="Passing webs to draw:", default=names[:2], none_text="None")
    if not run:
        return
    chosen = [pid for pid, nm in zip(res.index, names) if nm in picked]
    if not chosen:
        st.info("Pick at least one player to draw his passing web.")
        return
    if len(chosen) > 4:
        _note("Drawing the first 4 picked (each passing web takes a few seconds to build).")
        chosen = chosen[:4]
    drawn = set()
    for pid in chosen:
        name = ctx["strip_accents"](str(res.loc[pid, "NAME"]))
        if passers:
            passer_id, passer_name = int(pid), name
            st.subheader(f"{passer_name}")
        else:
            # who set him up most on that kind of shot: his own team's assist network (one request)
            try:
                net = nba_data.get_team_assist_network(int(res.loc[pid, "TEAM_ID"]), season)
            except Exception as e:  # noqa: BLE001
                st.subheader(f"{name}")
                _note(f"His team's assist network couldn't be loaded just now ({ctx['friendly_error'](e)}).")
                continue
            mine = net[net["RECEIVER_ID"] == int(pid)] if net is not None and not net.empty else pd.DataFrame()
            if mine.empty:
                continue
            mine = mine.assign(_V=mine[col] if col else mine["AST"]).sort_values("_V", ascending=False)
            top = mine.iloc[0]
            passer_id, passer_name = int(top["PASSER_ID"]), ctx["strip_accents"](str(top["PASSER"]))
            spot = area_label.lower() if col else "all his baskets"
            st.subheader(f"{name}")
            _note(f"{passer_name} assisted {name} most on {spot}: {int(top['_V'])} baskets. Here's "
                  f"{passer_name}'s passing web.")
            if passer_id in drawn:
                _note(f"({passer_name}'s passing web is already drawn above.)")
                continue
        drawn.add(passer_id)
        ctx["render_passing_web"](passer_name, passer_id, season, top_n=5, rank_ascending=False,
                                  color_input=None, key=f"crit_pw_{passer_id}", show_explainer=False)
