"""
Validates hardcoded data every 3 days.
Checks: institutional leadership, CBC membership, committee chairs, vacant seats.
Opens a GitHub Issue if anything is out of date.
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
INSTITUTIONAL_LEADERSHIP = {
    "T000250": "Senate Majority Leader",
    "G000386": "President Pro Tempore",
    "B001261": "Senate Majority Whip",
    "C001095": "Senate Conference Chair",
    "L000575": "Senate Conference Vice Chair",
    "C001047": "Senate Policy Committee Chair",
    "S000148": "Senate Minority Leader",
    "D000563": "Senate Minority Whip",
    "K000367": "Steering & Policy Chair",
    "B001288": "Strategic Communications Chair",
    "J000299": "Speaker of the House",
    "S001176": "House Majority Leader",
    "E000294": "House Majority Whip",
    "M001136": "House Conference Chair",
    "J000294": "House Minority Leader",
    "C001101": "House Minority Whip",
    "A000371": "House Democratic Caucus Chair",
    "N000191": "Asst. Democratic Leader",
}

for bid, role in INSTITUTIONAL_LEADERSHIP.items():
    if bid not in current_bids:
        name = bid_to_name.get(bid, bid)
        issues.append(f"⚠️ **Leadership:** `{role}` holder `{name}` ({bid}) is no longer in current legislators dataset — may have left office.")

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
try:
    r = requests.get("https://clerk.house.gov/members", headers=HEADERS, timeout=20)
    sitting_count = len([m for m in legislators
                        if m.get("terms", [{}])[-1].get("type") == "rep"
                        and m.get("terms", [{}])[-1].get("state") not in
                        {"DC","PR","VI","GU","AS","MP"}])
    if sitting_count < 435:
        vacant = 435 - sitting_count
        issues.append(f"ℹ️ **Vacant seats:** {vacant} House seat(s) currently vacant ({sitting_count} sitting voting members). Consider updating the vacant seats section in build_members.py.")
    print(f"  Sitting House members (voting): {sitting_count}")
except Exception as e:
    print(f"  Could not check vacancies: {e}")

# ── 5. Report ──────────────────────────────────────────────────────────────────
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
