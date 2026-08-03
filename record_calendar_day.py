"""
record_calendar_day.py — called by update.yml after scrape.py and fetch_domewatch.py.
Appends/overwrites today's entry in calendar_history.json so the calendar page
builds up real day-by-day history automatically, with no manual backfill needed.
Idempotent per day: runs every 2 hours, each run just refreshes today's entry.
"""
import json
import os
from datetime import datetime, timezone, timedelta

from scrape import watch_link

HISTORY_FILE = "calendar_history.json"


def backfill_missing_links(history):
    """A watch-live link was only ever persisted going forward from when
    scrape.py's snapshot.json ordering bug was fixed — historical entries
    from before that fix have hearings with no link at all. watch_link() is
    a pure fuzzy-match against a static committee-page table (no network),
    so it's cheap and safe to recompute for any hearing still missing one,
    every run, rather than leaving those entries permanently broken."""
    filled = 0
    for day in history.values():
        for h in day.get("hearings", []):
            if not h.get("link"):
                link = watch_link(h.get("chamber", ""), h.get("committee", ""))
                if link:
                    h["link"] = link
                    filled += 1
    return filled


def get_et_offset():
    now_utc = datetime.now(timezone.utc)
    year = now_utc.year
    def nth_sunday(month, n):
        d = datetime(year, month, 1, tzinfo=timezone.utc)
        days_to_sun = (6 - d.weekday()) % 7
        return (d + timedelta(days=days_to_sun + 7 * (n - 1))).replace(hour=7)
    dst_start = nth_sunday(3, 2)
    dst_end = nth_sunday(11, 1)
    return timedelta(hours=-4) if dst_start <= now_utc < dst_end else timedelta(hours=-5)


def main():
    today_iso = (datetime.now(timezone.utc) + get_et_offset()).strftime("%Y-%m-%d")

    history = {}
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)

    hearings = []
    if os.path.exists("snapshot.json"):
        with open("snapshot.json", "r", encoding="utf-8") as f:
            snapshot = json.load(f)
        hearings = list(snapshot.values()) if isinstance(snapshot, dict) else []

    # Prefer the live floor-status feed for in-session accuracy; fall back to
    # "any non-cancelled hearing today" for days the feed is unavailable/empty.
    # DomeWatch's /floor response shape: {"now": {"value": "house_not_in_session", ...}, ...}
    in_session = None
    if os.path.exists("domewatch_floor.json"):
        with open("domewatch_floor.json", "r", encoding="utf-8") as f:
            floor = json.load(f)
        if floor and floor.get("now"):
            in_session = floor["now"].get("value") != "house_not_in_session"

    if in_session is None:
        in_session = any(not h.get("cancelled") for h in hearings)

    history[today_iso] = {"hearings": hearings, "inSession": in_session}

    filled = backfill_missing_links(history)

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"calendar_history.json: {today_iso} -> inSession={in_session}, hearings={len(hearings)} ({len(history)} days tracked total)"
          + (f"; backfilled {filled} missing watch link(s) in history" if filled else ""))


if __name__ == "__main__":
    main()
