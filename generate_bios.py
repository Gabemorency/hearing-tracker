"""
generate_bios.py — One-time bio generator
Run manually via GitHub Actions: Actions → Generate Member Bios → Run workflow
Uses Claude API directly to write clean 3-paragraph bios for all members.
No web scraping — Claude knows these public figures from training data.
"""

import requests
import yaml
import json
import time
import os
import re

# ── Load members ──────────────────────────────────────────────────────────────
print("📥 Loading legislators...")
r = requests.get(
    "https://raw.githubusercontent.com/unitedstates/congress-legislators/main/legislators-current.yaml",
    timeout=30
)
legislators = yaml.safe_load(r.text)
print(f"  {len(legislators)} members loaded")

# ── Load existing bios if resuming ────────────────────────────────────────────
OUTPUT_FILE = "bios_hardcoded.py"
bios = {}
if os.path.exists(OUTPUT_FILE):
    import importlib.util
    spec = importlib.util.spec_from_file_location("bios_hardcoded", OUTPUT_FILE)
    mod  = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        bios = dict(getattr(mod, "MEMBER_BIOS", {}))
        print(f"  Resuming — {len(bios)} bios already done")
    except:
        pass

# ── State name lookup ─────────────────────────────────────────────────────────
STATE_NAMES = {
    'AL':'Alabama','AK':'Alaska','AZ':'Arizona','AR':'Arkansas','CA':'California',
    'CO':'Colorado','CT':'Connecticut','DE':'Delaware','FL':'Florida','GA':'Georgia',
    'HI':'Hawaii','ID':'Idaho','IL':'Illinois','IN':'Indiana','IA':'Iowa',
    'KS':'Kansas','KY':'Kentucky','LA':'Louisiana','ME':'Maine','MD':'Maryland',
    'MA':'Massachusetts','MI':'Michigan','MN':'Minnesota','MS':'Mississippi',
    'MO':'Missouri','MT':'Montana','NE':'Nebraska','NV':'Nevada','NH':'New Hampshire',
    'NJ':'New Jersey','NM':'New Mexico','NY':'New York','NC':'North Carolina',
    'ND':'North Dakota','OH':'Ohio','OK':'Oklahoma','OR':'Oregon','PA':'Pennsylvania',
    'RI':'Rhode Island','SC':'South Carolina','SD':'South Dakota','TN':'Tennessee',
    'TX':'Texas','UT':'Utah','VT':'Vermont','VA':'Virginia','WA':'Washington',
    'WV':'West Virginia','WI':'Wisconsin','WY':'Wyoming','DC':'District of Columbia',
    'PR':'Puerto Rico','VI':'U.S. Virgin Islands','GU':'Guam','AS':'American Samoa',
    'MP':'Northern Mariana Islands'
}

# ── Institutional leadership roles ────────────────────────────────────────────
INST_ROLES = {
    "T000250": "Senate Majority Leader",
    "G000386": "President Pro Tempore of the United States Senate",
    "B001261": "Senate Majority Whip",
    "C001095": "Senate Republican Conference Chair",
    "L000575": "Senate Republican Conference Vice Chair",
    "C001047": "Senate Republican Policy Committee Chair",
    "S000148": "Senate Minority Leader",
    "D000563": "Senate Minority Whip",
    "K000367": "Senate Democratic Steering and Policy Committee Chair",
    "B001288": "Senate Democratic Strategic Communications Chair",
    "J000299": "Speaker of the United States House of Representatives",
    "S001176": "House Majority Leader",
    "E000294": "House Majority Whip",
    "M001136": "House Republican Conference Chair",
    "J000294": "House Minority Leader",
    "C001101": "House Minority Whip",
    "A000371": "House Democratic Caucus Chair",
    "N000191": "Assistant House Democratic Leader",
}

