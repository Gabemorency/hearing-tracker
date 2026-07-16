"""
fetch_domewatch.py — called by update.yml every 2 hours
Fetches DomeWatch data server-side and saves as JSON files.
No CORS issues — this runs on GitHub Actions, not in a browser.
"""
import os
import json
import requests

API_KEY = os.environ.get("DOMEWATCH_API_KEY", "")
BASE    = "https://data.domewatch.us/v1"

if not API_KEY:
    print("WARNING: DOMEWATCH_API_KEY not set — skipping DomeWatch fetch")
    raise SystemExit(0)

HEADERS = {
    "X-API-Key": API_KEY,
    "Accept":    "application/json",
}

def fetch(endpoint, params=None):
    url = BASE + endpoint
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=15)
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

print("Fetching DomeWatch data...")

# 1. Whip notices
data = fetch("/whip-notices", {"limit": 3})
save("domewatch_whip.json", data, {"data": []})

# 2. Floor updates
data = fetch("/floor-updates", {"limit": 8})
save("domewatch_updates.json", data, {"data": []})

# 3. Committee meetings — next 30 days
from datetime import datetime, timedelta
today = datetime.utcnow().strftime("%Y-%m-%d")
end   = (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%d")
data  = fetch("/committee-meetings", {"from": today, "to": end})
save("domewatch_meetings.json", data, {"data": []})

print("DomeWatch fetch complete.")
