"""Pull CELESTE Classic runs from June 2026 for one category, plus a few rows
from the games and developers tables, using the speedrun.com API (v1).

Usage: python pull.py [--category "100%"]   (default category: Any%)
"""

import argparse
import csv
import time

import requests

BASE_URL = "https://www.speedrun.com/api/v1"
MIN_INTERVAL = 0.7  # seconds between requests; the API allows 100 per minute
GAME_ID = "4d7e7z67"  # CELESTE Classic (speedrun.com/celestep8)
MONTH = "2026-06"
SAMPLE_ROWS = 5

session = requests.Session()
session.headers["User-Agent"] = "fastandfurious-pull/0.1"
last_request = 0.0


def get(url, params=None):
    """GET an API path or full URL, staying under the rate limit."""
    global last_request
    if not url.startswith("http"):
        url = f"{BASE_URL}/{url}"
    for _ in range(5):
        time.sleep(max(0, MIN_INTERVAL - (time.monotonic() - last_request)))
        last_request = time.monotonic()
        resp = session.get(url, params=params, timeout=30)
        if resp.status_code in (420, 429):  # rate limited: wait out the window
            time.sleep(60)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"Still rate limited after 5 attempts: {url}")


def find_category_id(name):
    categories = get(f"games/{GAME_ID}/categories")["data"]
    for category in categories:
        if category["name"].lower() == name.lower():
            return category["id"]
    options = ", ".join(c["name"] for c in categories)
    raise SystemExit(f"No category named {name!r}. Options: {options}")


def fetch_runs(category_id):
    """Runs dated in MONTH. The API has no date filter, so page newest-first
    and stop once runs are older than MONTH (undated runs sort last)."""
    runs = []
    url = "runs"
    params = {"game": GAME_ID, "category": category_id, "orderby": "date",
              "direction": "desc", "max": 200, "embed": "players"}
    while url:
        page = get(url, params)
        for run in page["data"]:
            date = run["date"] or ""
            if date < MONTH:
                return runs
            if date.startswith(MONTH):
                runs.append(run)
        url = next((l["uri"] for l in page["pagination"]["links"] if l["rel"] == "next"), None)
        params = None  # the "next" link already includes the query
    return runs


def run_row(run, category):
    players = [p["names"]["international"] if p["rel"] == "user" else p["name"]
               for p in run["players"]["data"]]
    videos = (run["videos"] or {}).get("links") or []
    return {
        "run_id": run["id"],
        "category": category,
        "players": "; ".join(players),
        "status": run["status"]["status"],
        "date": run["date"],
        "submitted": run["submitted"],
        "time_s": run["times"]["primary_t"],
        "video": videos[0]["uri"] if videos else None,
        "weblink": run["weblink"],
        "comment": run["comment"],
    }


def game_row(game):
    return {
        "game_id": game["id"],
        "name": game["names"]["international"],
        "abbreviation": game["abbreviation"],
        "released": game["released"],
        "developers": "; ".join(game["developers"]),
        "weblink": game["weblink"],
    }


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {path}")


def main():
    parser = argparse.ArgumentParser(description="Pull CELESTE Classic runs from June 2026.")
    parser.add_argument("--category", default="Any%",
                        help="category name, matched case-insensitively (default: Any%%)")
    args = parser.parse_args()

    category_id = find_category_id(args.category)
    runs = [run_row(r, args.category) for r in fetch_runs(category_id)]
    write_csv("celeste_classic_runs_2026_06.csv", runs,
              ["run_id", "category", "players", "status", "date", "submitted",
               "time_s", "video", "weblink", "comment"])

    games = [get(f"games/{GAME_ID}")["data"]] + get("games", {"max": SAMPLE_ROWS - 1})["data"]
    write_csv("games.csv", [game_row(g) for g in games],
              ["game_id", "name", "abbreviation", "released", "developers", "weblink"])

    # speedrun.com no longer fills this table, so this file may only have a header.
    developers = get("developers", {"max": SAMPLE_ROWS})["data"]
    write_csv("developers.csv", [{"developer_id": d["id"], "name": d["name"]} for d in developers],
              ["developer_id", "name"])


if __name__ == "__main__":
    main()
