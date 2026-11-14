"""Finds the NBA's YouTube highlight video of every recently finished game and saves it for the website.

Matches each final to its "FULL GAME HIGHLIGHTS" video on the NBA's YouTube channel by the two team names and the date.
Run by .github/workflows/highlights.yml every 10 minutes; standard library only.

- With a YouTube Data API key (the repo secret YOUTUBE_API_KEY): every final of the season so far (ESPN's scoreboard,
  one day at a time from the season's first day: ESPN no longer answers date ranges), against the channel's whole
  upload list, read back as far as the oldest game still without a video (one unit of the free 10,000-a-day quota per
  50 videos). A game with no video found 4 days after it was played is marked as checked and not looked for again,
  and a day whose games are all done is remembered ("days"), so later runs only look at the days still open.
- Without a key: the last three days' finals against the channel's public feed (only its 15 newest videos).

Where it can be watched: with the API key, each chosen video's regionRestriction is read (videos.list, 1 unit per 50
videos). The NBA's own uploads are blocked in some countries (much of Europe among them); for those, other embeddable
highlight videos of the same game that ARE watchable there are looked for (search.list, 100 units; at most a few games
a run) and saved as "alts". Each game then carries "blocked"/"allowed" (country codes) for the main video and its alts,
and the website plays the first one the viewer's country can watch (and moves on to the next if YouTube refuses it).

    python3 scripts/fetch_highlights.py docs/data/highlights.json
"""
import datetime as dt
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

NBA_CHANNEL = "UCWJ2lWNubArHWmf3FIHbfcQ"          # youtube.com/@NBA
FEED = "https://www.youtube.com/feeds/videos.xml?channel_id=" + NBA_CHANNEL
SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?limit=200&dates="
KEEP = 2600                                        # games remembered (two seasons)
API = "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&maxResults=50&playlistId=UU" + NBA_CHANNEL[2:]
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015", "media": "http://search.yahoo.com/mrss/"}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (bradley-analytics highlights)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def videos(xml_bytes):
    """[{id, title, published (datetime)}] from a YouTube channel feed."""
    root = ET.fromstring(xml_bytes)
    out = []
    for e in root.findall("a:entry", NS):
        vid = e.findtext("yt:videoId", default="", namespaces=NS)
        title = e.findtext("a:title", default="", namespaces=NS)
        pub = e.findtext("a:published", default="", namespaces=NS)
        try:
            when = dt.datetime.fromisoformat(pub.replace("Z", "+00:00"))
        except ValueError:
            continue
        if vid and title:
            out.append({"id": vid, "title": title, "published": when})
    return out


def api_videos(key, older_than):
    """The channel's uploads, newest first, back to `older_than` (datetime)."""
    out, token = [], ""
    for _ in range(400):
        d = json.loads(get(API + "&key=" + key + ("&pageToken=" + token if token else "")))
        for it in d.get("items", []):
            sn = it.get("snippet") or {}
            vid = (sn.get("resourceId") or {}).get("videoId")
            try:
                when = dt.datetime.fromisoformat(sn.get("publishedAt", "").replace("Z", "+00:00"))
            except ValueError:
                continue
            if vid:
                out.append({"id": vid, "title": sn.get("title", ""), "published": when})
        token = d.get("nextPageToken")
        if not token or (out and out[-1]["published"] < older_than):
            break
    return out


VIDEOS = "https://www.googleapis.com/youtube/v3/videos?part=contentDetails,status,snippet&maxResults=50&id="
SEARCH = "https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&videoEmbeddable=true&maxResults=15&order=relevance"
ALT_SEARCHES_PER_RUN = 3                            # 100 quota units each; 144 runs a day, but only new games search


def video_details(key, ids):
    """{id: {"blocked": [...], "allowed": [...] or None, "embeddable": bool, "title": str}} for up to any number of ids."""
    out = {}
    ids = [i for i in dict.fromkeys(ids) if i]
    for k in range(0, len(ids), 50):
        try:
            d = json.loads(get(VIDEOS + ",".join(ids[k:k + 50]) + "&key=" + key))
        except Exception as e:  # noqa: BLE001
            print("videos.list failed:", e)
            continue
        for it in d.get("items", []):
            rr = (it.get("contentDetails") or {}).get("regionRestriction") or {}
            out[it["id"]] = {"blocked": sorted(rr.get("blocked") or []), "allowed": sorted(rr["allowed"]) if "allowed" in rr else None,
                             "embeddable": bool((it.get("status") or {}).get("embeddable", True)),
                             "title": (it.get("snippet") or {}).get("title", ""),
                             "channel": (it.get("snippet") or {}).get("channelTitle", "")}
    return out


def restricted(det):
    return bool(det and (det.get("blocked") or det.get("allowed") is not None))


