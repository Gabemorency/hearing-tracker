"""
Bio Sync — runs every 6 hours via bio_sync.yml
Detects new members in legislators-current.yaml,
writes bios for them via Claude API,
removes departed members from bios_hardcoded.py.
"""

import json
import os
import re
import sys
import importlib.util
import requests
import yaml

BASE    = "https://raw.githubusercontent.com/unitedstates/congress-legislators/main"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; hearing-tracker-biosync/1.0)"}
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

STATE_NAMES = {
    "AL":"Alabama","AK":"Alaska","AZ":"Arizona","AR":"Arkansas","CA":"California",
    "CO":"Colorado","CT":"Connecticut","DE":"Delaware","FL":"Florida","GA":"Georgia",
    "HI":"Hawaii","ID":"Idaho","IL":"Illinois","IN":"Indiana","IA":"Iowa",
    "KS":"Kansas","KY":"Kentucky","LA":"Louisiana","ME":"Maine","MD":"Maryland",
    "MA":"Massachusetts","MI":"Michigan","MN":"Minnesota","MS":"Mississippi",
    "MO":"Missouri","MT":"Montana","NE":"Nebraska","NV":"Nevada","NH":"New Hampshire",
    "NJ":"New Jersey","NM":"New Mexico","NY":"New York","NC":"North Carolina",
    "ND":"North Dakota","OH":"Ohio","OK":"Oklahoma","OR":"Oregon","PA":"Pennsylvania",
    "RI":"Rhode Island","SC":"South Carolina","SD":"South Dakota","TN":"Tennessee",
    "TX":"Texas","UT":"Utah","VT":"Vermont","VA":"Virginia","WA":"Washington",
    "WV":"West Virginia","WI":"Wisconsin","WY":"Wyoming","DC":"District of Columbia",
    "PR":"Puerto Rico","VI":"U.S. Virgin Islands","GU":"Guam","AS":"American Samoa",
    "MP":"Northern Mariana Islands",
}

def fetch_yaml(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return yaml.safe_load(r.text)

def load_bios():
    if not os.path.exists("bios_hardcoded.py"):
        return {}
    spec = importlib.util.spec_from_file_location("bios_hardcoded", "bios_hardcoded.py")
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return dict(getattr(mod, "MEMBER_BIOS", {}))

def save_bios(bios):
    lines = [
        '"""',
        "Member bios for the current Congress.",
        "Auto-maintained by bio_sync.py — do not edit placeholders manually.",
        '"""',
        "",
        "MEMBER_BIOS = {",
    ]
    for bid, bio in sorted(bios.items()):
        escaped = bio.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        lines.append(f'    "{bid}": "{escaped}",')
    lines.append("}")
    lines.append("")
    with open("bios_hardcoded.py", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def write_bio(display_name, chamber, state, party, district=None):
    if not API_KEY:
        return ""
    state_full   = STATE_NAMES.get(state, state)
    party_full   = {"Republican":"Republican","Democrat":"Democrat","Independent":"Independent"}.get(party, party)
    chamber_word = "Senator" if "Senate" in chamber else "Representative"
    dist_str     = f"representing {state_full}'s {district}th Congressional District" if district else f"from {state_full}"

    prompt = (
        f"Write a professional 3-paragraph biography for {display_name}, "
        f"a {party_full} {chamber_word} {dist_str}.\n\n"
        "Paragraph 1 (2-3 sentences): Background — birthplace, education, career before Congress.\n"
        "Paragraph 2 (2-3 sentences): Congressional career — when first elected, key committees, what they are known for.\n"
        "Paragraph 3 (2-3 sentences): Current role — current focus, policy priorities, recent work.\n\n"
        "Rules: Third person, professional tone, no citation brackets, no headers. "
        "Separate paragraphs with a blank line. Return ONLY the 3 paragraphs."
    )

    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "Content-Type": "application/json",
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 800,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=30,
    )
    if r.status_code == 200:
        text = r.json().get("content", [{}])[0].get("text", "").strip()
        text = re.sub(r'\[\d+\]', "", text).strip()
        if len(text) > 200:
            return text
    return ""

def main():
    print("Fetching current legislators...")
    legislators = fetch_yaml(f"{BASE}/legislators-current.yaml")
    current_bids = {m.get("id", {}).get("bioguide", "") for m in legislators}
    current_bids.discard("")
    print(f"  {len(current_bids)} current members")

    print("Loading existing bios...")
    bios = load_bios()
    print(f"  {len(bios)} bios loaded")

    # 1. Remove departed members
    departed = [bid for bid in list(bios.keys()) if bid not in current_bids]
    for bid in departed:
        print(f"  Removing departed member: {bid}")
        del bios[bid]

    # 2. Find new members with no bio or placeholder bio
    PLACEHOLDER_PHRASE = "built a career in public service, business"
    new_or_placeholder = []
    for m in legislators:
        bid = m.get("id", {}).get("bioguide", "")
        if not bid:
            continue
        existing = bios.get(bid, "")
        if not existing or PLACEHOLDER_PHRASE in existing or len(existing) < 200:
            new_or_placeholder.append(m)

    print(f"  {len(new_or_placeholder)} members need bios")

    if not new_or_placeholder:
        print("Nothing to do.")
        if departed:
            save_bios(bios)
            print(f"Saved (removed {len(departed)} departed members)")
        return

    # 3. Write bios for new/placeholder members
    import time
    written = 0
    for m in new_or_placeholder:
        bid      = m.get("id", {}).get("bioguide", "")
        name     = m.get("name", {}).get("official_full", "")
        nick     = m.get("name", {}).get("nickname", "")
        term     = m.get("terms", [{}])[-1]
        chamber  = "United States Senate" if term.get("type") == "sen" else "United States House of Representatives"
        state    = term.get("state", "")
        party    = term.get("party", "")
        district = term.get("district") if term.get("type") == "rep" else None
        display  = f"{nick} {name.split()[-1]}" if nick else name

        print(f"  Writing bio for {display}...", end=" ", flush=True)
        bio = write_bio(display, chamber, state, party, district)
        if bio:
            bios[bid] = bio
            written += 1
            print("✓")
        else:
            print("✗ (API error)")
        time.sleep(0.5)

    save_bios(bios)
    print(f"\nDone. Written: {written}, Removed: {len(departed)}, Total: {len(bios)}")

if __name__ == "__main__":
    main()
