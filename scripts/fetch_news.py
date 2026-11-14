"""Saves a small copy of the NBA injury report and recent transactions for the live alerts (docs/data/news.json).

ESPN's injury report is about 1 MB (long write-ups for every player); the alerts only need each player's status, so this
keeps just that: { updated, injuries: [{id, name, team, status, note, img}], transactions: [{date, team, name, desc}] }.
Read by the website's alerts (assets/notify.js) and the alert server (worker/), both every 10 minutes. Run by
.github/workflows/highlights.yml; standard library only.

    python3 scripts/fetch_news.py docs/data/news.json
"""
import datetime as dt
import json
import sys
import urllib.request

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/"


def get(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "Mozilla/5.0 (bradley-analytics news)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def short(s, n=160):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def main(path):
    out = {"injuries": [], "transactions": []}
    try:
        for team in get("injuries").get("injuries", []):
            for x in team.get("injuries", []):
                a = x.get("athlete") or {}
                tri = ((a.get("team") or {}).get("abbreviation")) or ""
                if not a.get("displayName") or not tri:
                    continue
                pid = str(x.get("id") or a.get("displayName"))
                for link in a.get("links") or []:              # (the player's own id, steadier than the report entry's)
                    href = link.get("href", "")
                    if "/id/" in href:
                        pid = href.split("/id/")[1].split("/")[0]
                        break
                out["injuries"].append({"id": pid, "name": a["displayName"], "team": tri, "status": x.get("status") or "",
                                        "note": short(x.get("shortComment")), "img": ((a.get("headshot") or {}).get("href")) or ""})
    except Exception as e:  # noqa: BLE001
        print("Injury report couldn't be read:", e)
        return
    try:
        week = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)).isoformat()
        for t in get("transactions").get("transactions", []):
            if (t.get("date") or "") < week[:16]:
                continue
            team = t.get("team") or {}
            out["transactions"].append({"date": t.get("date"), "team": team.get("abbreviation", ""), "name": team.get("name", ""), "desc": short(t.get("description"), 220)})
    except Exception as e:  # noqa: BLE001
        print("Transactions couldn't be read:", e)
    out["injuries"].sort(key=lambda x: (x["team"], x["name"]))
    try:
        old = json.load(open(path))
        if old.get("injuries") == out["injuries"] and old.get("transactions") == out["transactions"]:
            print("No change.")
            return
    except Exception:  # noqa: BLE001
        pass
    out["updated"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with open(path, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(len(out["injuries"]), "injuries,", len(out["transactions"]), "transactions.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "docs/data/news.json")
