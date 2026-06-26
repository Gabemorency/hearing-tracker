"""
Congressional Member Directory Builder
Runs nightly via GitHub Actions.
Sources:
  - raw.githubusercontent.com/unitedstates/congress-legislators (YAML)
  - bioguide.congress.gov for photos
Outputs: members.json + members.html
"""

import json
import re
import sys
from datetime import datetime, timezone, timedelta

try:
    import requests
    import yaml
except ImportError:
    print("Installing dependencies...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                          "requests", "pyyaml", "--break-system-packages", "-q"])
    import requests
    import yaml

# ── Auto DST timezone ──────────────────────────────────────────────────────────
def get_et_offset():
    now_utc = datetime.now(timezone.utc)
    year = now_utc.year
    def nth_sunday(month, n):
        d = datetime(year, month, 1, tzinfo=timezone.utc)
        days_to_sun = (6 - d.weekday()) % 7
        return (d + timedelta(days=days_to_sun + 7*(n-1))).replace(hour=7)
    dst_start = nth_sunday(3, 2)
    dst_end   = nth_sunday(11, 1)
    return timedelta(hours=-4) if dst_start <= now_utc < dst_end else timedelta(hours=-5)

ET_OFFSET  = get_et_offset()
now_et     = datetime.now(timezone.utc) + ET_OFFSET
today_str  = now_et.strftime("%B %-d, %Y")
today_long = now_et.strftime("%A, %B %-d, %Y")
today_iso  = now_et.strftime("%Y-%m-%d")
generated  = now_et.strftime("%-I:%M %p ET")

BASE = "https://raw.githubusercontent.com/unitedstates/congress-legislators/main"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; hearing-tracker-bot/1.0)"}

# ── Current House vacancies (119th Congress) ───────────────────────────────────
# Updated by validate_hardcoded.py every 3 days — check GitHub Issues for alerts
VACANT_SEATS = [
    {
        "state": "CA", "district": 1,
        "label": "California's 1st Congressional District",
        "reason": "Rep. Doug LaMalfa (R) died January 6, 2026.",
        "election": "Special election: August 4, 2026 (primary June 2, 2026)",
        "party": "rep",
    },
    {
        "state": "CA", "district": 14,
        "label": "California's 14th Congressional District",
        "reason": "Rep. Eric Swalwell (D) resigned April 14, 2026.",
        "election": "Special election: August 18, 2026 (primary June 16, 2026)",
        "party": "dem",
    },
    {
        "state": "FL", "district": 20,
        "label": "Florida's 20th Congressional District",
        "reason": "Rep. Sheila Cherfilus-McCormick (D) resigned April 21, 2026.",
        "election": "Special election date to be determined.",
        "party": "dem",
    },
    {
        "state": "GA", "district": 13,
        "label": "Georgia's 13th Congressional District",
        "reason": "Rep. David Scott (D) died April 22, 2026.",
        "election": "Special election date to be determined.",
        "party": "dem",
    },
    {
        "state": "TX", "district": 23,
        "label": "Texas's 23rd Congressional District",
        "reason": "Rep. Tony Gonzales (R) resigned April 14, 2026.",
        "election": "Special election date to be determined.",
        "party": "rep",
    },
]

# ── 119th Congress institutional leadership (hardcoded by bioguide ID) ─────────
INSTITUTIONAL_LEADERSHIP = {
    # Senate Republican
    "T000250": {"label": "Senate Majority Leader",          "tier": 1},  # John Thune
    "G000386": {"label": "President Pro Tempore",           "tier": 1},  # Chuck Grassley
    "B001261": {"label": "Senate Majority Whip",            "tier": 2},  # John Barrasso
    "C001095": {"label": "Senate Conference Chair",         "tier": 3},  # Tom Cotton
    "L000575": {"label": "Senate Conference Vice Chair",    "tier": 3},  # James Lankford
    "C001047": {"label": "Senate Policy Committee Chair",   "tier": 3},  # Shelley Moore Capito
    # Senate Democratic
    "S000148": {"label": "Senate Minority Leader",          "tier": 1},  # Chuck Schumer
    "D000563": {"label": "Senate Minority Whip",            "tier": 2},  # Dick Durbin
    "K000367": {"label": "Steering & Policy Chair",         "tier": 3},  # Amy Klobuchar
    "B001288": {"label": "Strategic Communications Chair",  "tier": 3},  # Cory Booker
    # House Republican
    "J000299": {"label": "Speaker of the House",            "tier": 1},  # Mike Johnson
    "S001176": {"label": "House Majority Leader",           "tier": 1},  # Steve Scalise
    "E000294": {"label": "House Majority Whip",             "tier": 2},  # Tom Emmer
    "M001136": {"label": "House Conference Chair",          "tier": 3},  # Lisa McClain
    # House Democratic
    "J000294": {"label": "House Minority Leader",           "tier": 1},  # Hakeem Jeffries
    "C001101": {"label": "House Minority Whip",             "tier": 2},  # Katherine Clark
    "A000371": {"label": "House Democratic Caucus Chair",   "tier": 3},  # Pete Aguilar
    "N000191": {"label": "Asst. Democratic Leader",         "tier": 3},  # Joe Neguse
}

