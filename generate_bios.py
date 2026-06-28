"""
generate_bios.py — One-time bio generator
Run manually via GitHub Actions: Actions → Generate Member Bios → Run workflow
Scrapes Wikipedia for each member, rewrites with Claude API,
writes bios_hardcoded.py to the repo root.
"""

import requests
import yaml
import json
import time
import os
import re

BASE_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; hearing-tracker/1.0)"}

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

# ── Fetch Wikipedia ───────────────────────────────────────────────────────────
def fetch_wiki(name, nickname=None):
    """Fetch Wikipedia article text. Tries multiple name variants."""
    variants = [name]
    if nickname:
        parts = name.split()
        variants.append(f"{nickname} {parts[-1]}")
    if len(name.split()) > 2:
        parts = name.split()
        variants.append(f"{parts[0]} {parts[-1]}")

    for variant in variants:
        try:
            # Full article extract
            r = requests.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action":          "query",
                    "titles":          variant.replace(" ", "_"),
                    "prop":            "extracts",
                    "explaintext":     True,
                    "exsectionformat": "plain",
                    "exchars":         5000,
                    "format":          "json",
                },
                headers=BASE_HEADERS,
                timeout=15
            )
            if r.status_code == 200:
                pages = r.json().get("query", {}).get("pages", {})
                for page in pages.values():
                    if page.get("pageid", -1) == -1:
                        continue  # page not found
                    text = page.get("extract", "")
                    if len(text) > 300:
                        # Clean up section headers
                        text = re.sub(r'==+[^=]+=+', ' ', text)
                        text = re.sub(r'\s+', ' ', text).strip()
                        return text[:5000]
        except Exception as e:
            print(f"    Wiki error ({variant}): {e}")

    # Fallback: summary API
    for variant in variants:
        try:
            r = requests.get(
                f"https://en.wikipedia.org/api/rest_v1/page/summary/{variant.replace(' ', '_')}",
                headers=BASE_HEADERS,
                timeout=10
            )
            if r.status_code == 200:
                extract = r.json().get("extract", "")
                if len(extract) > 200:
                    return extract
        except:
            pass

    return ""

# ── Fetch Ballotpedia ─────────────────────────────────────────────────────────
def fetch_ballotpedia(name, nickname=None):
    """Fetch Ballotpedia bio text."""
    import unicodedata
    variants = [name]
    if nickname:
        parts = name.split()
        variants.append(f"{nickname} {parts[-1]}")
    if len(name.split()) > 2:
        parts = name.split()
        variants.append(f"{parts[0]} {parts[-1]}")

    for variant in variants:
        try:
            name_ascii = unicodedata.normalize('NFKD', variant).encode('ascii', 'ignore').decode('ascii')
            slug = name_ascii.replace(" ", "_")
            r = requests.get(
                f"https://ballotpedia.org/{slug}",
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                },
                timeout=15
            )
            if r.status_code != 200:
                continue

            # Extract main article body
            body_match = re.search(
                r'<div class="mw-parser-output">(.*?)<div[^>]*id="toc"',
                r.text, re.DOTALL
            )
            body = body_match.group(1) if body_match else r.text[:10000]

            # Strip HTML
            text = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', body, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\[\d+\]', '', text)
            text = re.sub(r'\s+', ' ', text).strip()

            # Remove junk
            for phrase in ['Contents', 'Navigation menu', 'Retrieved from',
                           'Jump to navigation', 'Ballotpedia features',
                           'Click here to contact', 'did not complete Ballotpedia',
                           'Candidate Connection survey', 'Personal tools']:
                idx = text.find(phrase)
                if 0 < idx < len(text) - 100:
                    text = text[:idx].strip()

            # Find member mention
            last_name = variant.split()[-1]
            idx = text.find(last_name)
            if idx < 0:
                continue

            bio_text = text[max(0, idx - 10):idx + 4000]
            sentences = re.split(r'(?<=[.!?])\s+', bio_text)
            sentences = [s.strip() for s in sentences
                         if len(s.strip()) > 40
                         and not s.startswith('[')
                         and 'Ballotpedia' not in s
                         and 'survey' not in s.lower()
                         and 'click here' not in s.lower()
                         and 'campaign finance' not in s.lower()]
            if len(sentences) >= 3:
                return " ".join(sentences[:15])
        except Exception as e:
            print(f"    BP error ({variant}): {e}")

    return ""

