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

The meeting id is docs.house.gov's own permanent EventId (it's literally in
the url, e.g. ?EventId=119443), not something DomeWatch invents, so it
shouldn't ever point to different content later — but "shouldn't" isn't
"can't" (e.g. the Clerk's office corrects a listing in place rather than
reposting under a new id). As cheap insurance against that, any leftover
scrape budget after covering brand-new meetings goes toward re-verifying the
longest-unchecked cached entries, oldest first, rather than sitting idle.
This never competes with new-meeting coverage — it only runs once the
backlog of brand-new meetings is caught up for a given run.
"""
import json
import os
import re
from playwright.sync_api import sync_playwright

MEETINGS_FILE   = "domewatch_meetings.json"
CACHE_FILE      = "domewatch_meeting_committees.json"
MAX_PER_RUN     = 30
RECHECK_PER_RUN = 3

# Real shape confirmed against a live docs.house.gov ByEvent.aspx page:
# <h1>Meeting: <title><small class="text-tiny"><blockquote>
#   <p>Committee on Rules<br></p></blockquote></small></h1>
COMMITTEE_RE = re.compile(
    r"<h1[^>]*>.*?<blockquote>\s*<p>(.*?)(?:<br\s*/?>)?\s*</p>", re.S | re.I)

def load_json(path, fallback):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return fallback

def pending_meetings(meetings, cache, max_per_run=MAX_PER_RUN):
    """Meetings with an id/url not yet in the cache, capped to max_per_run."""
    pending = [m for m in meetings if m.get("id") and m.get("url") and m["id"] not in cache]
    return pending[:max_per_run]

def recheck_candidates(meetings, cache, limit):
    """Cached meetings still present in the current meeting list, oldest
    check first, to re-verify — up to limit. Dict insertion order tracks
    check recency here: main() re-inserts a key after each recheck, so the
    least-recently-checked entries naturally surface first over time."""
    if limit <= 0:
        return []
    by_id = {m["id"]: m for m in meetings if m.get("id") and m.get("url")}
    return [by_id[mid] for mid in cache if mid in by_id][:limit]

def extract_committee_name(html):
    """Pull the committee name out of a docs.house.gov ByEvent.aspx page's
    <h1>Meeting: <title><small><blockquote><p>Committee Name</p> structure."""
    m = COMMITTEE_RE.search(html)
    if not m:
        return None
    name = re.sub(r"<[^>]+>", "", m.group(1)).strip()
    return name or None

def main():
    meetings = load_json(MEETINGS_FILE, {"data": []}).get("data", [])
    cache    = load_json(CACHE_FILE, {})

    new_batch = pending_meetings(meetings, cache)
    leftover  = MAX_PER_RUN - len(new_batch)
    recheck_batch = recheck_candidates(meetings, cache, min(leftover, RECHECK_PER_RUN))
    batch = new_batch + recheck_batch

    if not batch:
        print(f"scrape_meeting_committees: nothing to scrape or recheck "
              f"({len(cache)} cached, {len(meetings)} known meetings)")
        return

    total_uncached = sum(1 for m in meetings if m.get("id") and m.get("url") and m["id"] not in cache)
    print(f"scrape_meeting_committees: scraping {len(new_batch)} new "
          f"(of {total_uncached} uncached) + rechecking {len(recheck_batch)} "
          f"cached ({len(cache)} total cached)")

    found, changed = 0, 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        for m in batch:
            try:
                page.goto(m["url"], wait_until="domcontentloaded", timeout=20000)
                name = extract_committee_name(page.content())
                if name:
                    if m["id"] in cache and cache[m["id"]] != name:
                        print(f"  {m['id']}: committee changed on recheck "
                              f"({cache[m['id']]!r} -> {name!r})")
                        changed += 1
                    if m["id"] in cache:
                        del cache[m["id"]]  # reinsert below moves it to the
                    cache[m["id"]] = name   # end, rotating the recheck order
                    found += 1
            except Exception as e:
                print(f"  {m['id']}: failed ({e})")
        browser.close()

    print(f"scrape_meeting_committees: found {found} committee names this run"
          + (f", {changed} changed on recheck" if changed else ""))

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
        f.write("\n")

if __name__ == "__main__":
    main()