def fetch_yaml(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return yaml.safe_load(r.text)

def photo_url(bioguide_id):
    if not bioguide_id:
        return ""
    return f"https://bioguide.congress.gov/bioguide/photo/{bioguide_id[0].upper()}/{bioguide_id}.jpg"

def initials(name):
    parts = name.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return name[:2].upper() if name else "?"

def party_label(p):
    return {"Republican": "R", "Democrat": "D", "Independent": "I"}.get(p, p[0] if p else "?")

def party_class(p):
    return {"Republican": "rep", "Democrat": "dem", "Independent": "ind"}.get(p, "ind")

# Leadership title → (display label, tier)
LEADERSHIP_MAP = {
    "speaker of the house":          ("Speaker", 1),
    "majority leader":               ("Majority Leader", 1),
    "minority leader":               ("Minority Leader", 1),
    "president pro tempore":         ("President Pro Tempore", 1),
    "majority whip":                 ("Majority Whip", 2),
    "minority whip":                 ("Minority Whip", 2),
    "assistant majority leader":     ("Asst. Majority Leader", 2),
    "assistant minority leader":     ("Asst. Minority Leader", 2),
    "majority conference chair":     ("Conference Chair", 3),
    "minority conference chair":     ("Conference Chair", 3),
    "majority caucus chair":         ("Caucus Chair", 3),
    "minority caucus chair":         ("Caucus Chair", 3),
    "majority policy chair":         ("Policy Chair", 3),
    "minority policy chair":         ("Policy Chair", 3),
}

def get_leadership(title):
    if not title:
        return None
    tl = title.lower()
    for key, val in LEADERSHIP_MAP.items():
        if key in tl:
            return {"label": val[0], "tier": val[1]}
    return None

def build():
    print("📥 Fetching legislators-current.yaml...")
    legislators = fetch_yaml(f"{BASE}/legislators-current.yaml")
    print(f"  {len(legislators)} members loaded")

    print("📥 Fetching committee-membership-current.yaml...")
    cmte_membership = fetch_yaml(f"{BASE}/committee-membership-current.yaml")
    print(f"  {len(cmte_membership)} committees loaded")

    print("📥 Fetching committees-current.yaml for names...")
    committees_info = fetch_yaml(f"{BASE}/committees-current.yaml")
    # Build thomas_id -> name map
    cmte_names = {}
    for c in committees_info:
        tid = c.get("thomas_id", "")
        if tid:
            cmte_names[tid] = c.get("name", tid)
        for sub in c.get("subcommittees", []):
            sub_tid = tid + sub.get("thomas_id", "")
            cmte_names[sub_tid] = f"{c.get('name',tid)} — {sub.get('name','')}"

    # Build bioguide -> committee roles
    # Only count FULL committee chairs/RMs (not subcommittee chairs)
    # thomas_ids with no suffix = full committee; with suffix = subcommittee
    print("🔗 Building committee role map...")
    cmte_roles_map = {}
    chair_map      = {}
    for thomas_id, members in cmte_membership.items():
        cmte_name     = cmte_names.get(thomas_id, thomas_id)
        is_full_cmte  = len(thomas_id) <= 4  # full committee IDs are 4 chars or fewer
        for m in members:
            bid   = m.get("bioguide", "")
            title = m.get("title", "")
            rank  = m.get("rank", 99)
            if not bid:
                continue
            if bid not in cmte_roles_map:
                cmte_roles_map[bid] = []
            role = title if title else "Member"
            cmte_roles_map[bid].append({
                "committee": cmte_name,
                "role":      role,
                "rank":      rank,
            })
            # Only set chair/RM leadership badge for FULL committee chairs/RMs
            tl = title.lower() if title else ""
            if is_full_cmte:
                if "chair" in tl and "ranking" not in tl:
                    if bid not in chair_map:
                        chair_map[bid] = {"label": "Chair", "tier": 4, "committee": cmte_name}
                elif "ranking" in tl:
                    if bid not in chair_map:
                        chair_map[bid] = {"label": "Ranking Member", "tier": 5, "committee": cmte_name}
            else:
                # Subcommittee chairs/RMs — tiers 6 and 7
                # Only assign if member doesn't already have a full committee role
                if "chair" in tl and "ranking" not in tl:
                    if bid not in chair_map:
                        chair_map[bid] = {"label": "Subcmte. Chair", "tier": 6, "committee": cmte_name}
                elif "ranking" in tl:
                    if bid not in chair_map:
                        chair_map[bid] = {"label": "Subcmte. Ranking Member", "tier": 7, "committee": cmte_name}

    # ── Congressional Black Caucus membership ─────────────────────────────────
    # CBC page requires JavaScript to render — using bioguide IDs matched from
    # the static HTML that does load, cross-referenced with the legislators dataset.
    # CBC members — bioguide IDs matched directly from cbc.house.gov/membership/
    # As of June 2026: 61 active members
    # (Cherfilus-McCormick resigned Apr 2026, David Scott GA-13 deceased, Sylvester Turner TX-18 deceased)
    print("📋 Loading CBC membership...")
    CBC_BIOGUIDES = [
        "N000147",  # Eleanor Holmes Norton (DC)
        "W000187",  # Maxine Waters (CA)
        "B000490",  # Sanford D. Bishop, Jr. (GA)
        "C000537",  # James E. Clyburn (SC)
        "S000185",  # Robert C. Bobby Scott (VA)
        "T000193",  # Bennie G. Thompson (MS)
        "D000096",  # Danny K. Davis (IL)
        "M001137",  # Gregory W. Meeks (NY)
        "C001061",  # Emanuel Cleaver (MO)
        "G000553",  # Al Green (TX)
        "M001160",  # Gwen Moore (WI)
        "C001067",  # Yvette D. Clarke (NY) - CBC Chair
        "J000288",  # Henry C. Hank Johnson Jr (GA)
        "C001072",  # Andre Carson (IN)
        "M000687",  # Kweisi Mfume (MD)
        "S001185",  # Terri A. Sewell (AL)
        "W000808",  # Frederica S. Wilson (FL)
        "B001281",  # Joyce Beatty (OH)
        "J000294",  # Hakeem S. Jeffries (NY)
        "V000131",  # Marc A. Veasey (TX)
        "K000385",  # Robin L. Kelly (IL)
        "B001288",  # Cory A. Booker (NJ)
        "A000370",  # Alma S. Adams (NC)
        "P000610",  # Stacey E. Plaskett (VI)
        "W000822",  # Bonnie Watson Coleman (NJ)
        "E000296",  # Dwight Evans (PA)
        "B001303",  # Lisa Blunt Rochester (DE)
        "H001066",  # Steven Horsford (NV)
        "H001081",  # Jahana Hayes (CT)
        "M001208",  # Lucy McBath (GA)
        "N000191",  # Joe Neguse (CO)
        "O000173",  # Ilhan Omar (MN)
        "P000617",  # Ayanna Pressley (MA)
        "U000040",  # Lauren Underwood (IL)
        "W000788",  # Nikema Williams (GA)
        "T000486",  # Ritchie Torres (NY)
        "S001159",  # Marilyn Strickland (WA)
        "W000790",  # Raphael G. Warnock (GA)
        "C001125",  # Troy A. Carter (LA)
        "B001313",  # Shontel M. Brown (OH)
        "C001130",  # Jasmine Crockett (TX)
        "D000230",  # Donald G. Davis (NC)
        "F000477",  # Valerie P. Foushee (NC)
        "F000476",  # Maxwell Frost (FL)
        "I000058",  # Glenn Ivey (MD)
        "J000309",  # Jonathan L. Jackson (IL)
        "K000400",  # Sydney Kamlager-Dove (CA)
        "L000602",  # Summer L. Lee (PA)
        "S001223",  # Emilia Strong Sykes (OH)
        "M001227",  # Jennifer L. McClellan (VA)
        "A000380",  # Gabe Amo (RI)
        "M001229",  # LaMonica McIver (NJ)
        "A000382",  # Angela D. Alsobrooks (MD)
        "B001324",  # Wesley Bell (MO)
        "B001326",  # Janelle S. Bynum (OR)
        "C001136",  # Herbert C. Conaway Jr (NJ)
        "F000110",  # Cleo Fields (LA)
        "F000481",  # Shomari Figures (AL)
        "S001231",  # Lateefah Simon (CA)
        "M001245",  # Christian D. Menefee (TX)
    ]

    caucus_map = {}
    for bid in CBC_BIOGUIDES:
        caucus_map[bid] = ["cbc"]
    print(f"  Black Caucus: {len(CBC_BIOGUIDES)} members loaded")

    # ── Hardcoded 119th Congress institutional leadership ──────────────────────
    # These positions change only after elections or resignations.
    # Bioguide IDs are stable and authoritative.
    # Tiers: 1 = top leaders, 2 = whips, 3 = conference/caucus/policy chairs
    pass  # INSTITUTIONAL_LEADERSHIP defined at module level

    # ── Wikipedia bios ─────────────────────────────────────────────────────────
    print("📥 Fetching Wikipedia bios...")
    wiki_bios = {}

    def fetch_wiki_bio(name):
        """Fetch a short bio extract from Wikipedia API."""
        try:
            r = requests.get(
                "https://en.wikipedia.org/api/rest_v1/page/summary/" +
                name.replace(" ", "_"),
                headers=HEADERS, timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                extract = data.get("extract", "")
                # Take first 2 sentences max
                sentences = re.split(r'(?<=[.!?])\s+', extract)
                return " ".join(sentences[:2]).strip()
        except:
            pass
        return ""

    # Build member objects
    print("🔨 Building member objects...")
    senators = []
    reps     = []

    for m in legislators:
        terms = m.get("terms", [])
        if not terms:
            continue
        term  = terms[-1]
        name  = m.get("name", {})
        ids   = m.get("id", {})

        bioguide_id = ids.get("bioguide", "")
        full_name   = name.get("official_full", "") or \
                      f"{name.get('first','')} {name.get('last','')}".strip()
        first = name.get("first", "")
        last  = name.get("last", "")

        chamber  = "senate" if term.get("type") == "sen" else "house"
        state    = term.get("state", "")
        party    = term.get("party", "")
        district = term.get("district", "")

        # Non-voting delegates represent territories, not states
        TERRITORIES = {"DC", "PR", "VI", "GU", "AS", "MP"}
        is_delegate = chamber == "house" and state in TERRITORIES

        # Leadership: institutional leaders first (hardcoded, most reliable)
        # then fall back to term title, then committee chair_map
        if bioguide_id in INSTITUTIONAL_LEADERSHIP:
            leadership = INSTITUTIONAL_LEADERSHIP[bioguide_id]
        else:
            leadership_title = term.get("leadership_title", "")
            leadership = get_leadership(leadership_title)
            if not leadership and bioguide_id in chair_map:
                leadership = chair_map[bioguide_id]

        member = {
            "bioguide_id": bioguide_id,
            "name":        full_name,
            "first":       first,
            "last":        last,
            "chamber":     chamber,
            "state":       state,
            "party":       party,
            "party_short": party_label(party),
            "party_class": party_class(party),
            "district":    district,
            "photo_url":   photo_url(bioguide_id),
            "initials":    initials(full_name),
            "leadership":  leadership,
            "committees":  cmte_roles_map.get(bioguide_id, []),
            "caucuses":    caucus_map.get(bioguide_id, []),
            "delegate":    is_delegate,
            "bio":         "",  # filled in below
        }

        if chamber == "senate":
            senators.append(member)
        else:
            reps.append(member)

    # Sort
    def sort_key(m):
        tier = m["leadership"]["tier"] if m["leadership"] else 99
        return (tier, m["last"])
    senators.sort(key=sort_key)
    reps.sort(key=sort_key)

    # Fetch Wikipedia bios (rate limited — fetch top leaders + chairs first, sample rest)
    print("📖 Fetching Wikipedia bios...")
    all_members = senators + reps
    # Prioritize leadership and chairs, then sample remaining
    priority = [m for m in all_members if m["leadership"]]
    remaining = [m for m in all_members if not m["leadership"]]
    to_fetch = priority + remaining  # fetch all, Wikipedia API is fast

    # ── Bio fetching: Ballotpedia (primary) → Wikipedia (fallback) ───────────
    print("📖 Fetching member bios (Ballotpedia → Wikipedia)...")

    import time, os
    from playwright.async_api import async_playwright as _apw
    os.makedirs("bios", exist_ok=True)

    def fetch_ballotpedia_bio_requests(name):
        """Fetch Ballotpedia bio using requests — fast, works for most members."""
        try:
            slug = name.replace(" ", "_")
            r = requests.get(
                f"https://ballotpedia.org/{slug}",
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
                timeout=15
            )
            if r.status_code != 200:
                return "", ""
            import re as _re
            # Remove scripts, styles, nav elements
            text = _re.sub(r'<(script|style|nav|header|footer)[^>]*>.*?</\1>', ' ', r.text, flags=_re.DOTALL|_re.IGNORECASE)
            text = _re.sub(r'<[^>]+>', ' ', text)
            text = _re.sub(r'\s+', ' ', text).strip()
            # Find the intro paragraph — Ballotpedia always starts with the member's name
            parts = name.split()
            last = parts[-1] if parts else ""
            idx = text.find(last)
            if idx < 0:
                return "", ""
            # Extract a generous chunk and clean it
            chunk = text[max(0, idx-20):idx+2000]
            # Remove nav/edit artifacts
            chunk = _re.sub(r'(Contents|Navigation menu|Categories|Retrieved from|Jump to).*', '', chunk)
            sentences = _re.split(r'(?<=[.!?])\s+', chunk)
            sentences = [s.strip() for s in sentences if len(s.strip()) > 30 and not s.strip().startswith('[')]
            if len(sentences) >= 3:
                return " ".join(sentences[:12]), "Ballotpedia"
        except:
            pass
        return "", ""

    def fetch_wiki_bio_full(name):
        """Fetch Wikipedia extract as fallback."""
        try:
            r = requests.get(
                "https://en.wikipedia.org/api/rest_v1/page/summary/" +
                name.replace(" ", "_"),
                headers=HEADERS, timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                extract = data.get("extract", "")
                if len(extract) > 300:
                    return extract, "Wikipedia"
        except:
            pass
        return "", ""

    def rewrite_bio_with_claude(raw_text, member_name, role, state, chamber):
        """
        Use Claude API to rewrite raw scraped text into 3 clean,
        consistent, typo-free paragraphs about the member.
        """
        try:
            prompt = f"""You are writing a professional congressional biography for {member_name}, 
a {role if role else "member"} of the {chamber} from {state}.

Here is the raw source text about them:

{raw_text[:3000]}

Rewrite this into exactly 3 clean paragraphs with NO typos, NO repetition, and consistent professional tone:
- Paragraph 1: Background — where they are from, education, career before Congress
- Paragraph 2: Congressional career — when first elected, key legislation or moments, committees, what they are known for  
- Paragraph 3: Current role — what they focus on now, their position and influence, key issues they champion

Rules:
- Write in third person
- Do not use their first name alone — always use full name or last name
- Do not include Wikipedia-style citation brackets like [1] [2]
- Do not mention the source (Ballotpedia/Wikipedia)
- Each paragraph should be 3-5 sentences
- Be specific and informative, not generic
- If information is missing, do not fabricate — just omit it

Return ONLY the 3 paragraphs separated by a blank line. No headers, no labels, no preamble."""

            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={"Content-Type": "application/json"},
                json={{
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 600,
                    "messages": [{{"role": "user", "content": prompt}}]
                }},
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                text = data.get("content", [{{}}])[0].get("text", "").strip()
                if text and len(text) > 200:
                    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
                    return paragraphs[:3]
        except Exception as e:
            print(f"    Claude API error for {member_name}: {{e}}")
        return []

    all_members = senators + reps
    fetched_count = 0

    for m in all_members:
        # Try Ballotpedia first
        bio_text, bio_source = fetch_ballotpedia_bio_requests(m["name"])

        # Fall back to Wikipedia
        if not bio_text:
            bio_text, bio_source = fetch_wiki_bio_full(m["name"])

        slug = re.sub(r"[^a-z0-9]+", "-", m["name"].lower()).strip("-")
        m["bio_slug"] = slug

        if bio_text:
            # Rewrite with Claude for clean consistent paragraphs
            role_label = m["leadership"]["label"] if m.get("leadership") else ""
            state_name = m["state"]
            chamber_label = "United States Senate" if m["chamber"] == "senate" else "United States House of Representatives"

            paragraphs = rewrite_bio_with_claude(bio_text, m["name"], role_label, state_name, chamber_label)

            if not paragraphs:
                # Fallback: split raw text into paragraphs without Claude
                import re as _re
                sentences = _re.split(r'(?<=[.!?])\s+', bio_text.strip())
                sentences = [s for s in sentences if len(s) > 30]
                third = max(1, len(sentences)//3)
                paragraphs = [
                    " ".join(sentences[:third]),
                    " ".join(sentences[third:2*third]),
                    " ".join(sentences[2*third:3*third]),
                ]
                paragraphs = [p for p in paragraphs if p]

            # Short bio for modal (first 2 sentences of para 1)
            if paragraphs:
                import re as _re
                first_para_sentences = _re.split(r'(?<=[.!?])\s+', paragraphs[0])
                m["bio"] = " ".join(first_para_sentences[:2]).strip()
            else:
                m["bio"] = ""

            m["bio_source"] = bio_source

            # Generate bio page
            bio_html = build_bio_page(m, paragraphs, bio_source)
            with open(f"bios/{slug}.html", "w", encoding="utf-8") as f:
                f.write(bio_html)
            fetched_count += 1
        else:
            m["bio"] = ""
            m["bio_source"] = ""

        time.sleep(0.1)  # Respectful rate limiting

    print(f"  Bios generated: {fetched_count}/{len(all_members)}")

    print(f"✅ {len(senators)} senators, {len(reps)} representatives")
    print(f"  Senate leaders/chairs: {sum(1 for m in senators if m['leadership'])}")
    print(f"  House leaders/chairs:  {sum(1 for m in reps if m['leadership'])}")

    members_data = {
        "date":      today_iso,
        "generated": generated,
        "senators":  senators,
        "reps":      reps,
        "vacancies": VACANT_SEATS,
    }

    with open("members.json", "w", encoding="utf-8") as f:
        json.dump(members_data, f, indent=2, ensure_ascii=False)
    print("✅ members.json written")

    members_json = json.dumps(members_data, ensure_ascii=False)
    with open("members.html", "w", encoding="utf-8") as f:
        f.write(build_html(members_json))
    print("✅ members.html written")

def build_bio_page(m, paragraphs, source):
    """Generate a full biography page for a single member."""
    pc         = m["party_class"]
    party_full = {"rep":"Republican","dem":"Democrat","ind":"Independent"}.get(pc, "Independent")
    chamber_full = "United States Senate" if m["chamber"]=="senate" else "United States House of Representatives"
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
    state_full = state_names.get(m["state"], m["state"])
    dist_str   = f"District {m['district']} · " if m.get("district") and m["chamber"]=="house" else ""
    role_str   = m["leadership"]["label"] if m.get("leadership") else ""
    bio_photo  = m.get("photo_url", "")
    init_color = "180,60,60" if pc=="rep" else "50,100,160" if pc=="dem" else "100,50,160"

    para_html = ""
    for p in (paragraphs or []):
        if p and p.strip():
            para_html += f'<p class="bio-para">{p.strip()}</p>'

    if not para_html:
        para_html = '<p class="bio-para" style="font-style:italic;opacity:0.5">Biography not yet available.</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{m["name"]} — Congressional Hearing Tracker</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;700&family=IBM+Plex+Sans:wght@300;400;600;700&family=Playfair+Display:wght@700&display=swap" rel="stylesheet">
<style>
  /* ── CSS variables — dark default ── */
  :root {{
    --bg:#0D0C0A; --bg2:#111009; --text:#F0E8D8; --text2:#C8B89A;
    --muted:#A09070; --dim:#807050; --faint:#504030;
    --gold:#E0B870; --border:rgba(255,255,255,0.08);
    --header-bg:rgba(200,169,110,0.03); --header-border:rgba(200,169,110,0.2);
    --tog-bg:rgba(255,255,255,0.08); --tog-border:rgba(255,255,255,0.16);
  }}
  :root.light {{
    --bg:#F5F3EE; --bg2:#EAE7DF; --text:#0E0C0A; --text2:#3A3020;
    --muted:#5A4A35; --dim:#7A6A55; --faint:#A09080;
    --gold:#B8860B; --border:rgba(0,0,0,0.08);
    --header-bg:rgba(200,169,110,0.06); --header-border:rgba(180,130,50,0.3);
    --tog-bg:rgba(0,0,0,0.05); --tog-border:rgba(0,0,0,0.12);
  }}
  @media(prefers-color-scheme:light){{:root:not(.dark){{
    --bg:#F5F3EE; --bg2:#EAE7DF; --text:#0E0C0A; --text2:#3A3020;
    --muted:#5A4A35; --dim:#7A6A55; --faint:#A09080;
    --gold:#B8860B; --border:rgba(0,0,0,0.08);
    --header-bg:rgba(200,169,110,0.06); --header-border:rgba(180,130,50,0.3);
    --tog-bg:rgba(0,0,0,0.05); --tog-border:rgba(0,0,0,0.12);
  }}}}
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:var(--bg);color:var(--text);font-family:'IBM Plex Sans',sans-serif;min-height:100vh;transition:background 0.2s,color 0.2s}}
  /* ── Header ── */
  .header{{
    padding:16px 20px;
    border-bottom:1px solid var(--header-border);
    background:var(--header-bg);
    display:flex;justify-content:space-between;align-items:center;
  }}
  .nav{{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:0.08em;color:var(--muted)}}
  .nav a{{color:var(--gold);text-decoration:none}}
  .nav a:hover{{text-decoration:underline}}
  .toggle{{
    background:var(--tog-bg);border:1px solid var(--tog-border);
    border-radius:8px;padding:6px 10px;cursor:pointer;
    font-size:15px;line-height:1;transition:background 0.15s;
  }}
  /* ── Content ── */
  .content{{max-width:680px;margin:0 auto;padding:32px 20px 60px}}
  /* ── Hero ── */
  .hero{{display:flex;gap:24px;align-items:flex-start;margin-bottom:40px;flex-wrap:wrap}}
  .hero-photo{{
    width:160px;height:200px;border-radius:12px;
    object-fit:cover;object-position:top;
    border:2px solid var(--gold);
    flex-shrink:0;background:var(--bg2);
  }}
  .hero-initials{{
    width:160px;height:200px;border-radius:12px;
    display:none;align-items:center;justify-content:center;
    font-family:'Playfair Display',serif;font-size:52px;font-weight:700;
    color:white;flex-shrink:0;
    background:rgba({init_color},0.7);
  }}
  .hero-info{{flex:1;min-width:200px;padding-top:4px}}
  .member-name{{
    font-family:'Playfair Display',serif;
    font-size:clamp(22px,4vw,30px);font-weight:700;
    line-height:1.2;margin-bottom:10px;color:var(--text);
  }}
  .member-sub{{
    font-family:'IBM Plex Mono',monospace;font-size:11px;
    color:var(--muted);letter-spacing:0.05em;line-height:1.9;
  }}
  .role-badge{{
    display:inline-block;font-family:'IBM Plex Mono',monospace;
    font-size:10px;font-weight:700;letter-spacing:0.08em;
    padding:3px 9px;border-radius:4px;text-transform:uppercase;
    margin-top:10px;background:rgba(224,184,112,0.15);
    color:var(--gold);border:1px solid rgba(224,184,112,0.35);
  }}
  /* ── Bio section ── */
  .section-label{{
    font-family:'IBM Plex Mono',monospace;font-size:10px;
    letter-spacing:0.14em;text-transform:uppercase;
    color:var(--dim);margin-bottom:16px;
    padding-bottom:8px;border-bottom:1px solid var(--border);
    display:flex;align-items:center;gap:8px;
  }}
  .section-label::after{{content:'';flex:1;height:1px;background:var(--border);}}
  .bio-section{{margin-bottom:40px}}
  .bio-para{{
    font-size:16px;line-height:1.85;
    color:var(--text2);margin-bottom:22px;
  }}
  /* ── Back button ── */
  .back-btn{{
    display:inline-block;font-family:'IBM Plex Mono',monospace;
    font-size:11px;letter-spacing:0.08em;padding:9px 18px;
    border:1px solid rgba(200,169,110,0.3);border-radius:6px;
    color:var(--gold);text-decoration:none;margin-top:8px;
    transition:all 0.2s;background:transparent;
  }}
  .back-btn:hover{{background:rgba(200,169,110,0.1);}}
  /* ── Source note ── */
  .source-note{{
    font-family:'IBM Plex Mono',monospace;font-size:10px;
    color:var(--faint);margin-top:48px;padding-top:16px;
    border-top:1px solid var(--border);
  }}
</style>
</head>
<body>
<div class="header">
  <div class="nav">
    <a href="../index.html">🏛 Hearings</a> &nbsp;·&nbsp;
    <a href="../members.html">Members</a> &nbsp;·&nbsp;
    <span>{m["name"]}</span>
  </div>
  <button class="toggle" id="tog" onclick="toggleTheme()">☀️</button>
</div>
<div class="content">
  <div class="hero">
    {"" if not bio_photo else f'<img class="hero-photo" src="{bio_photo}" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\';" alt="{m["name"]}">'}
    <div class="hero-initials" id="initials" {"style=\'display:flex\'" if not bio_photo else ""}>{m["initials"]}</div>
    <div class="hero-info">
      <div class="member-name">{m["name"]}</div>
      <div class="member-sub">
        {chamber_full}<br>
        {dist_str}{state_full} · {party_full}
      </div>
      {f'<div class="role-badge">{role_str}</div>' if role_str else ''}
    </div>
  </div>

  <div class="bio-section">
    <div class="section-label">Biography</div>
    {para_html}
  </div>

  <a href="../members.html" class="back-btn">← Back to Directory</a>

  <div class="source-note">
    Source: {source or "Not available"} · Data: unitedstates/congress-legislators · Photos: bioguide.congress.gov
  </div>
</div>
<script>
function sysTheme(){{ return matchMedia('(prefers-color-scheme:light)').matches?'light':'dark'; }}
function applyTheme(t){{
  document.documentElement.classList.remove('light','dark');
  document.documentElement.classList.add(t);
  document.getElementById('tog').textContent = t==='dark'?'☀️':'🌙';
}}
function toggleTheme(){{
  const n = document.documentElement.classList.contains('light')?'dark':'light';
  localStorage.setItem('theme',n); applyTheme(n);
}}
(function(){{ applyTheme(localStorage.getItem('theme')||sysTheme()); }})();
matchMedia('(prefers-color-scheme:light)').addEventListener('change',e=>{{
  if(!localStorage.getItem('theme')) applyTheme(e.matches?'light':'dark');
}});
</script>
</body>
</html>"""

def build_html(members_json):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Congressional Directory — {today_str}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;700&family=IBM+Plex+Sans:wght@300;400;600;700&family=Playfair+Display:wght@700&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg:#0D0C0A;--bg-sec:#111009;--bg-card:rgba(255,255,255,0.03);--bg-card-h:rgba(255,255,255,0.06);
    --bg-hdr:rgba(200,169,110,0.04);--text:#F0E8D8;--text-h:#FAF4EA;--text-s:#C8B89A;
    --text-m:#A09070;--text-d:#807050;--text-f:#504030;
    --bdr:rgba(255,255,255,0.1);--bdr-h:rgba(200,169,110,0.3);--bdr-s:rgba(255,255,255,0.07);
    --bdr-sec:rgba(255,255,255,0.08);--scroll:#2A2820;
    --gold:#E0B870;--blue:#6BB8E8;--purple:#C4A0F0;
    --rep:#FF6B6B;--dem:#5BA8E8;--ind:#C4A0F0;
    --rep-bg:rgba(255,80,80,0.15);--dem-bg:rgba(60,140,220,0.15);--ind-bg:rgba(160,100,220,0.15);
    --rep-br:rgba(255,80,80,0.45);--dem-br:rgba(60,140,220,0.45);--ind-br:rgba(160,100,220,0.45);
    --tog-bg:rgba(255,255,255,0.08);--tog-br:rgba(255,255,255,0.16);
  }}
  :root.light {{
    --bg:#F5F3EE;--bg-sec:#EAE7DF;--bg-card:rgba(255,255,255,0.85);--bg-card-h:rgba(255,255,255,1);
    --bg-hdr:rgba(200,169,110,0.08);--text:#0E0C0A;--text-h:#050403;--text-s:#3A3020;
    --text-m:#5A4A35;--text-d:#7A6A55;--text-f:#A09080;
    --bdr:rgba(0,0,0,0.12);--bdr-h:rgba(180,130,50,0.4);--bdr-s:rgba(0,0,0,0.08);
    --bdr-sec:rgba(0,0,0,0.08);--scroll:#C8BFB0;
    --gold:#B8860B;--blue:#1A6AAA;--purple:#6040A0;
    --rep:#CC2020;--dem:#1A60A0;--ind:#6040A0;
    --rep-bg:rgba(180,30,30,0.1);--dem-bg:rgba(20,90,160,0.1);--ind-bg:rgba(80,40,140,0.1);
    --rep-br:rgba(180,30,30,0.35);--dem-br:rgba(20,90,160,0.35);--ind-br:rgba(80,40,140,0.35);
    --tog-bg:rgba(0,0,0,0.06);--tog-br:rgba(0,0,0,0.15);
  }}
  @media(prefers-color-scheme:light){{:root:not(.dark){{
    --bg:#F5F3EE;--bg-sec:#EAE7DF;--bg-card:rgba(255,255,255,0.85);--bg-card-h:rgba(255,255,255,1);
    --bg-hdr:rgba(200,169,110,0.08);--text:#0E0C0A;--text-h:#050403;--text-s:#3A3020;
    --text-m:#5A4A35;--text-d:#7A6A55;--text-f:#A09080;
    --bdr:rgba(0,0,0,0.12);--bdr-h:rgba(180,130,50,0.4);--bdr-s:rgba(0,0,0,0.08);
    --bdr-sec:rgba(0,0,0,0.08);--scroll:#C8BFB0;
    --gold:#B8860B;--blue:#1A6AAA;--purple:#6040A0;
    --rep:#CC2020;--dem:#1A60A0;--ind:#6040A0;
    --rep-bg:rgba(180,30,30,0.1);--dem-bg:rgba(20,90,160,0.1);--ind-bg:rgba(80,40,140,0.1);
    --rep-br:rgba(180,30,30,0.35);--dem-br:rgba(20,90,160,0.35);--ind-br:rgba(80,40,140,0.35);
    --tog-bg:rgba(0,0,0,0.06);--tog-br:rgba(0,0,0,0.15);
  }}}}

  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:var(--bg);color:var(--text);font-family:'IBM Plex Sans',sans-serif;min-height:100vh;transition:background 0.2s,color 0.2s}}
  ::-webkit-scrollbar{{width:4px}}::-webkit-scrollbar-thumb{{background:var(--scroll);border-radius:2px}}

  /* Header */
  .header{{border-bottom:1px solid var(--bdr-h);padding:20px 20px 0;background:var(--bg-hdr)}}
  .header-top{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px}}
  .eyebrow{{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:0.18em;color:var(--gold);text-transform:uppercase;margin-bottom:6px}}
  h1{{font-family:'Playfair Display',serif;font-size:clamp(20px,5vw,26px);font-weight:700;color:var(--text-h);letter-spacing:-0.01em;margin-bottom:4px}}
  .timestamp{{font-family:'IBM Plex Mono',monospace;font-size:10px;color:var(--text-m);letter-spacing:0.04em}}
  .toggle{{background:var(--tog-bg);border:1px solid var(--tog-br);border-radius:8px;padding:7px 10px;cursor:pointer;font-size:16px;line-height:1;flex-shrink:0;margin-left:12px;margin-top:2px;transition:background 0.15s}}
  .toggle:hover{{background:rgba(200,169,110,0.1);border-color:rgba(200,169,110,0.3)}}

  /* Page nav */
  .page-nav{{display:flex;gap:0}}
  .page-nav a{{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:0.08em;color:var(--text-m);text-decoration:none;padding:10px 16px;border-bottom:2px solid transparent;transition:all 0.15s}}
  .page-nav a:hover{{color:var(--gold)}}
  .page-nav a.active{{color:var(--gold);border-bottom-color:var(--gold)}}

  /* Controls */
  .controls{{padding:14px 16px;border-bottom:1px solid var(--bdr-sec);display:flex;flex-direction:column;gap:10px}}
  .search-wrap{{position:relative}}
  .search-icon{{position:absolute;left:12px;top:50%;transform:translateY(-50%);font-size:14px;pointer-events:none}}
  .search-box{{width:100%;padding:9px 12px 9px 36px;background:var(--bg-card);border:1px solid var(--bdr);border-radius:8px;color:var(--text);font-family:'IBM Plex Sans',sans-serif;font-size:13px;outline:none;transition:border-color 0.15s}}
  .search-box:focus{{border-color:rgba(200,169,110,0.4)}}
  .search-box::placeholder{{color:var(--text-f)}}
  .group-row{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
  .group-label{{font-family:'IBM Plex Mono',monospace;font-size:10px;color:var(--text-d);letter-spacing:0.08em;text-transform:uppercase}}
  .group-btn{{
    background:transparent;border:1px solid var(--bdr);color:var(--text-m);
    border-radius:6px;padding:5px 11px;font-size:11px;
    font-family:'IBM Plex Mono',monospace;letter-spacing:0.05em;
    cursor:pointer;transition:all 0.2s ease-out;
  }}
  .group-btn.active{{
    background:rgba(200,169,110,0.15);border-color:var(--gold);
    color:var(--gold);transform:scale(1.03);
  }}
  .group-btn:hover:not(.active){{background:rgba(255,255,255,0.05);color:var(--text);}}

  /* Chamber tabs */
  .chamber-tabs{{display:flex;border-bottom:1px solid var(--bdr-sec);background:var(--bg-sec)}}
  .chamber-tab{{flex:1;padding:12px 8px;text-align:center;cursor:pointer;font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:0.08em;color:var(--text-d);border-bottom:2px solid transparent;transition:all 0.15s}}
  .chamber-tab.active{{color:var(--gold);border-bottom-color:var(--gold)}}
  .tab-count{{font-family:'Playfair Display',serif;font-size:18px;font-weight:700;display:block;margin-bottom:2px}}

  /* Content */
  .content{{padding:14px 16px}}
  .section-hdr{{
    font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:0.14em;
    text-transform:uppercase;color:var(--text-d);
    padding:14px 0 10px;margin-bottom:12px;
    border-bottom:1px solid var(--bdr-sec);
    display:flex;align-items:center;gap:8px;
  }}
  .section-hdr::after{{content:'';flex:1;height:1px;background:var(--bdr-sec);}}

  /* Two-column party layout */
  .party-cols{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px}}
  .party-col-hdr{{font-family:'IBM Plex Mono',monospace;font-size:9px;letter-spacing:0.12em;text-transform:uppercase;padding:4px 0;margin-bottom:6px;border-bottom:2px solid}}
  .col-rep{{color:var(--rep);border-color:var(--rep)}}
  .col-dem{{color:var(--dem);border-color:var(--dem)}}
  .col-ind{{color:var(--ind);border-color:var(--ind)}}

  /* Leader grid — side by side */
  .leader-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px}}

  /* Member card — collapsed only, clean grid */
  .member-card {{
    border:1px solid var(--bdr);border-radius:12px;
    background:var(--bg-card);margin-bottom:8px;
    cursor:pointer;
    transition:background 0.2s ease-out, transform 0.2s ease-out, box-shadow 0.2s ease-out;
    overflow:hidden;
    box-shadow:0 1px 3px rgba(0,0,0,0.2);
  }}
  .member-card:hover {{
    background:var(--bg-card-h);
    transform:translateY(-2px);
    box-shadow:0 4px 12px rgba(0,0,0,0.3);
  }}
  .card-leader{{border-left:3px solid var(--gold);}}
  .card-chair{{border-left:3px solid rgba(200,169,110,0.5);}}
  .card-ranking{{border-left:3px solid var(--bdr);}}

  .card-face {{ display:flex;align-items:center;gap:12px;padding:12px 14px; }}

  /* Photo — 80×100px */
  .photo {{
    width:80px;height:100px;border-radius:8px;
    object-fit:cover;object-position:top;
    flex-shrink:0;background:var(--bg-sec);
    border:1.5px solid var(--bdr-h);
    box-shadow:inset 0 0 8px rgba(0,0,0,0.15);
  }}
  .initials-box {{
    width:80px;height:100px;border-radius:6px;
    display:flex;align-items:center;justify-content:center;
    font-family:'Playfair Display',serif;font-size:28px;font-weight:700;
    flex-shrink:0;color:white;border:1px solid rgba(255,255,255,0.1);
  }}
  .i-rep{{ background:rgba(160,50,50,0.75); }}
  .i-dem{{ background:rgba(50,100,160,0.75); }}
  .i-ind{{ background:rgba(100,50,160,0.75); }}

  .card-face .info {{ flex:1;min-width:0;overflow:hidden;word-break:break-word; }}
  .mname {{ font-size:13px;font-weight:700;color:var(--text);line-height:1.3;margin-bottom:3px; }}
  .mmeta {{ font-family:'IBM Plex Mono',monospace;font-size:10px;color:var(--text-m);margin-bottom:4px; }}
  .mrole {{
    display:inline-block;font-family:'IBM Plex Mono',monospace;
    font-size:8px;letter-spacing:0.05em;padding:2px 5px;
    border-radius:3px;text-transform:uppercase;font-weight:700;line-height:1.4;
    white-space:nowrap;max-width:100%;overflow:hidden;text-overflow:ellipsis;
  }}
  .role-leader {{ background:rgba(200,169,110,0.15);color:var(--gold);border:1px solid rgba(200,169,110,0.35); }}
  .role-whip   {{ background:rgba(160,120,200,0.1);color:var(--purple);border:1px solid rgba(160,120,200,0.3); }}
  .role-chair  {{ background:rgba(200,169,110,0.08);color:var(--gold);border:1px solid rgba(200,169,110,0.2); }}
  .role-rm     {{ background:var(--bg-sec);color:var(--text-s);border:1px solid var(--bdr); }}
  .pbadge {{ font-family:'IBM Plex Mono',monospace;font-size:9px;font-weight:700;padding:1px 5px;border-radius:3px;margin-left:4px; }}
  .b-rep{{ background:var(--rep-bg);color:var(--rep);border:1px solid var(--rep-br); }}
  .b-dem{{ background:var(--dem-bg);color:var(--dem);border:1px solid var(--dem-br); }}
  .b-ind{{ background:var(--ind-bg);color:var(--ind);border:1px solid var(--ind-br); }}

  /* ── Modal ── */
  .modal-overlay {{
    position:fixed;inset:0;z-index:1000;
    background:rgba(0,0,0,0.75);
    display:flex;align-items:center;justify-content:center;
    opacity:0;pointer-events:none;
    transition:opacity 0.2s;
    padding:16px;
  }}
  .modal-overlay.visible {{ opacity:1;pointer-events:all; }}
  .modal {{
    background:var(--bg);
    border:1px solid var(--bdr-h);
    border-radius:20px;
    width:100%;
    max-width:420px;   /* same width on desktop as mobile feel */
    max-height:88vh;
    overflow-y:auto;
    position:relative;
    transform:scale(0.82) translateY(20px);
    opacity:0;
    transition:transform 0.28s cubic-bezier(0.34,1.4,0.64,1), opacity 0.18s;
    transform-origin:center center;
    -webkit-overflow-scrolling:touch;
  }}
  .modal-overlay.visible .modal {{
    transform:scale(1) translateY(0);
    opacity:1;
  }}
  .modal-close {{
    position:sticky;top:0;z-index:10;
    display:flex;justify-content:flex-end;
    padding:14px 16px 0;
    background:var(--bg);
  }}
  .modal-close button {{
    background:var(--bg-sec);border:1px solid var(--bdr);
    border-radius:20px;padding:5px 14px;
    font-family:'IBM Plex Mono',monospace;font-size:11px;
    color:var(--text-m);cursor:pointer;transition:background 0.15s;
  }}
  .modal-close button:hover {{ background:rgba(200,169,110,0.1); }}
  .modal-body {{ padding:0 20px 28px; }}
  .modal-photo-wrap {{ display:flex;justify-content:center;margin-bottom:18px;padding-top:10px; }}
  .modal-photo {{
    width:120px;height:150px;border-radius:10px;
    object-fit:cover;object-position:top;
    border:2px solid var(--bdr-h);background:var(--bg-sec);
  }}
  .modal-initials {{
    width:120px;height:150px;border-radius:10px;
    display:flex;align-items:center;justify-content:center;
    font-family:'Playfair Display',serif;font-size:42px;font-weight:700;color:white;
  }}
  .modal-name {{
    font-family:'Playfair Display',serif;
    font-size:22px;font-weight:700;
    color:var(--text-h);text-align:center;
    margin-bottom:5px;line-height:1.2;
  }}
  .modal-sub {{
    font-family:'IBM Plex Mono',monospace;
    font-size:11px;color:var(--text-m);
    text-align:center;letter-spacing:0.05em;
    margin-bottom:18px;line-height:1.6;
  }}
  .modal-divider {{ border:none;border-top:1px solid var(--bdr-sec);margin:16px 0; }}
  .modal-section-label {{
    font-family:'IBM Plex Mono',monospace;font-size:10px;
    letter-spacing:0.12em;text-transform:uppercase;
    color:var(--text-d);margin-bottom:6px;
  }}
  .modal-section-value {{
    font-size:15px;color:var(--text-s);line-height:1.65;
    margin-bottom:16px;
  }}
  .modal-cmte {{
    font-size:14px;color:var(--text-s);line-height:1.65;
    padding:8px 12px;border-left:2px solid var(--bdr);
    margin-bottom:8px;
  }}
  .modal-cmte-badge {{
    display:inline-block;font-family:'IBM Plex Mono',monospace;
    font-size:9px;font-weight:700;letter-spacing:0.05em;
    padding:2px 6px;border-radius:3px;margin-bottom:4px;
  }}
  .badge-chair {{ background:rgba(200,169,110,0.15);color:var(--gold);border:1px solid rgba(200,169,110,0.3); }}
  .badge-rm    {{ background:var(--bg-sec);color:var(--text-s);border:1px solid var(--bdr); }}

  /* State / committee group views */
  .group-block{{margin-bottom:14px}}
  .group-title{{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gold);padding:5px 0;margin-bottom:6px;border-bottom:1px solid var(--bdr)}}
  .cmte-title{{color:var(--text-m)}}

  .source-note{{margin-top:20px;padding:12px 14px;background:rgba(255,255,255,0.012);border:1px solid var(--bdr);border-radius:6px;font-family:'IBM Plex Mono',monospace;font-size:10px;color:var(--text-d);line-height:1.6}}
  .empty{{text-align:center;padding:40px;color:var(--text-f);font-size:13px}}
</style>
</head>
<body>

<div class="header">
  <div class="header-top">
    <div>
      <div class="eyebrow">🏛 Congressional Hearing Tracker</div>
      <h1>Congressional Directory</h1>
      <div class="timestamp">Updated {generated} · {today_long} · Refreshes daily</div>
    </div>
    <button class="toggle" id="tog" onclick="toggleTheme()">☀️</button>
  </div>
  <nav class="page-nav">
    <a href="index.html">Hearings</a>
    <a href="members.html" class="active">Members</a>
  </nav>
</div>

<div class="controls">
  <div class="search-wrap">
    <span class="search-icon">🔍</span>
    <input class="search-box" id="search" type="text"
      placeholder="Search by name, state, or committee..."
      oninput="render()">
  </div>
  <div class="group-row">
    <span class="group-label">Group by</span>
    <button class="group-btn active" onclick="setGroup('party',this)">Party</button>
    <button class="group-btn" onclick="setGroup('state',this)">State</button>
    <button class="group-btn" onclick="setGroup('committee',this)">Committee</button>
    <button class="group-btn" onclick="setGroup('leadership',this)">Leadership</button>
  </div>
  <div class="group-row">
    <span class="group-label">Congressional Caucuses</span>
    <button class="group-btn caucus-btn active" onclick="setCaucus('all',this)">All</button>
    <button class="group-btn caucus-btn" onclick="setCaucus('cbc',this)">Black Caucus</button>
  </div>
</div>

<div class="chamber-tabs">
  <div class="chamber-tab active" id="tab-senate" onclick="setChamber('senate')">
    <span class="tab-count" id="cnt-senate">—</span>SENATE
  </div>
  <div class="chamber-tab" id="tab-house" onclick="setChamber('house')">
    <span class="tab-count" id="cnt-house">—</span>HOUSE
  </div>
</div>

<div class="content" id="cbc-panel" style="display:none;border-bottom:1px solid var(--bdr-sec);padding-bottom:0"></div>
<div class="content" id="content"></div>

<div class="modal-overlay" id="modal-overlay" onclick="closeModal(event)">
  <div class="modal" id="modal">
    <div class="modal-close"><button onclick="closeModal(null)">✕ Close</button></div>
    <div class="modal-body" id="modal-body"></div>
  </div>
</div>

<script>
const DATA      = {members_json};
const SENATORS  = DATA.senators  || [];
const REPS      = DATA.reps      || [];
const VACANCIES = DATA.vacancies || [];
let chamber = 'senate';
let group   = 'party';
let caucus  = 'all';

// ── Theme ──────────────────────────────────────────────────────────────────────
function sysTheme(){{ return matchMedia('(prefers-color-scheme:light)').matches?'light':'dark'; }}
function applyTheme(t){{
  document.documentElement.classList.remove('light','dark');
  document.documentElement.classList.add(t);
  document.getElementById('tog').textContent = t==='dark'?'☀️':'🌙';
}}
function toggleTheme(){{
  const n = document.documentElement.classList.contains('light')?'dark':'light';
  localStorage.setItem('theme',n); applyTheme(n);
}}
(function(){{ applyTheme(localStorage.getItem('theme')||sysTheme()); }})();
matchMedia('(prefers-color-scheme:light)').addEventListener('change',e=>{{
  if(!localStorage.getItem('theme')) applyTheme(e.matches?'light':'dark');
}});

// ── Card builder ───────────────────────────────────────────────────────────────
function roleHtml(m){{
  if(!m.leadership) return '';
  const tier  = m.leadership.tier;
  const label = m.leadership.label;
  const l     = label.toLowerCase();
  // Tiers 1-3: institutional leaders — always show badge
  // Tiers 4-5: full committee chairs/RMs — show badge
  // Tiers 6-7: subcommittee chairs/RMs — show smaller badge
  // Tier 99+: no badge
  if(tier > 7) return '';
  let cls = 'role-chair';
  if(l.includes('leader')||l.includes('speaker')||l.includes('pro tempore')) cls='role-leader';
  else if(l.includes('whip')) cls='role-whip';
  else if(l.includes('ranking')) cls='role-rm';
  const display = tier<=3 ? label
                : tier===4 ? 'Chair'
                : tier===5 ? 'Ranking Member'
                : tier===6 ? 'Subcmte. Chair'
                : 'Subcmte. Ranking Member';
  const sizeStyle = tier >= 6 ? 'font-size:7px;opacity:0.85;' : '';
  return `<span class="mrole ${{cls}}" style="${{sizeStyle}}">${{display}}</span>`;
}}

function roleClass(m){{
  if(!m.leadership) return '';
  // Only apply gold left border for institutional leaders
  if(m.leadership.tier <= 3) return 'card-leader';
  return '';
}}

function photoEl(m, cls, initCls){{
  return m.photo_url
    ? `<img class="${{cls}}" src="${{m.photo_url}}"
         onerror="this.style.display='none';this.nextElementSibling.style.display='flex';"
         alt="${{m.name}}" loading="lazy">
       <div class="${{initCls}} i-${{m.party_class}}" style="display:none">${{m.initials}}</div>`
    : `<div class="${{initCls}} i-${{m.party_class}}">${{m.initials}}</div>`;
}}

function fullRoleDescription(m){{
  if(!m.leadership) return '';
  const label = m.leadership.label;
  const tier  = m.leadership.tier;
  if(tier<=2) return label + (m.chamber==='senate'
    ? ' of the United States Senate'
    : ' of the United States House of Representatives');
  return label.replace(/^RM,\s*/,'Ranking Member, ');
}}

function buildCommitteeSections(m){{
  const cmtes = (m.committees||[]);
  if(!cmtes.length) return '<p style="color:var(--text-f);font-style:italic;font-size:14px;margin-top:6px">No committee data available</p>';

  // Deduplicate — keep highest role per committee
  const roleRank = {{'Chair':0,'Chairman':0,'Chairwoman':0,'Chairperson':0,'Ranking Member':1,'Member':2}};
  const seen = {{}};
  cmtes.forEach(c=>{{
    const key  = c.committee;
    const rank = roleRank[c.role] ?? 2;
    if(!(key in seen) || rank < seen[key].rank)
      seen[key] = {{...c, rank}};
  }});
  const all = Object.values(seen).sort((a,b)=>a.rank-b.rank||a.committee.localeCompare(b.committee));

  const chairs   = all.filter(c=>c.rank===0);
  const rankings = all.filter(c=>c.rank===1);
  const members  = all.filter(c=>c.rank===2);

  let html = '';

  if(chairs.length){{
    html += `<div class="modal-section-label" style="margin-top:14px">Chairs</div>`;
    html += chairs.map(c=>`<div class="modal-cmte" style="border-left-color:var(--gold)">${{c.committee}}</div>`).join('');
  }}

  if(rankings.length){{
    html += `<div class="modal-section-label" style="margin-top:14px">Ranking Member</div>`;
    html += rankings.map(c=>`<div class="modal-cmte">${{c.committee}}</div>`).join('');
  }}

  if(members.length){{
    html += `<div class="modal-section-label" style="margin-top:14px">Committee Assignments</div>`;
    html += members.map(c=>`<div class="modal-cmte">${{c.committee}}</div>`).join('');
  }}

  return html;
}}

// ── Modal ─────────────────────────────────────────────────────────────────────
function openModal(m){{
  const pc          = m.party_class;
  const partyFull   = pc==='rep'?'Republican':pc==='dem'?'Democrat':'Independent';
  const chamberFull = m.chamber==='senate'
    ? 'United States Senate'
    : 'United States House of Representatives';
  const dist = m.chamber==='house' && m.district ? `District ${{m.district}} · ` : '';
  const stateFull = STATE_NAMES[m.state] || m.state;

  // Institutional role (tier 1-3 only)
  let instRole = '';
  if(m.leadership && m.leadership.tier <= 3){{
    const label = m.leadership.label;
    const tier  = m.leadership.tier;
    instRole = tier<=2
      ? label + (m.chamber==='senate' ? ' of the United States Senate' : ' of the United States House of Representatives')
      : label;
  }}

  const photoHtml = m.photo_url
    ? `<img class="modal-photo" src="${{m.photo_url}}"
         onerror="this.style.display='none';this.nextElementSibling.style.display='flex';"
         alt="${{m.name}}">
       <div class="modal-initials i-${{pc}}" style="display:none">${{m.initials}}</div>`
    : `<div class="modal-initials i-${{pc}}">${{m.initials}}</div>`;

  document.getElementById('modal-body').innerHTML = `
    <div class="modal-photo-wrap">${{photoHtml}}</div>
    <div class="modal-name">${{m.name}}</div>
    <div class="modal-sub">
      ${{chamberFull}}<br>
      ${{dist}}${{stateFull}} · ${{partyFull}} <span class="pbadge b-${{pc}}">${{m.party_short}}</span>
    </div>
    ${{instRole ? `
    <hr class="modal-divider">
    <div class="modal-section-label">Leadership Role</div>
    <div class="modal-section-value">${{instRole}}</div>` : ''}}
    <hr class="modal-divider">
    <div class="modal-section-label">About</div>
    ${{m.bio_slug ? `
    <a href="bios/${{m.bio_slug}}.html"
       style="display:block;font-family:'IBM Plex Mono',monospace;font-size:12px;
              letter-spacing:0.06em;padding:10px 16px;border:1px solid rgba(200,169,110,0.35);
              border-radius:8px;color:var(--gold);text-decoration:none;
              transition:all 0.2s;background:rgba(200,169,110,0.05);margin-bottom:4px;
              text-align:center;"
       onmouseover="this.style.background='rgba(200,169,110,0.12)'"
       onmouseout="this.style.background='rgba(200,169,110,0.05)'"
       target="_blank">
      → Full Biography
    </a>` : '<div style="color:var(--text-faint);font-style:italic;font-size:12px">Biography not yet available</div>'}}
    <hr class="modal-divider">
    ${{buildCommitteeSections(m)}}
  `;

  document.getElementById('modal-overlay').classList.add('visible');
  document.body.style.overflow = 'hidden';
}}

function closeModal(e){{
  if(e && e.target !== document.getElementById('modal-overlay')) return;
  document.getElementById('modal-overlay').classList.remove('visible');
  document.body.style.overflow = '';
}}

document.addEventListener('keydown', e => {{ if(e.key==='Escape') closeModal(null); }});

// ── Card (collapsed only — tap opens modal) ───────────────────────────────────
function card(m){{
  const pc   = m.party_class;
  const cc   = roleClass(m);
  const dist = (m.chamber==='house' && m.district) ? ` · District ${{m.district}}` : '';
  const idx  = CURRENT_MEMBERS.push(m) - 1;
  return `<div class="member-card ${{cc}}" onclick="openModal(CURRENT_MEMBERS[${{idx}}])">
    <div class="card-face">
      ${{photoEl(m,'photo','initials-box')}}
      <div class="info">
        <div class="mname">${{m.name}}</div>
        <div class="mmeta">${{m.state}}${{dist}} <span class="pbadge b-${{pc}}">${{m.party_short}}</span></div>
        ${{roleHtml(m)}}
      </div>
    </div>
  </div>`;
}}

let CURRENT_MEMBERS = [];

const STATE_NAMES = {{
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
}};

// ── Filter ────────────────────────────────────────────────────────────────────
function filtered(){{
  const q = document.getElementById('search').value.toLowerCase().trim();
  let pool = q
    ? [...SENATORS, ...REPS]
    : chamber==='senate' ? SENATORS : REPS;
  if(caucus !== 'all')
    pool = pool.filter(m=>(m.caucuses||[]).includes(caucus));
  if(!q) return pool;
  return pool.filter(m=>
    m.name.toLowerCase().includes(q) ||
    m.state.toLowerCase().includes(q) ||
    (m.committees||[]).some(c=>c.committee.toLowerCase().includes(q)) ||
    (m.leadership?.label||'').toLowerCase().includes(q)
  );
}}

function setCaucus(c, btn){{
  caucus = c;
  document.querySelectorAll('.caucus-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  // When CBC is active, hide chamber tabs and main content — CBC panel is self-contained
  const isCbc = c === 'cbc';
  document.querySelector('.chamber-tabs').style.display = isCbc ? 'none' : '';
  document.getElementById('content').style.display = isCbc ? 'none' : '';
  const panel = document.getElementById('cbc-panel');
  if(panel) panel.style.display = isCbc ? 'block' : 'none';
  render();
}}

// ── CBC Panel ─────────────────────────────────────────────────────────────────
function buildCbcPanel(){{
  const cbcMembers = [...SENATORS,...REPS].filter(m=>(m.caucuses||[]).includes('cbc'));
  if(!cbcMembers.length) return '';

  const senate  = cbcMembers.filter(m=>m.chamber==='senate');
  const house   = cbcMembers.filter(m=>m.chamber==='house');

  const miniCard = (m) => {{
    const idx = CURRENT_MEMBERS.push(m)-1;
    const pc  = m.party_class;
    const dist = m.chamber==='house'&&m.district?` · District ${{m.district}}`:'';
    return `<div class="member-card" onclick="openModal(CURRENT_MEMBERS[${{idx}}])">
      <div class="card-face">
        ${{photoEl(m,'photo','initials-box')}}
        <div class="info">
          <div class="mname">${{m.name}}</div>
          <div class="mmeta">${{m.state}}${{dist}} <span class="pbadge b-${{pc}}">${{m.party_short}}</span></div>
          ${{roleHtml(m)}}
        </div>
      </div>
    </div>`;
  }};

  const chamberSection = (arr, label) => {{
    if(!arr.length) return '';
    const leaders  = arr.filter(m=>m.leadership&&m.leadership.tier<=3);
    const chairs   = arr.filter(m=>m.leadership&&m.leadership.tier===4);
    const rankings = arr.filter(m=>m.leadership&&m.leadership.tier===5);
    const rest     = arr.filter(m=>!m.leadership||m.leadership.tier>5);
    let h = `<div class="party-col-hdr col-dem" style="margin-bottom:8px">${{label}} · ${{arr.length}}</div>`;
    if(leaders.length) {{
      h += `<div class="section-hdr" style="font-size:9px;margin-bottom:6px">── Leadership</div>`;
      h += `<div class="party-cols">${{leaders.map(miniCard).join('')}}</div>`;
    }}
    if(chairs.length||rankings.length) {{
      h += `<div class="section-hdr" style="font-size:9px;margin-bottom:6px">── Committee Chairs & Ranking Members</div>`;
      h += `<div class="party-cols">${{[...chairs,...rankings].map(miniCard).join('')}}</div>`;
    }}
    h += `<div class="party-cols">${{rest.map(miniCard).join('')}}</div>`;
    return h;
  }};

  return `
    <div style="margin-bottom:6px">
      <div class="section-hdr">── Congressional Black Caucus · ${{cbcMembers.length}} Members</div>
      ${{chamberSection(senate, 'Senate')}}
      ${{house.length ? `<div style="margin-top:10px">${{chamberSection(house, 'House')}}</div>` : ''}}
    </div>`;
}}

// ── Render modes ──────────────────────────────────────────────────────────────
function renderParty(members){{
  const leaders   = members.filter(m=>m.leadership&&m.leadership.tier<=3);
  const chairs    = members.filter(m=>m.leadership&&m.leadership.tier===4);
  const rankings  = members.filter(m=>m.leadership&&m.leadership.tier===5);
  const subcChairs= members.filter(m=>m.leadership&&m.leadership.tier===6);
  const subcRMs   = members.filter(m=>m.leadership&&m.leadership.tier===7);
  const rest      = members.filter(m=>!m.leadership||m.leadership.tier>7);
  const maj = rest.filter(m=>m.party_class==='rep');
  const min = rest.filter(m=>m.party_class==='dem');
  const ind = rest.filter(m=>m.party_class==='ind');
  let h = '';

  if(leaders.length){{
    h += `<div class="section-hdr">── Party Leadership</div><div class="leader-grid">`;
    const majL = leaders.filter(m=>m.party_class==='rep').sort((a,b)=>a.leadership.tier-b.leadership.tier);
    const minL = leaders.filter(m=>m.party_class!=='rep').sort((a,b)=>a.leadership.tier-b.leadership.tier);
    const mx = Math.max(majL.length,minL.length);
    for(let i=0;i<mx;i++){{
      h += majL[i]?card(majL[i]):'<div></div>';
      h += minL[i]?card(minL[i]):'<div></div>';
    }}
    h += '</div>';
  }}

  if(chairs.length||rankings.length){{
    h += `<div class="section-hdr">── Committee Chairs & Ranking Members</div><div class="leader-grid">`;
    const allChairs   = chairs.sort((a,b)=>(a.leadership.committee||'').localeCompare(b.leadership.committee||''));
    const allRankings = rankings.sort((a,b)=>(a.leadership.committee||'').localeCompare(b.leadership.committee||''));
    const mx = Math.max(allChairs.length,allRankings.length);
    for(let i=0;i<mx;i++){{
      h += allChairs[i]?card(allChairs[i]):'<div></div>';
      h += allRankings[i]?card(allRankings[i]):'<div></div>';
    }}
    h += '</div>';
  }}

  if(subcChairs.length||subcRMs.length){{
    h += `<div class="section-hdr">── Subcommittee Chairs & Ranking Members</div><div class="leader-grid">`;
    const scSorted = subcChairs.sort((a,b)=>(a.leadership.committee||'').localeCompare(b.leadership.committee||''));
    const srSorted = subcRMs.sort((a,b)=>(a.leadership.committee||'').localeCompare(b.leadership.committee||''));
    const mx = Math.max(scSorted.length, srSorted.length);
    for(let i=0;i<mx;i++){{
      h += scSorted[i] ? card(scSorted[i]) : '<div></div>';
      h += srSorted[i] ? card(srSorted[i]) : '<div></div>';
    }}
    h += '</div>';
  }}

  if(rest.length){{
    const voting    = rest.filter(m=>!m.delegate);
    const delegates = rest.filter(m=>m.delegate);
    const vmaj = voting.filter(m=>m.party_class==='rep');
    const vmin = voting.filter(m=>m.party_class==='dem');
    const vind = voting.filter(m=>m.party_class==='ind');

    if(voting.length){{
      h += `<div class="section-hdr">── Sitting Members · ${{voting.length}}</div>
      <div class="party-cols">
        <div>
          <div class="party-col-hdr col-rep">Republican · ${{vmaj.length}}</div>
          ${{vmaj.map(card).join('')}}
        </div>
        <div>
          <div class="party-col-hdr col-dem">Democrat · ${{vmin.length}}</div>
          ${{vmin.map(card).join('')}}
          ${{vind.length?`<div class="party-col-hdr col-ind" style="margin-top:10px">Independent · ${{vind.length}}</div>${{vind.map(card).join('')}}`:''}}
        </div>
      </div>`;
    }}

    if(delegates.length){{
      h += `<div class="section-hdr" style="margin-top:16px">── Non-Voting Delegates & Commissioners · ${{delegates.length}}</div>
      <div class="party-cols">${{delegates.map(card).join('')}}</div>`;
    }}
  }}
  return h || '<div class="empty">No members found.</div>';
}}

function renderState(members){{
  const by={{}};
  members.forEach(m=>{{(by[m.state]=by[m.state]||[]).push(m);}});
  return Object.keys(by).sort().map(s=>
    `<div class="group-block"><div class="group-title">${{s}}</div>${{by[s].map(card).join('')}}</div>`
  ).join('') || '<div class="empty">No members found.</div>';
}}

function renderCommittee(members){{
  const by={{}};
  members.forEach(m=>{{
    (m.committees||[]).filter(c=>c.role!=='Member').forEach(c=>{{
      (by[c.committee]=by[c.committee]||[]).push(m);
    }});
  }});
  if(!Object.keys(by).length) return '<div class="empty">No committee data found.</div>';
  return Object.keys(by).sort().map(c=>
    `<div class="group-block"><div class="group-title cmte-title">${{c}}</div>${{by[c].map(card).join('')}}</div>`
  ).join('');
}}

function renderLeadership(members){{
  const leaders = members.filter(m=>m.leadership);
  if(!leaders.length) return '<div class="empty">No leadership data found.</div>';
  return `<div class="section-hdr">── Leadership & Committee Chairs</div>`+leaders.map(card).join('');
}}

// ── Vacant seats ──────────────────────────────────────────────────────────────
function renderVacancies(){{
  if(!VACANCIES.length) return '';
  const STATE_NAMES_V = STATE_NAMES; // reuse existing lookup
  return `
    <div style="margin-top:20px">
      <div class="section-hdr">── Vacant Seats · ${{VACANCIES.length}}</div>
      <div class="party-cols">
        ${{VACANCIES.map(v=>{{
          const stateFull = STATE_NAMES_V[v.state] || v.state;
          const pc = v.party;
          return `<div class="member-card" style="cursor:default;opacity:0.8">
            <div class="card-face">
              <div class="initials-box" style="background:rgba(120,120,120,0.3);border:1px solid var(--bdr);color:var(--text-d);font-size:18px">
                ${{v.state}}-${{v.district}}
              </div>
              <div class="info">
                <div class="mname" style="color:var(--text-d)">Vacant</div>
                <div class="mmeta">${{v.label}}</div>
                <div style="font-size:11px;color:var(--text-d);margin-top:4px;line-height:1.5">
                  ${{v.reason}}<br>
                  <span style="color:var(--gold);font-family:'IBM Plex Mono',monospace;font-size:10px">${{v.election}}</span>
                </div>
              </div>
            </div>
          </div>`;
        }}).join('')}}
      </div>
    </div>`;
}}

// ── Main render ───────────────────────────────────────────────────────────────
function render(){{
  CURRENT_MEMBERS = [];

  const panel = document.getElementById('cbc-panel');
  if(panel){{
    panel.innerHTML = buildCbcPanel();
    panel.style.display = caucus==='cbc' ? 'block' : 'none';
  }}

  const members = filtered();
  let html = '';
  if(group==='party')           html = renderParty(members);
  else if(group==='state')      html = renderState(members);
  else if(group==='committee')  html = renderCommittee(members);
  else                          html = renderLeadership(members);

  // Add vacant seats section at bottom of House tab only
  if(chamber === 'house' && caucus === 'all' && VACANCIES.length){{
    html += renderVacancies();
  }}

  document.getElementById('content').innerHTML = html +
    `<div class="source-note">ℹ Data: github.com/unitedstates/congress-legislators · Photos: bioguide.congress.gov · Bios: Wikipedia · Refreshes daily · Vacancies checked every 3 days</div>`;
}}

function setChamber(c){{
  chamber=c;
  document.querySelectorAll('.chamber-tab').forEach(t=>t.classList.remove('active'));
  document.getElementById('tab-'+c).classList.add('active');
  render();
}}

function setGroup(g,btn){{
  group=g;
  document.querySelectorAll('.group-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  render();
}}

// Init
document.getElementById('cnt-senate').textContent = SENATORS.length;
const votingReps   = REPS.filter(m=>!m.delegate).length;
const delegateReps = REPS.filter(m=>m.delegate).length;
const vacantCount  = VACANCIES.length;
document.getElementById('cnt-house').textContent = 435;
render();
</script>
</body>
</html>"""

build()
