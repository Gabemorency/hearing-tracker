"""
Temporary diagnostic: does DomeWatch's /committee-meetings endpoint return
data for PAST date ranges (with hearing detail / witness / vote links), or
only the forward-looking window we currently query? Prints raw shape so we
can decide whether calendar history can be backfilled from DomeWatch itself
instead of relying solely on our own git-history mining.

Not part of the regular pipeline — delete after use.
"""
import os
import json
import requests

API_KEY = os.environ.get("DOMEWATCH_API_KEY", "")
BASE = "https://data.domewatch.us/v1"

def fetch(endpoint, params=None):
    headers = {"X-API-Key": API_KEY, "Accept": "application/json"}
    r = requests.get(BASE + endpoint, headers=headers, params=params, timeout=15)
    print(f"GET {endpoint} {params} -> {r.status_code}")
    try:
        return r.json()
    except Exception as e:
        print("  non-JSON response:", r.text[:500])
        return None

if __name__ == "__main__":
    if not API_KEY:
        print("NO API KEY SET")
        raise SystemExit(1)

    print("=== /committee-meetings, past range 2026-07-13..2026-07-23 ===")
    data = fetch("/committee-meetings", {"from": "2026-07-13", "to": "2026-07-23"})
    if data:
        items = data.get("data", [])
        print(f"count: {len(items)}")
        if items:
            print(json.dumps(items[0], indent=2)[:3000])

    print()
    print("=== /committee-meetings, single past day 2026-07-22 ===")
    data2 = fetch("/committee-meetings", {"from": "2026-07-22", "to": "2026-07-22"})
    if data2:
        items2 = data2.get("data", [])
        print(f"count: {len(items2)}")
        if items2:
            print(json.dumps(items2[0], indent=2)[:3000])

    print()
    print("=== /floor, does it accept a date param for history? ===")
    data3 = fetch("/floor", {"date": "2026-07-22"})
    if data3:
        print(json.dumps(data3, indent=2)[:2000])
