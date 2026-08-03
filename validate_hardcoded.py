"""
Validates hardcoded data every 3 days.
Checks: institutional leadership (institutional_leadership.json), CBC
membership, vacant House seats (vacant_seats.json — auto-removes entries once
filled), and departed members in bios_hardcoded.json (auto-removed).
Opens a GitHub Issue if anything still needs a human to update.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

try:
    import requests
    import yaml
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                          "requests", "pyyaml", "--break-system-packages", "-q"])
    import requests
    import yaml

BASE    = "https://raw.githubusercontent.com/unitedstates/congress-legislators/main"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; hearing-tracker-validator/1.0)"}

def fetch_yaml(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return yaml.safe_load(r.text)

# ── Load current legislators ───────────────────────────────────────────────────
print("📥 Fetching current legislators...")
legislators = fetch_yaml(f"{BASE}/legislators-current.yaml")
current_bids = {m.get("id", {}).get("bioguide", "") for m in legislators}
bid_to_name  = {
    m.get("id", {}).get("bioguide", ""): m.get("name", {}).get("official_full", "")
    for m in legislators
}

issues = []

# ── 1. Check institutional leadership ─────────────────────────────────────────
print("🔍 Checking institutional leadership...")
with open("institutional_leadership.json", "r", encoding="utf-8") as _lf:
    INSTITUTIONAL_LEADERSHIP = json.load(_lf)

for bid, info in INSTITUTIONAL_LEADERSHIP.items():
    if bid not in current_bids:
        name = bid_to_name.get(bid, bid)
        issues.append(f"⚠️ **Leadership:** `{info['label']}` holder `{name}` ({bid}) is no longer in current legislators dataset — may have left office. Update institutional_leadership.json.")

# ── 2. Check CBC membership ────────────────────────────────────────────────────
print("🔍 Checking CBC membership...")
CBC_BIOGUIDES = [
    "N000147","W000187","B000490","C000537","S000185","T000193","D000096",
    "M001137","C001061","G000553","M001160","C001067","J000288","C001072",
    "M000687","S001185","W000808","B001281","J000294","V000131","K000385",
    "B001288","A000370","P000610","W000822","E000296","B001303","H001066",
    "H001081","M001208","N000191","O000173","P000617","U000040","W000788",
    "T000486","S001159","W000790","C001125","B001313","C001130","D000230",
    "F000477","F000476","I000058","J000309","K000400","L000602","S001223",
    "M001227","A000380","M001229","A000382","B001324","B001326","C001136",
    "F000110","F000481","S001231","M001245",
]

for bid in CBC_BIOGUIDES:
    if bid not in current_bids:
        name = bid_to_name.get(bid, bid)
        issues.append(f"⚠️ **CBC:** Member `{name}` ({bid}) is no longer in current legislators dataset — may have left office or seat is vacant.")

# ── 3. Check for new CBC members (Democrats not in list) ──────────────────────
# Flag any Black Caucus members on cbc.house.gov not in our list
# (We can't auto-detect race, so just flag if CBC count changes significantly)
print("🔍 Checking for potential new CBC members...")
dem_house = [m for m in legislators
             if m.get("terms", [{}])[-1].get("party") == "Democrat"
             and m.get("terms", [{}])[-1].get("type") == "rep"]
cbc_set = set(CBC_BIOGUIDES)
print(f"  Current CBC list: {len(cbc_set)} members")
print(f"  Total House Democrats: {len(dem_house)}")
if len(dem_house) < len(cbc_set):
    issues.append(f"⚠️ **CBC:** CBC list has {len(cbc_set)} members but only {len(dem_house)} House Democrats exist — list may include departed members.")

# ── 4. Check for vacant House seats ───────────────────────────────────────────
print("🔍 Checking for vacant House seats...")

# 4a. Auto-remove entries from vacant_seats.json whose seat now has a sitting member
rep_seats = {
    (m.get("terms", [{}])[-1].get("state"), m.get("terms", [{}])[-1].get("district"))
    for m in legislators
    if m.get("terms", [{}])[-1].get("type") == "rep"
}
if os.path.exists("vacant_seats.json"):
    with open("vacant_seats.json", "r", encoding="utf-8") as _vf:
        vacant_seats = json.load(_vf)
    filled = [v for v in vacant_seats if (v["state"], v["district"]) in rep_seats]
    if filled:
        for v in filled:
            print(f"  Seat now filled — removing: {v['label']}")
        vacant_seats = [v for v in vacant_seats if v not in filled]
        with open("vacant_seats.json", "w", encoding="utf-8") as _vf:
            json.dump(vacant_seats, _vf, indent=2, ensure_ascii=False)
            _vf.write("\n")
        labels = ", ".join(v["label"] for v in filled)
        issues.append(f"ℹ️ **Vacant seats cleaned:** Removed {len(filled)} seat(s) now filled from vacant_seats.json: {labels}")
    else:
        print(f"  vacant_seats.json is current — {len(vacant_seats)} listed, none yet filled")
else:
    vacant_seats = []
    print("  ℹ️  vacant_seats.json not found — skipping")

# 4b. Check aggregate sitting-member count for vacancies not yet listed
try:
    sitting_count = len([m for m in legislators
                        if m.get("terms", [{}])[-1].get("type") == "rep"
                        and m.get("terms", [{}])[-1].get("state") not in
                        {"DC","PR","VI","GU","AS","MP"}])
    known_vacant = len(vacant_seats)
    if sitting_count + known_vacant < 435:
        unlisted = 435 - sitting_count - known_vacant
        issues.append(f"ℹ️ **Vacant seats:** {unlisted} House seat(s) appear vacant but aren't in vacant_seats.json ({sitting_count} sitting voting members, {known_vacant} already listed). Add the new vacancy to vacant_seats.json.")
    print(f"  Sitting House members (voting): {sitting_count}, listed vacancies: {known_vacant}")
except Exception as e:
    print(f"  Could not check vacancies: {e}")

# ── 5. Remove departed members from bios_hardcoded.json ───────────────────────
print("🧹 Checking bios_hardcoded.json for departed members...")
if os.path.exists("bios_hardcoded.json"):
    try:
        with open("bios_hardcoded.json", "r", encoding="utf-8") as _f:
            existing_bios = json.load(_f)
        departed_bids = [bid for bid in existing_bios if bid not in current_bids and bid]
        if departed_bids:
            print(f"  Found {len(departed_bids)} departed member(s) in bios_hardcoded.json — removing...")
            for bid in departed_bids:
                name = bid_to_name.get(bid, bid)
                print(f"    Removing: {bid} ({name})")
                del existing_bios[bid]
            with open("bios_hardcoded.json", "w", encoding="utf-8") as _f:
                json.dump(existing_bios, _f, indent=2, sort_keys=True, ensure_ascii=False)
                _f.write("\n")
            print(f"  ✅ bios_hardcoded.json updated — {len(departed_bids)} departed member(s) removed")
            issues.append(f"ℹ️ **Bios cleaned:** Removed {len(departed_bids)} departed member(s) from bios_hardcoded.json: {', '.join(departed_bids)}")
        else:
            print("  ✅ bios_hardcoded.json is current — no departed members found")
    except Exception as e:
        print(f"  ⚠️  Could not process bios_hardcoded.json: {e}")
else:
    print("  ℹ️  bios_hardcoded.json not found — skipping cleanup")

if issues:
    print(f"\n⚠️  {len(issues)} issue(s) found:")
    for issue in issues:
        print(f"  {issue}")

    # Write issues to a file for the workflow to read
    with open("validation_issues.txt", "w") as f:
        f.write("\n".join(issues))

    # Exit with code 1 to signal the workflow to create a GitHub Issue
    sys.exit(1)
else:
    print("\n✅ All hardcoded data looks current.")
    if os.path.exists("validation_issues.txt"):
        os.remove("validation_issues.txt")
    sys.exit(0)