# ── Write bio with Claude ─────────────────────────────────────────────────────
def write_bio_with_claude(name, chamber, state, role, raw_text):
    """Use Claude to write a clean consistent 3-paragraph bio."""
    chamber_short = "Senate" if "Senate" in chamber else "House"
    state_names = {
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
    state_full = state_names.get(state, state)

    source_section = f"""Use this source material as your primary reference:
{raw_text[:4000]}

""" if raw_text else ""

    prompt = f"""Write a professional 3-paragraph biography for {name}, a U.S. {chamber_short} member from {state_full}{f' serving as {role}' if role else ''}.

{source_section}Write exactly 3 paragraphs separated by a blank line:

Paragraph 1 — Background: Where they are from, their upbringing, education, and career before entering Congress. 2-3 sentences.

Paragraph 2 — Congressional Career: When they were first elected, their key legislative work, committees they've served on, and what they are known for in Congress. 2-3 sentences.

Paragraph 3 — Current Role: Their current position and responsibilities, the policy issues they focus on, and their recent work or priorities. 2-3 sentences.

Rules:
- Write in third person throughout
- Use their last name after the first full mention
- No citation brackets like [1] or [2]
- Professional, factual, neutral tone
- Each paragraph must be 2-3 complete sentences — never just one sentence
- If source material is limited, use your knowledge of this public figure's career

Return ONLY the 3 paragraphs with a blank line between each. No headers, labels, or preamble."""

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
            if len(text) > 200:
                return text
        else:
            print(f"    Claude {r.status_code}: {r.text[:100]}")
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

# ── Institutional leadership roles ────────────────────────────────────────────
INST_ROLES = {
    "T000250": "Senate Majority Leader",
    "G000386": "President Pro Tempore of the Senate",
    "B001261": "Senate Majority Whip",
    "S000148": "Senate Minority Leader",
    "D000563": "Senate Minority Whip",
    "J000299": "Speaker of the House",
    "S001176": "House Majority Leader",
    "E000294": "House Majority Whip",
    "J000294": "House Minority Leader",
    "C001101": "House Minority Whip",
    "A000371": "House Democratic Caucus Chair",
    "N000191": "Assistant Democratic Leader",
    "C001095": "Senate Republican Conference Chair",
    "M001136": "House Republican Conference Chair",
}

# ── Main loop ─────────────────────────────────────────────────────────────────
total      = len(legislators)
processed  = 0
skipped    = 0
no_source  = 0

for i, m in enumerate(legislators):
    bid  = m.get("id", {}).get("bioguide", "")
    name = m.get("name", {}).get("official_full", "")
    nick = m.get("name", {}).get("nickname", "")
    if not bid or not name:
        continue

    if bid in bios and len(bios[bid]) > 400 and bios[bid].count('\n\n') >= 1:
        # Already has a proper multi-paragraph bio — skip
        skipped += 1
        continue

    term    = m.get("terms", [{}])[-1]
    chamber = "United States Senate" if term.get("type") == "sen" else "United States House of Representatives"
    state   = term.get("state", "")
    role    = INST_ROLES.get(bid, "")

    print(f"[{i+1}/{total}] {name} ({bid})...", end=" ", flush=True)

    # Try Wikipedia first, then Ballotpedia
    raw = fetch_wiki(name, nick)
    source = "Wikipedia"
    if not raw:
        raw = fetch_ballotpedia(name, nick)
        source = "Ballotpedia"

    if not raw:
        print("❌ no source")
        bios[bid] = f"{name} is a member of the {chamber} from {state}."
        no_source += 1
    else:
        bio = write_bio_with_claude(name, chamber, state, role, raw)
        if bio:
            bios[bid] = bio
            processed += 1
            print(f"✓ {source} ({len(bio)} chars)")
        else:
            # Use first 3 sentences of raw as fallback
            sentences = re.split(r'(?<=[.!?])\s+', re.sub(r'\[\d+\]', '', raw))
            sentences = [s.strip() for s in sentences if len(s.strip()) > 30]
            bios[bid] = " ".join(sentences[:4])
            processed += 1
            print(f"✓ {source} raw fallback")

    # Save every 10 members
    if (i + 1) % 10 == 0:
        save_bios()
        print(f"  💾 Saved {len(bios)}/{total} bios")

    time.sleep(0.4)

save_bios()
print(f"\n✅ Done: {processed} written, {skipped} skipped, {no_source} no source")
print(f"📄 Output: {OUTPUT_FILE}")
