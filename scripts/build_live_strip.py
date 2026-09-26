"""
build_live_strip.py

Builds the data behind the website's auto-scrolling "live strip" (the animated cards right above the dashboard on
docs/index.html) as files. OPTIONAL BACKUP ONLY: the strip normally reads ESPN's public feed straight from the
visitor's browser (assets/live-strip.js) and needs nothing from this script; data/live/ is only used if ESPN can't be
reached. Everything here comes from the NBA's public live-data CDN (cdn.nba.com), which answers from servers but not
from web pages.

What it shows:
  * During the season: games being played right now plus the most recent game day's finished games.
  * From the end of the NBA Finals until the next regular season tips off: every game of that year's Finals.
    (Preseason games never count -- the Finals stay up until opening night.)

Output (inside docs/, so GitHub Pages serves it next to the page):
  docs/data/live/index.json          -- which games there are, which one to show first, the strip's label
  docs/data/live/games/<gameId>.json -- one game: teams, quarter scores, team stats, every player's line, every shot
                                        with its court position and time, the score after every basket, and who
                                        assisted whom

If the NBA can't be reached, nothing is overwritten -- the page keeps showing the last good data.

Run locally:  python scripts/build_live_strip.py            (writes into docs/data/live)
Testing:      python scripts/build_live_strip.py --source DIR  reads saved CDN files from DIR instead of the web
              (DIR/scheduleLeagueV2.json, DIR/boxscore_<id>.json, DIR/playbyplay_<id>.json,
               DIR/todaysScoreboard_00.json)
"""

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "docs", "data", "live")
CDN = "https://cdn.nba.com/static/json"
URLS = {
    "schedule": CDN + "/staticData/scheduleLeagueV2.json",
    "scoreboard": CDN + "/liveData/scoreboard/todaysScoreboard_00.json",
    "boxscore": CDN + "/liveData/boxscore/boxscore_{gid}.json",
    "playbyplay": CDN + "/liveData/playbyplay/playbyplay_{gid}.json",
}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
    "Accept": "application/json, text/plain, */*",
}
# game-id prefixes that count as "real" games: regular season, playoffs, play-in, NBA Cup final (never preseason)
REAL_GAME_PREFIXES = ("002", "004", "005", "006")
MAX_RECENT_GAMES = 15

# Team colours chosen to read on the page's near-black background (a team's darkest official colour often doesn't)
TEAM_COLORS = {
    "ATL": "#E03A3E", "BOS": "#18A659", "BKN": "#C9C9C9", "CHA": "#00A3B4", "CHI": "#E0314B", "CLE": "#FDBB30",
    "DAL": "#1E7FD6", "DEN": "#FEC524", "DET": "#E0314B", "GSW": "#FFC72C", "HOU": "#E0314B", "IND": "#FDBB30",
    "LAC": "#3B82F6", "LAL": "#FDB927", "MEM": "#7D95C9", "MIA": "#F25C54", "MIL": "#EEE1C6", "MIN": "#78BE20",
    "NOP": "#C9A95E", "NYK": "#F58426", "OKC": "#2E9BE6", "ORL": "#2F8FE0", "PHI": "#3B82F6", "PHX": "#F07A2E",
    "POR": "#E03A3E", "SAC": "#A57FDB", "SAS": "#C4CED4", "TOR": "#E0314B", "UTA": "#F9C21B", "WAS": "#E31837",
}


# ---------------------------------------------------------------- fetching

class Source:
    def __init__(self, folder=None):
        self.folder = folder

    def get(self, kind, gid=None):
        if self.folder:
            name = {"schedule": "scheduleLeagueV2.json", "scoreboard": "todaysScoreboard_00.json",
                    "boxscore": f"boxscore_{gid}.json", "playbyplay": f"playbyplay_{gid}.json"}[kind]
            path = os.path.join(self.folder, name)
            if not os.path.exists(path):
                return None
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        url = URLS[kind].format(gid=gid)
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=25) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code in (403, 404):        # a game that doesn't exist (yet)
                    return None
                time.sleep(2 * (attempt + 1))
            except (urllib.error.URLError, TimeoutError, ValueError, OSError):
                time.sleep(2 * (attempt + 1))
        return None


# ---------------------------------------------------------------- helpers

