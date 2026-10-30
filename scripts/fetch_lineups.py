"""Saves five-man lineups (75+ minutes together) for Guess the Analytics: net, offensive and defensive rating, +/-,
eFG%, TS%, pace, assist %, rebound % and turnover %, with the five players' NBA ids (for their pictures), from the
NBA's stats site. Early in a season (fewer than 80 such lineups yet) the last full season is kept. Run daily by .github/workflows/lineups.yml; standard library only.
stats.nba.com sometimes turns cloud servers away: then the file is left as it was and the game just skips its
lineup rounds.

    python3 scripts/fetch_lineups.py docs/data/lineups.json
"""
import datetime as dt
import json
import sys
import urllib.request

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36",
           "Referer": "https://www.nba.com/", "Origin": "https://www.nba.com", "Accept": "application/json, text/plain, */*",
           "x-nba-stats-origin": "stats", "x-nba-stats-token": "true"}
URL = ("https://stats.nba.com/stats/leaguedashlineups?Conference=&DateFrom=&DateTo=&Division=&GameSegment=&GroupQuantity=5"
       "&LastNGames=0&LeagueID=00&Location=&MeasureType={m}&Month=0&OpponentTeamID=0&Outcome=&PORound=0&PaceAdjust=N"
       "&PerMode=Totals&Period=0&PlusMinus=N&Rank=N&Season={s}&SeasonSegment=&SeasonType=Regular+Season&ShotClockRange="
       "&TeamID=0&VsConference=&VsDivision=")
TRI = {"GSW": "GS", "NYK": "NY", "SAS": "SA", "NOP": "NO", "UTA": "UTAH", "WAS": "WSH"}       # (the site uses ESPN's)


def rows(measure, season):
    req = urllib.request.Request(URL.format(m=measure, s=season), headers=HEADERS)
    d = json.loads(urllib.request.urlopen(req, timeout=60).read())
    rs = d["resultSets"][0]
    return [dict(zip(rs["headers"], r)) for r in rs["rowSet"]]


def season_name(y):
    return f"{y}-{str(y + 1)[2:]}"


def build(season):
    adv = {r["GROUP_ID"]: r for r in rows("Advanced", season)}
    base = {r["GROUP_ID"]: r for r in rows("Base", season)}
    out = []
    for gid, a in adv.items():
        b = base.get(gid, {})
        if (a.get("MIN") or 0) < 75 or None in (a.get("OFF_RATING"), a.get("DEF_RATING"), a.get("NET_RATING")):
            continue
        pct = lambda k: round((a.get(k) or 0) * 1000) / 10
        out.append({"team": TRI.get(a.get("TEAM_ABBREVIATION"), a.get("TEAM_ABBREVIATION")),
                    "ids": [int(x) for x in gid.split("-") if x], "names": [n.strip() for n in (a.get("GROUP_NAME") or "").split(" - ")],
                    "min": round(a.get("MIN") or 0), "off": a["OFF_RATING"], "def": a["DEF_RATING"], "net": a["NET_RATING"],
                    "pm": b.get("PLUS_MINUS"), "efg": pct("EFG_PCT"), "ts": pct("TS_PCT"), "pace": a.get("PACE"),
                    "ast": pct("AST_PCT"), "reb": pct("REB_PCT"), "tov": pct("TM_TOV_PCT")})
    return sorted(out, key=lambda r: -r["min"])


def main(path):
    now = dt.date.today()
    y = now.year if now.month >= 10 else now.year - 1
    try:
        season, out = season_name(y), build(season_name(y))
        if len(out) < 80:
            season, out = season_name(y - 1), build(season_name(y - 1))
    except Exception as e:
        print("The NBA's stats site couldn't be reached:", e)
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"season": season, "updated": now.isoformat(), "lineups": out}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(out)} lineups saved ({season}).")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "docs/data/lineups.json")
