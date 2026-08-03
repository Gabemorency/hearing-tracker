"""
TEMPORARY diagnostic script — to be deleted after use.
Investigates whether DomeWatch's API exposes a forward-looking session
calendar (projected in-session/recess days for the next few months),
the way their website shows one. Tries a range of plausible endpoint
names and also dumps the full shape of any hit so we know what fields
are available.
"""
import os
import json
import requests

API_KEY = os.environ.get("DOMEWATCH_API_KEY", "")
BASE = "https://data.domewatch.us/v1"

CANDIDATES = [
    "/session-calendar",
    "/calendar",
    "/legislative-calendar",
    "/schedule",
    "/session-days",
    "/floor-calendar",
    "/in-session",
    "/house-calendar",
    "/senate-calendar",
    "/floor/calendar",
    "/floor-schedule",
    "/congress-calendar",
]

def fetch(endpoint, params=None):
    url = BASE + endpoint
    headers = {"X-API-Key": API_KEY, "Accept": "application/json"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        print(f"  {endpoint} -> HTTP {r.status_code}")
        if r.status_code == 200:
            try:
                return r.json()
            except Exception as e:
                print(f"    (not JSON: {e}); body[:300]={r.text[:300]!r}")
        else:
            print(f"    body[:300]={r.text[:300]!r}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"  {endpoint} -> request failed: {e}")
        return None

def main():
    if not API_KEY:
        print("WARNING: DOMEWATCH_API_KEY not set")
        return

    print("=== Trying candidate session-calendar endpoints ===")
    for ep in CANDIDATES:
        data = fetch(ep)
        if data:
            print(f"    HIT! Keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
            print(f"    Sample: {json.dumps(data, indent=2)[:2000]}")

    print("\n=== Re-checking known-good /floor endpoint for hints of a calendar field ===")
    data = fetch("/floor")
    if data:
        print(json.dumps(data, indent=2)[:3000])

    print("\n=== Re-checking /committee-meetings response shape for any calendar-like sibling data ===")
    data = fetch("/committee-meetings", {"from": "2026-08-01", "to": "2026-08-10"})
    if data:
        print(f"Top-level keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")

if __name__ == "__main__":
    main()