def find_alts(key, game, rec, exclude):
    """Other embeddable highlight videos of this game with fewer country blocks than the main one."""
    names = [sorted(n, key=len)[-1].title() for n in game["teams"]]          # e.g. "Mavericks", "Rockets"
    q = urllib.parse.quote(f"{names[0]} vs {names[1]} highlights")
    after = (game["start"] - dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    before = (game["start"] + dt.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        d = json.loads(get(SEARCH + "&q=" + q + "&publishedAfter=" + after + "&publishedBefore=" + before + "&key=" + key))
    except Exception as e:  # noqa: BLE001
        print("search failed (tried again on a later run):", e)
        return None
    cands = []
    for it in d.get("items", []):
        vid = (it.get("id") or {}).get("videoId"); sn = it.get("snippet") or {}
        if not vid or vid in exclude:
            continue
        try:
            when = dt.datetime.fromisoformat(sn.get("publishedAt", "").replace("Z", "+00:00"))
        except ValueError:
            continue
        v = {"id": vid, "title": sn.get("title", ""), "published": when}
        if score(v, game) > 0:
            cands.append(v)
    det = video_details(key, [c["id"] for c in cands])
    main_blocked = set(rec.get("blocked") or [])
    alts = []
    for c in sorted(cands, key=lambda c: -score(c, game)):
        dd = det.get(c["id"])
        if not dd or not dd["embeddable"]:
            continue
        if dd["allowed"] is not None:
            continue                                   # (only watchable in a few countries)
        if main_blocked and not (main_blocked - set(dd["blocked"])):
            continue                                   # (blocked everywhere the main one is: no help)
        alts.append({"id": c["id"], "title": c["title"], "channel": dd["channel"], "blocked": dd["blocked"]})
        if len(alts) >= 3:
            break
    return alts


def season_start(today_sb):
    lg = (today_sb.get("leagues") or [{}])[0]
    for k in ("calendarStartDate",):
        if lg.get(k):
            return dt.datetime.fromisoformat(lg[k].replace("Z", "+00:00"))
    s = (lg.get("season") or {}).get("startDate")
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def finals(scoreboard):
    """[{id, start (datetime), names: [away names], [home names]}] of the finished games."""
    out = []
    for ev in scoreboard.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        if ((comp.get("status") or ev.get("status") or {}).get("type") or {}).get("state") != "post":
            continue
        teams, tri = [], []
        for c in sorted(comp.get("competitors", []), key=lambda c: c.get("homeAway") != "away"):
            t = c.get("team") or {}
            names = {t.get("name", ""), t.get("shortDisplayName", ""), t.get("location", ""), t.get("abbreviation", "")}
            if t.get("name") == "Trail Blazers":
                names.add("Blazers")
            teams.append({n.upper() for n in names if n and len(n) > 2})
            tri.append(t.get("abbreviation", ""))
        try:
            start = dt.datetime.fromisoformat((comp.get("date") or ev.get("date")).replace("Z", "+00:00"))
        except Exception:
            continue
        if len(teams) == 2:
            out.append({"id": str(ev["id"]), "start": start, "teams": teams, "tri": tri,
                        "day": (start - dt.timedelta(hours=5)).strftime("%Y%m%d")})
    return out


TEAM_NAMES = {"ATL": "Hawks", "BOS": "Celtics", "BKN": "Nets", "CHA": "Hornets", "CHI": "Bulls", "CLE": "Cavaliers",
              "DAL": "Mavericks", "DEN": "Nuggets", "DET": "Pistons", "GS": "Warriors", "GSW": "Warriors", "HOU": "Rockets",
              "IND": "Pacers", "LAC": "Clippers", "LAL": "Lakers", "MEM": "Grizzlies", "MIA": "Heat", "MIL": "Bucks",
              "MIN": "Timberwolves", "NO": "Pelicans", "NOP": "Pelicans", "NY": "Knicks", "NYK": "Knicks", "OKC": "Thunder",
              "ORL": "Magic", "PHI": "76ers", "PHX": "Suns", "POR": "Blazers", "SAC": "Kings", "SA": "Spurs", "SAS": "Spurs",
              "TOR": "Raptors", "UTAH": "Jazz", "UTA": "Jazz", "WSH": "Wizards", "WAS": "Wizards"}


def score(video, game):
    """How well a video matches a game (0 = not at all)."""
    t = video["title"].upper()
    if "HIGHLIGHT" not in t:
        return 0
    if not all(any(re.search(r"\b" + re.escape(n) + r"\b", t) for n in names) for names in game["teams"]):
        return 0
    hours = (video["published"] - game["start"]).total_seconds() / 3600
    if hours < 1 or hours > 48:
        return 0
    s = 10
    if "FULL GAME" in t:
        s += 10
    if "|" in t:
        s += 2
    if re.search(r"\b(GAME [1-7]|FINALS|PLAYOFFS|IN-SEASON|CUP)\b", t):
        s += 1
    return s - hours / 48


def main(path):
    import os
    try:
        saved = json.load(open(path))
    except Exception:
        saved = {}
    games = saved.get("games") or {}
    checked = saved.get("checked") or {}
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=-5)))
    today = (now - dt.timedelta(hours=6)).strftime("%Y%m%d")
    todo = []
    days_done = set(saved.get("days") or [])
    day_games = {}
    if key:
        sb_today = json.loads(get(SCOREBOARD + today))
        start = season_start(sb_today) or (now - dt.timedelta(days=200))
        events, a, fetched = [], start, 0
        while a.strftime("%Y%m%d") <= today and fetched < 90:   # (one day at a time; at most 90 days a run)
            d = a.strftime("%Y%m%d")
            a += dt.timedelta(days=1)
            if d in days_done:
                continue
            try:
                evs = json.loads(get(SCOREBOARD + d)).get("events", [])
                fetched += 1
            except Exception as e:
                print("Scoreboard for", d, "couldn't be read:", e)
                continue
            evs = [e for e in evs if (e.get("season") or {}).get("type") in (2, 3, 5, None)]
            day_games[d] = [str(e["id"]) for e in evs]
            events += evs
        todo = [g for g in finals({"events": events}) if g["id"] not in games and g["id"] not in checked]
        vids = api_videos(key, min(g["start"] for g in todo) - dt.timedelta(hours=2)) if todo else []
    else:
        vids = videos(get(FEED))
        for back in range(3):
            day = (now - dt.timedelta(days=back, hours=6)).strftime("%Y%m%d")
            try:
                todo += [g for g in finals(json.loads(get(SCOREBOARD + day))) if g["id"] not in games]
            except Exception:
                continue
    found = 0
    for g in todo:
        best = max(vids, key=lambda v: score(v, g), default=None)
        if best and score(best, g) > 0:
            games[g["id"]] = {"id": best["id"], "title": best["title"], "published": best["published"].isoformat(), "teams": g["tri"], "day": g["day"]}
            found += 1
        elif key and (now - g["start"]).days >= 4:
            checked[g["id"]] = 1                     # (no highlights video for this one: not looked for again)
    # where each video can be watched; alternatives for the ones the NBA blocks in some countries
    if key:
        need = [gid for gid, v in games.items() if "blocked" not in v]
        det = video_details(key, [games[g]["id"] for g in need])
        for gid in need:
            dd = det.get(games[gid]["id"])
            if dd:
                games[gid]["blocked"] = dd["blocked"]
                if dd["allowed"] is not None:
                    games[gid]["allowed"] = dd["allowed"]
                found += 1
        by_id = {g["id"]: g for g in todo}
        searched = 0
        for gid, v in sorted(games.items(), key=lambda kv: kv[1].get("published", ""), reverse=True):
            if searched >= ALT_SEARCHES_PER_RUN:
                break
            if "alts" in v or not restricted(v):
                continue
            g = by_id.get(gid)
            if g is None:                               # (an older game: rebuild what the search needs from the record)
                try:
                    pub = dt.datetime.fromisoformat(v["published"])
                except Exception:  # noqa: BLE001
                    continue
                names = TEAM_NAMES.get(v.get("teams", ["", ""])[0]), TEAM_NAMES.get(v.get("teams", ["", ""])[-1])
                if not all(names):
                    continue
                g = {"teams": [{names[0].upper()}, {names[1].upper()}], "start": pub - dt.timedelta(hours=3)}
            alts = find_alts(key, g, v, {v["id"]})
            searched += 1
            if alts is None:
                break                                   # (out of quota for today, most likely)
            v["alts"] = alts
            found += 1
    # a day is done once every one of its games has its video (or was given up on), or it had no games, and it's over
    for d, ids in day_games.items():
        if d < today and all(i in games or i in checked for i in ids):
            days_done.add(d)
    changed = found or len(checked) != len(saved.get("checked") or {}) or len(days_done) != len(saved.get("days") or [])
    if changed:
        keep = sorted(games.items(), key=lambda kv: kv[1].get("published", ""), reverse=True)[:KEEP]
        out = {"updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "games": dict(keep), "checked": checked, "days": sorted(days_done)}
        with open(path, "w") as f:
            json.dump(out, f, indent=1, sort_keys=True)
            f.write("\n")
    # the last three days' videos, with their teams: a small file for the "highlights are up" alerts
    week = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3)).isoformat()
    recent = {k: v for k, v in games.items() if v.get("teams") and v.get("published", "") >= week}
    rpath = path.replace("highlights.json", "highlights-recent.json")
    try:
        old = json.load(open(rpath)).get("games")
    except Exception:  # noqa: BLE001
        old = None
    if old != recent:
        with open(rpath, "w") as f:
            json.dump({"games": recent}, f, separators=(",", ":"))
    print(f"{len(vids)} videos read, {len(todo)} game(s) looked for, {found} new highlight video(s).")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "docs/data/highlights.json")