# ── Write bio with Claude (no scraping) ──────────────────────────────────────
def write_bio(name, chamber, state_code, party, role, district=None):
    state_full   = STATE_NAMES.get(state_code, state_code)
    chamber_word = "Senator" if "Senate" in chamber else "Representative"
    dist_str     = f", {state_full}'s {district}th Congressional District" if district else f" from {state_full}"
    role_str     = f", currently serving as {role}" if role else ""
    party_full   = {"Republican": "Republican", "Democrat": "Democrat",
                    "Independent": "Independent"}.get(party, party)

    prompt = f"""Write a professional 3-paragraph biography for {name}, a {party_full} {chamber_word}{dist_str}{role_str}.

Paragraph 1 — Background (2-3 sentences):
Where they are from, their upbringing, education, and professional career before entering Congress.

Paragraph 2 — Congressional Career (2-3 sentences):
When they were first elected to Congress, their key legislative achievements, committees they have served on, and what they are best known for.

Paragraph 3 — Current Role (2-3 sentences):
Their current responsibilities and position, the policy areas and issues they focus on, and their recent legislative priorities or notable work.

Requirements:
- Write in third person throughout
- Use their last name after the first full mention
- Professional, factual, neutral tone
- Each paragraph must be exactly 2-3 complete sentences — never just one sentence
- Separate paragraphs with a single blank line
- No headers, labels, bullet points, or preamble
- No citation brackets like [1] or [2]
- Draw on your knowledge of this person's public career

Return ONLY the three paragraphs."""

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"Content-Type": "application/json"},
            json={
                "model":      "claude-sonnet-4-6",
                "max_tokens": 1000,
                "messages":   [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        if r.status_code == 200:
            text = r.json().get("content", [{}])[0].get("text", "").strip()
            text = re.sub(r'\[\d+\]', '', text).strip()
            if len(text) > 200 and '\n\n' in text:
                return text
            elif len(text) > 200:
                return text
        else:
            print(f"    Claude {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"    Claude error: {e}")
    return ""

# ── Save helper ───────────────────────────────────────────────────────────────
def save_bios():
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write('"""\nAuto-generated member bios — regenerate with generate_bios.py\n"""\n\n')
        f.write("MEMBER_BIOS = {\n")
        for bid, bio in sorted(bios.items()):
            escaped = bio.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            f.write(f'    "{bid}": "{escaped}",\n')
        f.write("}\n")

# ── Main loop ─────────────────────────────────────────────────────────────────
total     = len(legislators)
processed = 0
skipped   = 0
errors    = 0

for i, m in enumerate(legislators):
    bid  = m.get("id", {}).get("bioguide", "")
    name = m.get("name", {}).get("official_full", "")
    nick = m.get("name", {}).get("nickname", "")
    if not bid or not name:
        continue

    # Always regenerate every member for consistency

    term     = m.get("terms", [{}])[-1]
    chamber  = "United States Senate" if term.get("type") == "sen" else "United States House of Representatives"
    state    = term.get("state", "")
    party    = term.get("party", "")
    district = term.get("district") if term.get("type") == "rep" else None
    role     = INST_ROLES.get(bid, "")

    # Use nickname if available for better recognition
    display_name = name
    if nick:
        parts = name.split()
        if len(parts) >= 2:
            display_name = f"{nick} {parts[-1]}"

    print(f"[{i+1}/{total}] {display_name} ({bid})...", end=" ", flush=True)

    bio = write_bio(display_name, chamber, state, party, role, district)

    if bio:
        bios[bid] = bio
        processed += 1
        paragraphs = [p for p in bio.split('\n\n') if p.strip()]
        print(f"✓ ({len(paragraphs)} paragraphs, {len(bio)} chars)")
    else:
        bios[bid] = f"{display_name} is a member of the {chamber} from {STATE_NAMES.get(state, state)}."
        errors += 1
        print("❌ Claude failed")

    # Save checkpoint every 10 members
    if (i + 1) % 10 == 0:
        save_bios()
        print(f"  💾 Checkpoint: {len(bios)}/{total}")

    time.sleep(0.5)  # Rate limiting

# Final save
save_bios()
print(f"\n✅ Done: {processed} written, {skipped} skipped, {errors} errors")
print(f"📄 Output: {OUTPUT_FILE} ({len(bios)} bios)")