def _clock_seconds(clock):
    """'PT10M53.00S' -> 653.0 seconds left in the period."""
    m = re.match(r"PT(\d+)M([\d.]+)S", str(clock or ""))
    return int(m.group(1)) * 60 + float(m.group(2)) if m else None


def _elapsed(period, clock):
    """Seconds since tip-off at this moment of the game (quarters are 12:00, overtimes 5:00)."""
    left = _clock_seconds(clock)
    period = int(period or 1)
    length = 720 if period <= 4 else 300
    before = 720 * min(period - 1, 4) + 300 * max(0, period - 5)
    return round(before + (length - (left if left is not None else length)), 1)


def _minutes(iso):
    """'PT36M12.00S' -> '36:12'."""
    s = _clock_seconds(iso)
    if s is None:
        return "0:00"
    return f"{int(s // 60)}:{int(round(s % 60)):02d}"


def _num(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return default


def _pct(v):
    try:
        return round(float(v) * 100, 1)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- one game

def build_game(src, gid, label=None, series=None):
    box = src.get("boxscore", gid)
    game = (box or {}).get("game")
    if not game:
        return None
    pbp = src.get("playbyplay", gid)
    actions = ((pbp or {}).get("game") or {}).get("actions") or []

    def team(t):
        tri = t.get("teamTricode", "")
        s = t.get("statistics") or {}
        return {
            "id": _num(t.get("teamId")), "tri": tri, "name": t.get("teamName", ""), "city": t.get("teamCity", ""),
            "color": TEAM_COLORS.get(tri, "#D4AF37"), "score": _num(t.get("score")),
            "periods": [_num(p.get("score")) for p in t.get("periods") or []],
            "stats": {
                "fg": f"{_num(s.get('fieldGoalsMade'))}-{_num(s.get('fieldGoalsAttempted'))}",
                "fgPct": _pct(s.get("fieldGoalsPercentage")),
                "tp": f"{_num(s.get('threePointersMade'))}-{_num(s.get('threePointersAttempted'))}",
                "tpPct": _pct(s.get("threePointersPercentage")),
                "ft": f"{_num(s.get('freeThrowsMade'))}-{_num(s.get('freeThrowsAttempted'))}",
                "reb": _num(s.get("reboundsTotal")), "ast": _num(s.get("assists")), "tov": _num(s.get("turnovers")),
                "stl": _num(s.get("steals")), "blk": _num(s.get("blocks")),
                "paint": _num(s.get("pointsInThePaint")), "fastBreak": _num(s.get("pointsFastBreak")),
                "secondChance": _num(s.get("pointsSecondChance")), "benchPts": _num(s.get("benchPoints")),
                "biggestLead": _num(s.get("biggestLead")),
            },
        }

    home, away = team(game.get("homeTeam") or {}), team(game.get("awayTeam") or {})
    players = []
    for side, t in (("home", game.get("homeTeam") or {}), ("away", game.get("awayTeam") or {})):
        for p in t.get("players") or []:
            s = p.get("statistics") or {}
            if str(p.get("played", "1")) == "0" and not _num(s.get("points")):
                continue
            players.append({
                "id": _num(p.get("personId")), "name": p.get("name") or f"{p.get('firstName', '')} {p.get('familyName', '')}".strip(),
                "short": p.get("nameI") or p.get("name", ""), "team": side, "starter": str(p.get("starter")) == "1",
                "pos": p.get("position") or "", "min": _minutes(s.get("minutes")),
                "pts": _num(s.get("points")), "reb": _num(s.get("reboundsTotal")), "ast": _num(s.get("assists")),
                "stl": _num(s.get("steals")), "blk": _num(s.get("blocks")), "tov": _num(s.get("turnovers")),
                "fgm": _num(s.get("fieldGoalsMade")), "fga": _num(s.get("fieldGoalsAttempted")),
                "tpm": _num(s.get("threePointersMade")), "tpa": _num(s.get("threePointersAttempted")),
                "ftm": _num(s.get("freeThrowsMade")), "fta": _num(s.get("freeThrowsAttempted")),
                "pm": _num(s.get("plusMinusPoints")),
            })
    home_id = home["id"]

    shots, flow, assists, scoring = [], [[0, 0, 0]], [], []
    last = (0, 0)
    for a in actions:
        t = _elapsed(a.get("period"), a.get("clock"))
        side = 0 if _num(a.get("teamId")) == home_id else 1
        if a.get("isFieldGoal") and a.get("xLegacy") is not None and a.get("yLegacy") is not None:
            made = 1 if str(a.get("shotResult", "")).lower() == "made" else 0
            value = 3 if str(a.get("actionType", "")).lower().startswith("3") else 2
            pid = _num(a.get("personId"))
            shots.append([t, pid, side, _num(a.get("xLegacy")), _num(a.get("yLegacy")), made, value,
                          _num(a.get("period"))])
            if made and a.get("assistPersonId"):
                assists.append([_num(a.get("assistPersonId")), pid, side, _num(a.get("xLegacy")),
                                _num(a.get("yLegacy")), value])
        hs, as_ = a.get("scoreHome"), a.get("scoreAway")
        if hs not in (None, "") and as_ not in (None, ""):
            cur = (_num(hs), _num(as_))
            if cur != last:
                flow.append([t, cur[0], cur[1]])
                pts = (cur[0] - last[0]) if cur[0] != last[0] else (cur[1] - last[1])
                if a.get("personId") and pts > 0:
                    scoring.append([t, _num(a.get("personId")), pts])
                last = cur

    status = game.get("gameStatus")
    lead_changes, leader = 0, 0
    for _, h, a_ in flow:
        now = (h > a_) - (h < a_)
        if now and leader and now != leader:
            lead_changes += 1
        leader = now or leader
    return {
        "id": gid, "label": label or "", "series": series or "",
        "date": (game.get("gameTimeUTC") or game.get("gameEt") or "")[:10],
        "status": game.get("gameStatusText", ""), "live": status == 2, "final": status == 3,
        "period": _num(game.get("period")), "clock": _minutes(game.get("gameClock")) if status == 2 else "",
        "home": home, "away": away, "players": players, "shots": shots, "flow": flow, "assists": assists,
        "scoring": scoring,
        "leadChanges": _num((game.get("homeTeam") or {}).get("statistics", {}).get("leadChanges"), lead_changes),
        "timesTied": _num((game.get("homeTeam") or {}).get("statistics", {}).get("timesTied"), 0),
    }


def _summary(g):
    return {"id": g["id"], "label": g["label"], "date": g["date"], "status": g["status"], "live": g["live"],
            "final": g["final"], "series": g["series"],
            "home": {k: g["home"][k] for k in ("tri", "name", "score", "color")},
            "away": {k: g["away"][k] for k in ("tri", "name", "score", "color")}}


# ---------------------------------------------------------------- which games

def _schedule_games(schedule):
    out = []
    for day in ((schedule or {}).get("leagueSchedule") or {}).get("gameDates") or []:
        for g in day.get("games") or []:
            gid = str(g.get("gameId", ""))
            if gid[:3] in REAL_GAME_PREFIXES:
                out.append(g)
    return out


def _finals_ids(season_start_year):
    yy = season_start_year % 100
    return [f"004{yy:02d}0040{n}" for n in range(1, 8)]


def pick_games(src, schedule, today, board=None):
    """-> (mode, label, [(gameId, label, seriesText)])"""
    games = _schedule_games(schedule)
    # the schedule file can lag behind tonight's games: today's scoreboard has their up-to-the-minute status
    now = {str(g.get("gameId")): g for g in ((board or {}).get("scoreboard") or {}).get("games") or []}
    for g in games:
        b = now.get(str(g.get("gameId")))
        if b and b.get("gameStatus") in (1, 2, 3):
            g["gameStatus"] = b["gameStatus"]
    season_year = str(((schedule or {}).get("leagueSchedule") or {}).get("seasonYear") or "")
    started = [g for g in games if g.get("gameStatus") in (2, 3)]
    if started:
        def when(g):
            return str(g.get("gameDateTimeUTC") or g.get("gameDateUTC") or "")
        started.sort(key=when)
        latest = started[-1]
        lid = str(latest.get("gameId"))
        if lid.startswith("004") and lid[7] == "4":      # the most recent game is a Finals game -> the whole Finals
            finals = [g for g in started if str(g.get("gameId", "")).startswith(lid[:8])]
            year = int(season_year[:4]) + 1 if season_year[:4].isdigit() else today.year
            return "finals", f"{year} NBA Finals", [(str(g["gameId"]), g.get("gameSubLabel") or g.get("gameLabel") or "",
                                                     g.get("seriesText") or "") for g in finals]
        live = [g for g in started if g.get("gameStatus") == 2]
        last_day = when(latest)[:10]
        recent = [g for g in started if g.get("gameStatus") == 3 and when(g)[:10] >= _day_before(last_day)]
        pick = (live + list(reversed(recent)))[:MAX_RECENT_GAMES]
        label = "Live now" if live else "Latest games"
        return "live" if live else "recent", label, [(str(g["gameId"]), g.get("gameLabel") or "",
                                                     g.get("seriesText") or "") for g in pick]
    # The schedule is already next season's and nothing has been played yet: show the last Finals.
    start = int(season_year[:4]) if season_year[:4].isdigit() else (today.year if today.month >= 10 else today.year - 1)
    prev_start = start - 1
    picked = []
    for n, gid in enumerate(_finals_ids(prev_start), 1):
        picked.append((gid, f"Game {n}", ""))
    return "finals", f"{prev_start + 1} NBA Finals", picked


def _day_before(day):
    try:
        return (dt.date.fromisoformat(day) - dt.timedelta(days=1)).isoformat()
    except ValueError:
        return day


def _series_text(games):
    """'OKC wins 4-3' style text for a set of Finals games, from their results."""
    wins = {}
    for g in games:
        if not g["final"]:
            continue
        w = g["home"] if g["home"]["score"] > g["away"]["score"] else g["away"]
        wins[w["tri"]] = wins.get(w["tri"], 0) + 1
    if not wins:
        return ""
    teams = {g["home"]["tri"] for g in games} | {g["away"]["tri"] for g in games}
    ranked = sorted(teams, key=lambda t: -wins.get(t, 0))
    a, b = ranked[0], (ranked[1] if len(ranked) > 1 else "")
    wa, wb = wins.get(a, 0), wins.get(b, 0)
    if wa == 4:
        return f"{a} wins {wa}-{wb}"
    if wa == wb:
        return f"Series tied {wa}-{wb}"
    return f"{a} leads {wa}-{wb}"


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", help="read saved CDN files from this folder instead of the web")
    ap.add_argument("--out", default=OUT_DIR)
    ap.add_argument("--today", help="YYYY-MM-DD (testing)")
    args = ap.parse_args(argv)
    src = Source(args.source)
    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(dt.timezone.utc).date()

    schedule = src.get("schedule")
    if schedule is None:
        print("Couldn't read the NBA schedule -- keeping the current data.")
        return 0
    mode, label, wanted = pick_games(src, schedule, today, src.get("scoreboard"))
    built = []
    for gid, glabel, series in wanted:
        g = build_game(src, gid, glabel, series)
        if g is None:
            continue
        if mode == "finals" and not g["final"] and not g["live"]:
            continue
        built.append(g)
    if not built:
        print(f"No games could be built ({mode}: {len(wanted)} wanted) -- keeping the current data.")
        return 0
    if mode == "finals":
        text = _series_text(built)
        for i, g in enumerate(built):
            g["label"] = g["label"] if g["label"].lower().startswith("game") else f"Game {i + 1}"
            g["series"] = g["series"] or text
    games_dir = os.path.join(args.out, "games")
    os.makedirs(games_dir, exist_ok=True)
    keep = set()
    for g in built:
        path = os.path.join(games_dir, f"{g['id']}.json")
        keep.add(os.path.basename(path))
        _write_if_changed(path, g)
    for name in os.listdir(games_dir):
        if name.endswith(".json") and name not in keep:
            os.remove(os.path.join(games_dir, name))
    default = next((g["id"] for g in built if g["live"]), built[-1]["id"] if mode == "finals" else built[0]["id"])
    yy = int(built[0]["id"][3:5]) if built[0]["id"][3:5].isdigit() else None
    season = f"20{yy:02d}-{(yy + 1) % 100:02d}" if yy is not None else ""
    index = {"mode": mode, "label": label, "season": season,
             "default": default, "games": [_summary(g) for g in built]}
    changed = _write_if_changed(os.path.join(args.out, "index.json"), index)
    print(f"{mode}: {label} -- {len(built)} games" + (" (updated)" if changed else " (no change)"))
    return 0


def _write_if_changed(path, data):
    text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return False
    except OSError:
        pass
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return True


if __name__ == "__main__":
    sys.exit(main())
