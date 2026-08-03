"""
fetch_domewatch.py — called by update.yml every 2 hours
Fetches DomeWatch data server-side and saves as JSON files.
No CORS issues — this runs on GitHub Actions, not in a browser.
"""
import os
import json
import re
import requests

API_KEY = os.environ.get("DOMEWATCH_API_KEY", "")
BASE    = "https://data.domewatch.us/v1"

# DomeWatch's own billUrl (e.g. "https://www.congress.gov/bill/hr-8884") isn't a
# real congress.gov path — it loads (not dead) but lands on a search/fallback
# page instead of the bill. Build the correct one ourselves from the bill number.
CONGRESS = 119  # 2025-2027

BILL_TYPE_SLUGS = [
    (re.compile(r"^H\.J\.Res\.?$", re.IGNORECASE), "house-joint-resolution"),
    (re.compile(r"^S\.J\.Res\.?$", re.IGNORECASE), "senate-joint-resolution"),
    (re.compile(r"^H\.Con\.Res\.?$", re.IGNORECASE), "house-concurrent-resolution"),
    (re.compile(r"^S\.Con\.Res\.?$", re.IGNORECASE), "senate-concurrent-resolution"),
    (re.compile(r"^H\.Res\.?$", re.IGNORECASE), "house-resolution"),
    (re.compile(r"^S\.Res\.?$", re.IGNORECASE), "senate-resolution"),
    (re.compile(r"^H\.R\.?$", re.IGNORECASE), "house-bill"),
    (re.compile(r"^S\.?$", re.IGNORECASE), "senate-bill"),
]

def congress_gov_bill_url(bill_number, fallback=None):
    """Build a real congress.gov bill URL from a bill number like 'H.R. 8884'."""
    if not bill_number:
        return fallback
    m = re.match(r"^\s*([A-Za-z.]+)\s*(\d+)\s*$", bill_number)
    if not m:
        return fallback
    prefix, number = m.group(1), m.group(2)
    for pattern, slug in BILL_TYPE_SLUGS:
        if pattern.match(prefix):
            return f"https://www.congress.gov/bill/{CONGRESS}th-congress/{slug}/{number}"
    return fallback

def fix_whip_bill_urls(data):
    """Rewrite each whip item's billUrl in place to a real congress.gov link."""
    if not data:
        return data
    for notice in data.get("data", []):
        for item in notice.get("items", []):
            item["billUrl"] = congress_gov_bill_url(item.get("billNumber"), fallback=item.get("billUrl"))
    return data

def fetch(endpoint, params=None):
    url = BASE + endpoint
    headers = {"X-API-Key": API_KEY, "Accept": "application/json"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        print(f"  Warning: {endpoint} failed — {e}")
        return None

def save(filename, data, fallback):
    """Save data to file, preserving existing file if fetch failed."""
    if data is not None:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f)
        print(f"  {filename} saved ({len(json.dumps(data))} bytes)")
    elif os.path.exists(filename):
        print(f"  {filename} unchanged (kept existing)")
    else:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(fallback, f)
        print(f"  {filename} created with fallback")

def main():
    if not API_KEY:
        print("WARNING: DOMEWATCH_API_KEY not set — skipping DomeWatch fetch")
        return

    print("Fetching DomeWatch data...")

    # 1. Whip notices
    data = fetch("/whip-notices", {"limit": 3})
    data = fix_whip_bill_urls(data)
    save("domewatch_whip.json", data, {"data": []})

    # 2. Committee meetings — DomeWatch's data here is mostly a record of
    # meetings that already happened, not a forward schedule, so querying
    # only "today..+30 days" returns 0 results whenever nothing's been
    # published that far ahead (e.g. during a recess) even though real
    # meetings from the recent past exist. calendar.html's own committee
    # rendering already looks back 90 days, so match that window here.
    from datetime import datetime, timedelta
    start = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d")
    end   = (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%d")
    data  = fetch("/committee-meetings", {"from": start, "to": end})
    if data is not None and not data.get("data"):
        print(f"  Note: /committee-meetings returned 0 results for {start}..{end} "
              f"(request succeeded — this account's plan may not include this "
              f"endpoint, or DomeWatch has no meeting records in this window; "
              f"not a code error)")
    save("domewatch_meetings.json", data, {"data": []})

    # 3. House floor status (in session / recess / active vote)
    data = fetch("/floor")
    save("domewatch_floor.json", data, {})

    print("DomeWatch fetch complete.")

if __name__ == "__main__":
    main()
