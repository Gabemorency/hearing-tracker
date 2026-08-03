"""
scrape_meeting_committees.py — called by update.yml after fetch_domewatch.py

DomeWatch's /committee-meetings API gives us meeting schedules with a real
link to the official docs.house.gov event page, but no committee name — the
API response only has id, subcommittee, startDate, endDate, location,
meetingType, and url. The committee name lives on that linked page (e.g. an
<h1> like "Meeting: <title><small><blockquote><p>Committee on Rules</p>"),
so we scrape it from there instead of guessing.

Building a small persistent cache (meeting id -> committee name) rather than
re-scraping DomeWatch's ~200+ known meetings on every 2-hour run. Only new,
uncached meeting ids get fetched, capped per run since each fetch is a real
Playwright page load. A meeting whose page fails to load or doesn't match
the expected shape (seen in the wild — some event ids 404 on the House side)
is simply left out of the cache and calendar.html falls back to its existing
generic "Hearing — Rm ___" label for it.
"""
import json
import os
from playwright.sync_api import sync_playwright

MEETINGS_FILE   = "domewatch_meetings.json"
CACHE_FILE      = "domewatch_meeting_committees.json"
MAX_PER_RUN     = 30

def load_json(path, fallback):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return fallback

def pending_meetings(meetings, cache, max_per_run=MAX_PER_RUN):
    """Meetings with an id/url not yet in the cache, capped to max_per_run."""
    pending = [m for m in meetings if m.get("id") and m.get("url") and m["id"] not in cache]
    return pending[:max_per_run]

def extract_committee_name(page):
    """Pull the committee name out of a docs.house.gov ByEvent.aspx page's
    <h1>Meeting: <title><small><blockquote><p>Committee Name</p> structure."""
    el = page.query_selector("h1 small blockquote p")
    return el.inner_text().strip() if el else None

def main():
    meetings = load_json(MEETINGS_FILE, {"data": []}).get("data", [])
    cache    = load_json(CACHE_FILE, {})
    batch    = pending_meetings(meetings, cache)

    if not batch:
        print(f"scrape_meeting_committees: nothing new to scrape "
              f"({len(cache)} cached, {len(meetings)} known meetings)")
        return

    print(f"scrape_meeting_committees: scraping {len(batch)} of "
          f"{len(pending)} uncached meetings ({len(cache)} already cached)")

    found = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        for m in batch:
            try:
                page.goto(m["url"], wait_until="domcontentloaded", timeout=20000)
                name = extract_committee_name(page)
                if name:
                    cache[m["id"]] = name
                    found += 1
            except Exception as e:
                print(f"  {m['id']}: failed ({e})")
        browser.close()

    print(f"scrape_meeting_committees: found {found} committee names this run")

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
        f.write("\n")

if __name__ == "__main__":
    main()
