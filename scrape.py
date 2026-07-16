"""
Congressional Hearing Tracker — Scraper (runs every 15 min)
Fixes:
  - Auto DST timezone (no manual changes needed ever)
  - Smart cancellation: only flags if cancellation is within 300 chars of today's date
  - Chair false-positive fix: ignores "Ranking Member" and generic titles
  - DataTables full-load: multiple strategies to show all rows
  - PDF witness lists via pdfplumber
  - Merge strategy: baseline is never overwritten, only enriched
"""

import asyncio
import json
import os
import re
import io
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright

try:
    import pdfplumber
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

try:
    import requests as req_lib
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ── Auto DST timezone ──────────────────────────────────────────────────────────

def get_et_offset():
    now_utc = datetime.now(timezone.utc)
    year = now_utc.year
    def nth_sunday(month, n):
        d = datetime(year, month, 1, tzinfo=timezone.utc)
        days_to_sun = (6 - d.weekday()) % 7
        return (d + timedelta(days=days_to_sun + 7*(n-1))).replace(hour=7)
    dst_start = nth_sunday(3, 2)   # 2nd Sunday March
    dst_end   = nth_sunday(11, 1)  # 1st Sunday November
    return timedelta(hours=-4) if dst_start <= now_utc < dst_end else timedelta(hours=-5)

ET_OFFSET   = get_et_offset()
now_utc     = datetime.now(timezone.utc)
now_et      = now_utc + ET_OFFSET
today_str   = now_et.strftime("%B %-d, %Y")
today_long  = now_et.strftime("%A, %B %-d, %Y")
today_id    = now_et.strftime("%m%d%Y")
today_iso   = now_et.strftime("%Y-%m-%d")
generated   = now_et.strftime("%-I:%M %p ET")
change_time = now_et.strftime("%-I:%M %p")
tz_label    = "EDT" if ET_OFFSET.seconds//3600 == 20 else "EST"  # 20h = -4h unsigned

today_variants = [
    today_str, today_long,
    now_et.strftime("%b. %-d, %Y"),
    now_et.strftime("%b %-d, %Y"),
    now_et.strftime("%-d-%b-%Y").upper(),
    now_et.strftime("%-d-%b-%y").upper(),
    today_iso,
    now_et.strftime("%m/%d/%Y"),
    now_et.strftime("%m/%d/%y"),
    now_et.strftime("%m%d%y"),
    now_et.strftime("%m%d%Y"),
    "Today,",
    now_et.strftime("%a, %b %-d"),
]

SNAPSHOT_FILE = "snapshot.json"
BASELINE_FILE = "baseline.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# ── Hardcoded 119th Congress full committee chairs ─────────────────────────────
# Validated every 3 days by validate_hardcoded.py
COMMITTEE_CHAIRS = {
    # Senate (Republican chairs · Democrat ranking members)
    "agriculture":                  "Sen. John Boozman (R-AR), Chair · Sen. Amy Klobuchar (D-MN), Ranking Member",
    "appropriations":               "Sen. Susan Collins (R-ME), Chair · Sen. Patty Murray (D-WA), Ranking Member",
    "armed services":               "Sen. Roger Wicker (R-MS), Chair · Sen. Jack Reed (D-RI), Ranking Member",
    "banking":                      "Sen. Tim Scott (R-SC), Chair · Sen. Elizabeth Warren (D-MA), Ranking Member",
    "budget":                       "Sen. Lindsey Graham (R-SC), Chair · Sen. Jeff Merkley (D-OR), Ranking Member",
    "commerce":                     "Sen. Ted Cruz (R-TX), Chair · Sen. Maria Cantwell (D-WA), Ranking Member",
    "energy natural resources":     "Sen. Mike Lee (R-UT), Chair · Sen. Martin Heinrich (D-NM), Ranking Member",
    "environment public works":     "Sen. Shelley Moore Capito (R-WV), Chair · Sen. Sheldon Whitehouse (D-RI), Ranking Member",
    "finance":                      "Sen. Mike Crapo (R-ID), Chair · Sen. Ron Wyden (D-OR), Ranking Member",
    "foreign relations":            "Sen. Jim Risch (R-ID), Chair · Sen. Jeanne Shaheen (D-NH), Ranking Member",
    "health help":                  "Sen. Bill Cassidy (R-LA), Chair · Sen. Bernie Sanders (I-VT), Ranking Member",
    "homeland security":            "Sen. Rand Paul (R-KY), Chair · Sen. Gary Peters (D-MI), Ranking Member",
    "indian affairs":               "Sen. Lisa Murkowski (R-AK), Chair · Sen. Brian Schatz (D-HI), Ranking Member",
    "intelligence":                 "Sen. Tom Cotton (R-AR), Chair · Sen. Mark Warner (D-VA), Ranking Member",
    "judiciary":                    "Sen. Chuck Grassley (R-IA), Chair · Sen. Dick Durbin (D-IL), Ranking Member",
    "rules":                        "Sen. Amy Klobuchar (D-MN) · Sen. Deb Fischer (R-NE), Chair",
    "small business senate":        "Sen. Joni Ernst (R-IA), Chair · Sen. Ed Markey (D-MA), Ranking Member",
    "veterans affairs senate":      "Sen. Jerry Moran (R-KS), Chair · Sen. Richard Blumenthal (D-CT), Ranking Member",
    "joint economic":               "Sen. Mike Lee (R-UT), Chair · Rep. Don Beyer (D-VA), Ranking Member",
    # House (Republican chairs · Democrat ranking members)
    "house agriculture":            "Rep. Glenn Thompson (R-PA), Chair · Rep. David Scott (D-GA), Ranking Member",
    "house appropriations":         "Rep. Tom Cole (R-OK), Chair · Rep. Rosa DeLauro (D-CT), Ranking Member",
    "house armed services":         "Rep. Mike Rogers (R-AL), Chair · Rep. Adam Smith (D-WA), Ranking Member",
    "house education workforce":    "Rep. Tim Walberg (R-MI), Chair · Rep. Bobby Scott (D-VA), Ranking Member",
    "house energy commerce":        "Rep. Brett Guthrie (R-KY), Chair · Rep. Frank Pallone (D-NJ), Ranking Member",
    "house financial services":     "Rep. French Hill (R-AR), Chair · Rep. Maxine Waters (D-CA), Ranking Member",
    "house foreign affairs":        "Rep. Brian Mast (R-FL), Chair · Rep. Gregory Meeks (D-NY), Ranking Member",
    "house homeland security":      "Rep. Mark Green (R-TN), Chair · Rep. Bennie Thompson (D-MS), Ranking Member",
    "house judiciary":              "Rep. Jim Jordan (R-OH), Chair · Rep. Jerry Nadler (D-NY), Ranking Member",
    "house natural resources":      "Rep. Bruce Westerman (R-AR), Chair · Rep. Raúl Grijalva (D-AZ), Ranking Member",
    "house oversight":              "Rep. James Comer (R-KY), Chair · Rep. Jamie Raskin (D-MD), Ranking Member",
    "house science":                "Rep. Brian Babin (R-TX), Chair · Rep. Zoe Lofgren (D-CA), Ranking Member",
    "house transportation":         "Rep. Sam Graves (R-MO), Chair · Rep. Rick Larsen (D-WA), Ranking Member",
    "house veterans affairs":       "Rep. Mike Bost (R-IL), Chair · Rep. Mark Takano (D-CA), Ranking Member",
    "house ways means":             "Rep. Jason Smith (R-MO), Chair · Rep. Richard Neal (D-MA), Ranking Member",
    "house rules":                  "Rep. Virginia Foxx (R-NC), Chair",
    "house intelligence":           "Rep. Mike Turner (R-OH), Chair · Rep. Jim Himes (D-CT), Ranking Member",
    "house administration":         "Rep. Bryan Steil (R-WI), Chair · Rep. Joseph Morelle (D-NY), Ranking Member",
    "house small business":         "Rep. Roger Williams (R-TX), Chair · Rep. Nydia Velázquez (D-NY), Ranking Member",
    "house budget":                 "Rep. Jodey Arrington (R-TX), Chair · Rep. Brendan Boyle (D-PA), Ranking Member",
}

def lookup_chair(committee_name):
    """Match a committee name to its chair string."""
    norm = re.sub(r"[^a-z0-9 ]", "", committee_name.lower())
    norm = re.sub(r"\b(committee|on|the|and|of|select|permanent|special|joint|subcommittee|senate|house)\b", "", norm)
    norm = re.sub(r"\s+", " ", norm).strip()
    best_match = None
    best_score = 0
    for key, chair in COMMITTEE_CHAIRS.items():
        key_words = set(key.split())
        norm_words = set(norm.split())
        overlap = len(key_words & norm_words)
        if overlap > best_score and overlap >= len(key_words) * 0.6:
            best_score = overlap
            best_match = chair
    return best_match or ""

# ── Committee pages ────────────────────────────────────────────────────────────
SENATE_COMMITTEE_PAGES = [
    ("Armed Services",             "https://www.armed-services.senate.gov/hearings"),
    ("Agriculture",                "https://www.agriculture.senate.gov/hearings"),
    ("Appropriations",             "https://www.appropriations.senate.gov/hearings"),
    ("Banking",                    "https://www.banking.senate.gov/hearings"),
    ("Budget",                     "https://www.budget.senate.gov/hearings"),
    ("Commerce",                   "https://www.commerce.senate.gov/hearings"),
    ("Energy & Natural Resources", "https://www.energy.senate.gov/hearings"),
    ("Environment & Public Works", "https://www.epw.senate.gov/public/index.cfm/hearings"),
    ("Finance",                    "https://www.finance.senate.gov/hearings"),
    ("Foreign Relations",          "https://www.foreign.senate.gov/hearings"),
    ("Health HELP",                "https://www.help.senate.gov/hearings"),
    ("Homeland Security",          "https://www.hsgac.senate.gov/hearings"),
    ("Indian Affairs",             "https://www.indian.senate.gov/hearings"),
    ("Intelligence",               "https://www.intelligence.senate.gov/hearings"),
    ("Judiciary",                  "https://www.judiciary.senate.gov/committee-activity/hearings"),
    ("Rules",                      "https://www.rules.senate.gov/hearings"),
    ("Small Business",             "https://www.sbc.senate.gov/public/index.cfm/hearings"),
    ("Veterans Affairs",           "https://www.veterans.senate.gov/hearings"),
    ("Joint Economic",             "https://www.jec.senate.gov/public/index.cfm/hearings-calendar"),
    ("Narcotics Control",          "https://www.drugcaucus.senate.gov/"),
]

HOUSE_COMMITTEE_PAGES = [
    ("Agriculture",               "https://agriculture.house.gov/calendar/"),
    ("Appropriations",            "https://appropriations.house.gov/events/hearings"),
    ("Armed Services",            "https://armedservices.house.gov/hearings"),
    ("Education & Workforce",     "https://edworkforce.house.gov/hearings/"),
    ("Energy & Commerce",         "https://energycommerce.house.gov/hearings"),
    ("Financial Services",        "https://financialservices.house.gov/calendar/"),
    ("Foreign Affairs",           "https://foreignaffairs.house.gov/hearings/"),
    ("Homeland Security",         "https://homeland.house.gov/hearings/"),
    ("Judiciary",                 "https://judiciary.house.gov/hearings/"),
    ("Natural Resources",         "https://naturalresources.house.gov/hearings/"),
    ("Oversight",                 "https://oversight.house.gov/hearings/"),
    ("Science Space Technology",  "https://science.house.gov/hearings"),
    ("Transportation",            "https://transportation.house.gov/hearings/"),
    ("Veterans Affairs",          "https://veterans.house.gov/hearings/"),
    ("Ways & Means",              "https://waysandmeans.house.gov/hearings/"),
]

# ── Helpers ────────────────────────────────────────────────────────────────────
def hearing_key(h):
    return f"{h['chamber']}|{h['committee'][:40]}|{h['time']}"

def detect_cancellation_near_date(text, window=400):
    """
    Smart cancellation: only returns True if a cancellation keyword appears
    within `window` characters of today's date string in the text.
    Prevents false positives from old/unrelated postponed hearings on the page.
    """
    cancel_words = ["postponed", "cancelled", "canceled", "rescheduled",
                    "withdrawn", "notice of cancellation"]
    for variant in today_variants:
        idx = text.lower().find(variant.lower())
        if idx == -1:
            continue
        surrounding = text[max(0, idx - window//2) : idx + window].lower()
        if any(w in surrounding for w in cancel_words):
            return True
    return False

def detect_cancellation(text):
    """Loose check — only used on topic/committee name strings, not full pages."""
    return any(w in text.lower() for w in
               ["postponed", "cancelled", "canceled", "rescheduled", "withdrawn"])

def is_today(text):
    return any(v in text for v in today_variants)

def extract_witnesses(text):
    witnesses = []
    for line in text.split("\n"):
        line = line.strip()
        if re.match(r"^(Mr\.|Ms\.|Mrs\.|Dr\.|The Honorable|Prof\.|Hon\.)", line):
            clean = re.sub(r"\s+", " ", line).strip(" ,;")
            if clean and 10 < len(clean) < 150:
                witnesses.append(clean)
    return list(dict.fromkeys(witnesses))

# False positive chair titles to reject
BAD_CHAIR_STRINGS = [
    "ranking member", "the ranking", "vice chair", "ex officio",
    "presiding", "members", "staff director", "chief counsel",
]

def extract_chair(text):
    """Extract committee chair, rejecting known false positive patterns."""
    patterns = [
        r"(?:Chairman|Chairwoman|Chair)\s+(Sen\.|Rep\.)?\s*([\w\s]+?)\s*\([RD]",
        r"(?:Sen\.|Rep\.)\s+([\w\s]+),\s+(?:Chair|Chairman|Chairwoman)",
        r"Chaired by[:\s]+([\w\s,\.]+?)(?:\n|$)",
        r"Chair(?:man|woman)?[:\s]+([\w\s]+?)(?:\n|,|\.|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            chair = match.group(match.lastindex).strip().strip(".,")
            # Reject false positives
            if any(bad in chair.lower() for bad in BAD_CHAIR_STRINGS):
                continue
            if 5 < len(chair) < 60:
                return chair
    return ""

def extract_pdf_witnesses(pdf_bytes):
    """Extract witness names from a PDF byte string."""
    if not HAS_PDF:
        return []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = "\n".join(
                (page.extract_text() or "") for page in pdf.pages[:5]
            )
        return extract_witnesses(text)
    except:
        return []

def building_from_room(room):
    mapping = {"SR": "Russell (SR)", "SD": "Dirksen (SD)",
               "SH": "Hart (SH)", "SV": "Capitol Visitor Center",
               "S-": "Capitol (Senate)"}
    for k, v in mapping.items():
        if room.startswith(k):
            return v
    return "Dirksen (SD)"

def house_building_from_room(room):
    if "LHOB" in room:  return "Longworth (LHOB)"
    if "CHOB" in room:  return "Cannon (CHOB)"
    if "RHOB" in room:  return "Rayburn (RHOB)"
    if room.startswith("H-") or room.startswith("H "): return "Capitol"
    return "Rayburn (RHOB)"

def load_json(path):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except:
            pass
    return {}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def norm_time(t):
    return re.sub(r"\s*(ET|EDT|EST)\s*$", "", str(t)).strip().upper().replace(" ", "")

def norm_cmte(c):
    """
    Aggressively normalize committee names so that variations from
    different sources all reduce to the same string.
    e.g. "Senate Committee on Commerce, Science, and Transportation"
         "Commerce, Science & Transportation"
         "Senate Commerce, Science, and Transportation Subcommittee on Aviation"
    all normalize similarly enough to match.
    """
    s = str(c).lower()
    # Remove common prefixes
    for prefix in [
        "united states senate committee on the",
        "united states senate committee on",
        "senate committee on the",
        "senate committee on",
        "house committee on the",
        "house committee on",
        "subcommittee on the",
        "subcommittee on",
        "u.s. senate committee on",
        "u.s. house committee on",
        "committee on the",
        "committee on",
        "permanent select committee on",
        "select committee on",
        "special committee on",
        "joint committee on",
        "caucus on",
    ]:
        if s.startswith(prefix):
            s = s[len(prefix):].strip()
            break
    # Normalize punctuation and conjunctions
    s = s.replace("&", "and")
    s = s.replace(",", " ")
    s = s.replace(".", " ")
    s = s.replace("-", " ")
    # Remove all non-alphanumeric except spaces
    s = re.sub(r"[^a-z0-9 ]", "", s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s

def cmte_similarity(c1, c2):
    """
    Returns True if two committee name strings are similar enough
    to be considered the same committee.
    Uses multiple strategies to handle prefix/suffix differences.
    """
    n1, n2 = norm_cmte(c1), norm_cmte(c2)
    if not n1 or not n2:
        return False
    # Exact match after normalization
    if n1 == n2:
        return True
    # One contains the other (handles "Commerce" vs "Commerce Science Transportation")
    if n1 in n2 or n2 in n1:
        return True
    # First N characters match (handles trailing subcommittee info)
    min_len = min(len(n1), len(n2))
    if min_len >= 8 and n1[:min_len//2] == n2[:min_len//2]:
        return True
    # Word overlap — if 60%+ of shorter string's words appear in longer
    w1, w2 = set(n1.split()), set(n2.split())
    if not w1 or not w2:
        return False
    shorter = w1 if len(w1) <= len(w2) else w2
    longer  = w1 if len(w1) > len(w2) else w2
    # Ignore very common words
    stop = {"the", "and", "of", "on", "for", "in", "to", "a", "an"}
    shorter_content = shorter - stop
    if not shorter_content:
        return False
    overlap = len(shorter_content & longer) / len(shorter_content)
    return overlap >= 0.6

def fuzzy_match(h1, h2):
    """Match two hearings if they're the same event from different sources."""
    # Must be same chamber (Joint can match Senate for JEC etc.)
    if h1["chamber"] != h2["chamber"]:
        # Allow Joint to match Senate
        chambers = {h1["chamber"], h2["chamber"]}
        if not (chambers <= {"Senate", "Joint"}):
            return False
    t1, t2 = norm_time(h1["time"]), norm_time(h2["time"])
    time_ok = t1 == t2 or t1[:5] == t2[:5] or t1 == "TBD" or t2 == "TBD"
    cmte_ok = cmte_similarity(h1["committee"], h2["committee"])
    return time_ok and cmte_ok

def diff_hearing(old, new):
    changes = []
    if old.get("time") != new.get("time"):
        changes.append(f"Time changed to {new.get('time','TBD')}")
    if old.get("room") != new.get("room"):
        changes.append(f"Room changed to {new.get('room','TBD')}")
    if old.get("building") != new.get("building"):
        changes.append(f"Location changed to {new.get('building','TBD')}")
    old_w = set(old.get("witnesses", []))
    new_w = set(new.get("witnesses", []))
    added = new_w - old_w - {"Witnesses not yet publicly posted",
                              "Not yet posted", "Closed session — witnesses not publicly disclosed"}
    if added:
        preview = ", ".join(list(added)[:2])
        extra   = f" +{len(added)-2} more" if len(added) > 2 else ""
        changes.append(f"Witness{'es' if len(added)>1 else ''} added: {preview}{extra}")
    if not old.get("cancelled") and new.get("cancelled"):
        changes.append("CANCELLED")
    return changes

# ── DataTables show-all helper ─────────────────────────────────────────────────
async def datatables_show_all(page):
    """
    Multiple strategies to make senate.gov's DataTables show every row.
    Tries them in sequence — first one that works wins.
    """
    strategies = [
        # Strategy 1: Select -1 (All) from the length dropdown
        """
        (function() {
            const sel = document.querySelector(
                'select[name$="_length"], .dataTables_length select, select');
            if (!sel) return 'no_select';
            const opts = Array.from(sel.options).map(o => o.value);
            const best = ['-1','200','100','50'].find(v => opts.includes(v));
            if (best) { sel.value = best; sel.dispatchEvent(new Event('change',{bubbles:true})); return best; }
            return 'no_match';
        })()
        """,
        # Strategy 2: Call DataTable API directly via jQuery
        """
        (function() {
            try {
                if (typeof jQuery !== 'undefined') {
                    jQuery('table').each(function() {
                        try { jQuery(this).DataTable().page.len(-1).draw(); } catch(e) {}
                    });
                    return 'jquery_ok';
                }
                return 'no_jquery';
            } catch(e) { return 'error:' + e.message; }
        })()
        """,
        # Strategy 3: Force all hidden rows to display via CSS
        """
        (function() {
            let shown = 0;
            document.querySelectorAll('table tbody tr').forEach(r => {
                if (r.style.display === 'none' || r.classList.contains('odd') || r.classList.contains('even')) {
                    r.style.display = '';
                    shown++;
                }
            });
            return 'forced:' + shown;
        })()
        """,
    ]
    for i, strategy in enumerate(strategies):
        try:
            result = await page.evaluate(strategy)
            print(f"  DataTables strategy {i+1}: {result}")
            if str(result) not in ['no_select', 'no_match', 'no_jquery', 'forced:0']:
                await asyncio.sleep(3)
                return True
        except Exception as e:
            print(f"  DataTables strategy {i+1} error: {e}")
    await asyncio.sleep(2)
    return False

# ── Main scraper ───────────────────────────────────────────────────────────────
async def scrape():
    scraped         = []
    witness_cache   = {}
    chair_cache     = {}
    cancelled_cache = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=HEADERS["User-Agent"])

        # ── House — docs.house.gov ────────────────────────────────────────────
        try:
            page = await context.new_page()
            await page.goto(
                f"https://docs.house.gov/Committee/Calendar/ByDay.aspx?DayID={today_id}",
                wait_until="networkidle", timeout=30000)
            await page.wait_for_selector("table", timeout=15000)
            await asyncio.sleep(2)

            rows = await page.query_selector_all("table tr")
            for row in rows:
                cells = await row.query_selector_all("td")
                if len(cells) < 3:
                    continue
                title_text = (await cells[0].inner_text()).strip()
                time_text  = (await cells[1].inner_text()).strip()
                loc_text   = (await cells[2].inner_text()).strip()
                lines = [l.strip() for l in title_text.split("\n") if l.strip()]
                if len(lines) < 2:
                    continue
                topic     = lines[0].strip('"""\u201c\u201d')
                committee = lines[1]
                scraped.append({
                    "chamber":   "House",
                    "committee": committee,
                    "chair":     "",
                    "time":      f"{time_text} ET" if time_text else "TBD",
                    "building":  house_building_from_room(loc_text),
                    "room":      loc_text if loc_text else "Closed",
                    "topic":     topic,
                    "witnesses": [],
                    "details":   "",
                    "cancelled": detect_cancellation(topic),
                    "changes":   [],
                })
            await page.close()
            print(f"✅ House: {sum(1 for h in scraped if h['chamber']=='House')} hearings")
        except Exception as e:
            print(f"❌ House: {e}")

        # ── Senate — senate.gov with multi-strategy show-all ─────────────────
        senate_from_main = []
        try:
            page = await context.new_page()
            await page.goto(
                "https://www.senate.gov/committees/hearings_meetings.htm",
                wait_until="networkidle", timeout=30000)
            try:
                await page.wait_for_selector(
                    "select, .dataTables_length, table tbody tr td",
                    timeout=15000)
            except:
                pass
            await asyncio.sleep(3)

            # Try all DataTables show-all strategies
            await datatables_show_all(page)

            full_text = await page.inner_text("body")
            print(f"Senate today found: {is_today(full_text)}")
            rows = await page.query_selector_all("table tr")
            print(f"Senate rows after show-all: {len(rows)}")

            seen_senate = set()
            for row in rows:
                text = await row.inner_text()
                if not is_today(text):
                    continue
                cells = await row.query_selector_all("td")
                if len(cells) < 2:
                    continue
                cell_texts = [(await c.inner_text()).strip() for c in cells]
                date_cell  = cell_texts[0] if cell_texts else ""
                cmte_cell  = cell_texts[1] if len(cell_texts) > 1 else ""
                topic_cell = cell_texts[2] if len(cell_texts) > 2 else ""

                time_match = re.search(r"(\d{1,2}:\d{2}\s*[AP]M)", date_cell, re.IGNORECASE)
                room_match = re.search(r"([A-Z]{1,3}-[\w]+)", date_cell)
                time_val   = time_match.group(1).strip() if time_match else "TBD"
                room_val   = room_match.group(1).strip() if room_match else "TBD"

                cmte_lines = [l.strip() for l in cmte_cell.split("\n") if l.strip()]
                committee  = cmte_lines[0] if cmte_lines else cmte_cell.strip()
                sub        = cmte_lines[1] if len(cmte_lines) > 1 else ""
                full_cmte  = f"{committee} — {sub}" if sub else committee

                if not full_cmte or full_cmte == "—":
                    continue

                dk = f"{full_cmte[:25]}|{time_val}"
                if dk in seen_senate:
                    continue
                seen_senate.add(dk)

                topic   = topic_cell.strip()[:200]

                # Skip placeholder "no hearings" rows from senate.gov
                PLACEHOLDER_PHRASES = [
                    "no committee hearings scheduled",
                    "no hearings scheduled",
                    "no hearings",
                    "committee recess",
                    "congress in recess",
                ]
                if any(p in full_cmte.lower() or p in topic.lower()
                       for p in PLACEHOLDER_PHRASES):
                    print(f"  ⏭️  Skipping placeholder: {full_cmte}")
                    continue

                chamber = "Joint" if any(x in full_cmte for x in
                          ["Joint Economic", "Joint Committee", "Caucus"]) else "Senate"

                senate_from_main.append({
                    "chamber":   chamber,
                    "committee": full_cmte,
                    "chair":     "",
                    "time":      f"{time_val} ET",
                    "building":  building_from_room(room_val),
                    "room":      room_val,
                    "topic":     topic,
                    "witnesses": [],
                    "details":   topic,
                    "cancelled": detect_cancellation(topic),
                    "changes":   [],
                })
                print(f"  Senate: {full_cmte} | {time_val} | {room_val}")

            await page.close()
            print(f"✅ Senate main: {len(senate_from_main)} hearings")
        except Exception as e:
            print(f"❌ Senate main: {e}")

        scraped.extend(senate_from_main)

        # ── Committee pages — witnesses, chairs, PDFs, cancellations ─────────
        for chamber_label, pages_list in [("Senate", SENATE_COMMITTEE_PAGES),
                                           ("House",  HOUSE_COMMITTEE_PAGES)]:
            for name, url in pages_list:
                try:
                    page = await context.new_page()
                    await page.goto(url, wait_until="networkidle", timeout=20000)
                    await asyncio.sleep(1)
                    text = await page.inner_text("body")

                    if not is_today(text):
                        await page.close()
                        continue

                    print(f"  📋 {chamber_label} {name}: today found")

                    # Smart cancellation — only flag if near today's date
                    if detect_cancellation_near_date(text):
                        cancelled_cache.add(name.lower())
                        print(f"  ⚠️  Cancellation: {name}")

                    # Witnesses from page text
                    witnesses = extract_witnesses(text)
                    if witnesses:
                        witness_cache[name.lower()] = witnesses
                        print(f"  👤 {name}: {len(witnesses)} witnesses")

                    # Chair — with false positive rejection
                    chair = extract_chair(text)
                    if chair:
                        chair_cache[name.lower()] = chair
                        print(f"  🪑 {name}: {chair}")

                    # PDF witness lists
                    if HAS_PDF and HAS_REQUESTS:
                        pdf_links = await page.query_selector_all(
                            "a[href$='.pdf'], a[href*='witness'], a[href*='Witness']")
                        for link in pdf_links[:3]:
                            try:
                                pdf_url = await link.get_attribute("href")
                                if not pdf_url:
                                    continue
                                if not pdf_url.startswith("http"):
                                    base = "/".join(url.split("/")[:3])
                                    pdf_url = base + ("" if pdf_url.startswith("/") else "/") + pdf_url
                                r = req_lib.get(pdf_url, headers=HEADERS, timeout=10)
                                if r.status_code == 200:
                                    pdf_witnesses = extract_pdf_witnesses(r.content)
                                    if pdf_witnesses:
                                        existing = witness_cache.get(name.lower(), [])
                                        witness_cache[name.lower()] = list(
                                            dict.fromkeys(existing + pdf_witnesses))
                                        print(f"  📄 PDF: {name} +{len(pdf_witnesses)} witnesses")
                            except:
                                pass

                    await page.close()
                except Exception as e:
                    print(f"  ❌ {name}: {e}")
                    try:
                        await page.close()
                    except:
                        pass

        await browser.close()

    # ── Apply enrichment ──────────────────────────────────────────────────────
    for h in scraped:
        cmte_lower = h["committee"].lower()
        for key, witnesses in witness_cache.items():
            if key in cmte_lower or any(w in cmte_lower for w in key.split()):
                if witnesses and not h["witnesses"]:
                    h["witnesses"] = witnesses
                    break
        for key, chair in chair_cache.items():
            if key in cmte_lower or any(w in cmte_lower for w in key.split()):
                if chair and not h["chair"]:
                    h["chair"] = chair
                    break
        for key in cancelled_cache:
            if key in cmte_lower or any(w in cmte_lower for w in key.split()):
                h["cancelled"] = True
                break

    # ── Global deduplication of scraped list ──────────────────────────────────
    # Different sources (senate.gov, committee pages, congress.gov) can return
    # the same hearing with slightly different committee name strings.
    # We keep the "best" version — the one with the most data.
    deduped = []
    for h in scraped:
        # Check if this hearing already exists in deduped
        match = next((d for d in deduped if fuzzy_match(h, d)), None)
        if match:
            # Merge: keep whichever has more data per field
            if len(h.get("topic", "")) > len(match.get("topic", "")):
                match["topic"] = h["topic"]
            if len(h.get("details", "")) > len(match.get("details", "")):
                match["details"] = h["details"]
            if h.get("chair") and not match.get("chair"):
                match["chair"] = h["chair"]
            if h.get("witnesses") and not match.get("witnesses"):
                match["witnesses"] = h["witnesses"]
            elif h.get("witnesses") and match.get("witnesses"):
                # Merge witness lists
                existing = set(match["witnesses"])
                new_w    = set(h["witnesses"])
                match["witnesses"] = list(existing | new_w)
            if h.get("room") and h["room"] != "TBD" and match.get("room") == "TBD":
                match["room"]     = h["room"]
                match["building"] = h["building"]
            if h.get("cancelled"):
                match["cancelled"] = True
            print(f"  🔀 Dedup merged: {h['committee'][:50]}")
        else:
            deduped.append(h)

    scraped = deduped
    print(f"  After dedup: {len(scraped)} unique hearings")

    # ── Merge with baseline ───────────────────────────────────────────────────
    baseline      = load_json(BASELINE_FILE)
    tomorrow_iso  = (now_et + timedelta(days=1)).strftime("%Y-%m-%d")
    baseline_date = baseline.get("date", "")
    baseline_valid = baseline_date in [today_iso, tomorrow_iso]

    merged = []

    if baseline_valid and baseline.get("hearings"):
        print(f"✅ Baseline found for {baseline_date} — merging {len(baseline['hearings'])} hearings")
        for h in baseline.get("hearings", []):
            scraped_match = next((s for s in scraped if fuzzy_match(h, s)), None)

            if scraped_match:
                enriched = dict(h)
                if norm_time(scraped_match["time"]) not in ["TBD", ""]:
                    if scraped_match["time"] != h["time"]:
                        enriched["time"] = scraped_match["time"]
                if scraped_match["room"] not in ["TBD", "", "Closed"]:
                    enriched["room"]     = scraped_match["room"]
                    enriched["building"] = scraped_match["building"]
                existing_w = set(h.get("witnesses", []))
                new_w      = set(scraped_match.get("witnesses", []))
                merged_w   = list(existing_w | new_w)
                enriched["witnesses"] = merged_w if merged_w else h.get("witnesses", [])
                if scraped_match.get("chair") and not h.get("chair"):
                    enriched["chair"] = scraped_match["chair"]
                # Apply hardcoded chair if still missing
                if not enriched.get("chair"):
                    hardcoded = lookup_chair(enriched["committee"])
                    if hardcoded:
                        enriched["chair"] = hardcoded
                if scraped_match.get("cancelled"):
                    enriched["cancelled"] = True
                enriched["changes"] = h.get("changes", [])
                merged.append(enriched)
            else:
                kept = dict(h)
                kept["changes"] = h.get("changes", [])
                # Apply hardcoded chair if missing
                if not kept.get("chair"):
                    hardcoded = lookup_chair(kept["committee"])
                    if hardcoded:
                        kept["chair"] = hardcoded
                merged.append(kept)
                print(f"  📌 Kept from baseline: {h['committee']}")

        # Add new hearings found by scraper not in baseline
        for s in scraped:
            if not any(fuzzy_match(s, m) for m in merged):
                if not s.get("chair"):
                    hardcoded = lookup_chair(s["committee"])
                    if hardcoded:
                        s["chair"] = hardcoded
                merged.append(s)
                print(f"  ➕ New from scraper: {s['committee']}")
    else:
        print(f"⚠️  No valid baseline — using scraped data only")
        merged = scraped

    # ── Change detection ──────────────────────────────────────────────────────
    snapshot = load_json(SNAPSHOT_FILE)
    for h in merged:
        key = hearing_key(h)
        if key in snapshot:
            old     = snapshot[key]
            changes = diff_hearing(old, h)
            if changes:
                new_stamps = [f"{c} · {change_time}" for c in changes]
                existing   = old.get("changes", [])
                h["changes"] = existing + [s for s in new_stamps if s not in existing]
                print(f"  🔄 {h['committee']}: {changes}")
            else:
                h["changes"] = old.get("changes", [])

    save_json(SNAPSHOT_FILE, {hearing_key(h): h for h in merged})

    # Sort
    def sort_key(h):
        order = {"Senate": 0, "House": 1, "Joint": 2}
        return (order.get(h["chamber"], 3), h.get("time", ""))
    merged.sort(key=sort_key)

    sc = sum(1 for h in merged if h["chamber"] == "Senate")
    hc = sum(1 for h in merged if h["chamber"] == "House")
    jc = sum(1 for h in merged if h["chamber"] == "Joint")
    print(f"\n📊 Total: {len(merged)} ({sc} Senate · {hc} House · {jc} Joint)")
    return merged

# ── Build HTML ─────────────────────────────────────────────────────────────────
def build_html(hearings):
    # Filter out placeholder "no hearing scheduled" entries
    PLACEHOLDER_PHRASES = [
        "no committee hearing scheduled",
        "no hearings scheduled",
        "no hearings",
        "committee recess",
        "congress in recess",
    ]
    def is_placeholder(h):
        topic = h.get("topic", "").lower()
        committee = h.get("committee", "").lower()
        return any(p in topic or p in committee for p in PLACEHOLDER_PHRASES)

    real_hearings = [h for h in hearings if not is_placeholder(h)]

    sc = sum(1 for h in real_hearings if h["chamber"] == "Senate")
    hc = sum(1 for h in real_hearings if h["chamber"] == "House")
    jc = sum(1 for h in real_hearings if h["chamber"] == "Joint")
    tc = len(real_hearings)
    ac = sum(1 for h in real_hearings if not h.get("cancelled"))
    hearings = real_hearings
    hearings_json = json.dumps(hearings, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="manifest" href="/hearing-tracker/manifest.json">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<link rel="apple-touch-icon" href="/hearing-tracker/icons/icon-192.png">
<title>Congressional Hearing Tracker — {today_str}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;700&family=IBM+Plex+Sans:wght@300;400;600;700&family=Playfair+Display:wght@700&display=swap" rel="stylesheet">
<style>
  /* ── CSS custom properties — dark mode (default) ── */
  :root {{
    --bg:           #0D0C0A;
    --bg-secondary: #111009;
    --bg-card:      rgba(255,255,255,0.03);
    --bg-card-open: rgba(255,255,255,0.06);
    --bg-header:    rgba(200,169,110,0.04);
    --bg-source:    rgba(255,255,255,0.02);

    --text-primary:   #F0E8D8;
    --text-heading:   #FAF4EA;
    --text-secondary: #C8B89A;
    --text-muted:     #A09070;
    --text-dim:       #807050;
    --text-faint:     #504030;

    --border:         rgba(255,255,255,0.1);
    --border-header:  rgba(200,169,110,0.3);
    --border-stat:    rgba(255,255,255,0.07);
    --border-filter:  rgba(255,255,255,0.08);
    --border-source:  rgba(255,255,255,0.07);
    --border-body:    rgba(255,255,255,0.08);
    --scrollbar:      #2A2820;

    --gold:   #E0B870;
    --blue:   #6BB8E8;
    --purple: #C4A0F0;

    --senate-bg:     rgba(220,180,80,0.15);
    --senate-border: rgba(220,180,80,0.45);
    --senate-accent: rgba(220,180,80,0.6);
    --house-bg:      rgba(80,160,220,0.13);
    --house-border:  rgba(80,160,220,0.40);
    --house-accent:  rgba(80,160,220,0.55);
    --joint-bg:      rgba(180,120,240,0.13);
    --joint-border:  rgba(180,120,240,0.40);
    --joint-accent:  rgba(180,120,240,0.55);

    --toggle-bg:     rgba(255,255,255,0.08);
    --toggle-border: rgba(255,255,255,0.16);
    --toggle-icon:   '☀️';
  }}

  /* ── Light mode overrides ── */
  :root.light {{
    --bg:           #F5F3EE;
    --bg-secondary: #EAE7DF;
    --bg-card:      rgba(255,255,255,0.85);
    --bg-card-open: rgba(255,255,255,1);
    --bg-header:    rgba(200,169,110,0.08);
    --bg-source:    rgba(0,0,0,0.03);

    --text-primary:   #0E0C0A;
    --text-heading:   #050403;
    --text-secondary: #3A3020;
    --text-muted:     #5A4A35;
    --text-dim:       #7A6A55;
    --text-faint:     #A09080;

    --border:         rgba(0,0,0,0.12);
    --border-header:  rgba(180,130,50,0.4);
    --border-stat:    rgba(0,0,0,0.08);
    --border-filter:  rgba(0,0,0,0.08);
    --border-source:  rgba(0,0,0,0.06);
    --border-body:    rgba(0,0,0,0.07);
    --scrollbar:      #D0C8BC;

    --senate-bg:     rgba(200,169,110,0.12);
    --senate-border: rgba(180,140,80,0.4);
    --senate-accent: rgba(180,140,80,0.6);
    --house-bg:      rgba(60,130,180,0.08);
    --house-border:  rgba(60,130,180,0.3);
    --house-accent:  rgba(60,130,180,0.5);
    --joint-bg:      rgba(120,80,180,0.08);
    --joint-border:  rgba(120,80,180,0.3);
    --joint-accent:  rgba(120,80,180,0.5);

    --toggle-bg:     rgba(0,0,0,0.05);
    --toggle-border: rgba(0,0,0,0.12);
    --toggle-icon:   '🌙';
  }}

  /* ── System preference default (runs before JS) ── */
  @media (prefers-color-scheme: light) {{
    :root:not(.dark) {{
      --bg:           #F5F3EE;
      --bg-secondary: #EDEAE3;
      --bg-card:      rgba(255,255,255,0.7);
      --bg-card-open: rgba(255,255,255,0.95);
      --bg-header:    rgba(200,169,110,0.06);
      --bg-source:    rgba(0,0,0,0.03);
      --text-primary:   #1A1714;
      --text-heading:   #0E0C0A;
      --text-secondary: #5A5040;
      --text-muted:     #7A6A58;
      --text-dim:       #9A8A78;
      --text-faint:     #C0B0A0;
      --border:         rgba(0,0,0,0.08);
      --border-header:  rgba(200,169,110,0.3);
      --border-stat:    rgba(0,0,0,0.06);
      --border-filter:  rgba(0,0,0,0.06);
      --border-source:  rgba(0,0,0,0.06);
      --border-body:    rgba(0,0,0,0.07);
      --scrollbar:      #D0C8BC;
      --senate-bg:     rgba(200,169,110,0.12);
      --senate-border: rgba(180,140,80,0.4);
      --senate-accent: rgba(180,140,80,0.6);
      --house-bg:      rgba(60,130,180,0.08);
      --house-border:  rgba(60,130,180,0.3);
      --house-accent:  rgba(60,130,180,0.5);
      --joint-bg:      rgba(120,80,180,0.08);
      --joint-border:  rgba(120,80,180,0.3);
      --joint-accent:  rgba(120,80,180,0.5);
      --toggle-bg:     rgba(0,0,0,0.05);
      --toggle-border: rgba(0,0,0,0.12);
    }}
  }}

  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: var(--bg);
    color: var(--text-primary);
    font-family: 'IBM Plex Sans', sans-serif;
    min-height: 100vh;
    transition: background 0.2s, color 0.2s;
  }}

  ::-webkit-scrollbar {{ width: 4px; }}
  ::-webkit-scrollbar-thumb {{ background: var(--scrollbar); border-radius: 2px; }}

  .header {{
    border-bottom: 1px solid var(--border-header);
    padding: 20px 20px 0;
    background: var(--bg-header);
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
  }}
  .header-left {{ flex: 1; margin-bottom: 14px; }}
  .header-eyebrow {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 10px; letter-spacing: 0.18em;
    color: var(--gold); text-transform: uppercase; margin-bottom: 6px;
  }}
  .header h1 {{
    font-family: 'Playfair Display', serif;
    font-size: clamp(20px,5vw,26px); font-weight: 700;
    color: var(--text-heading); letter-spacing: -0.01em; margin-bottom: 6px;
  }}
  .header-timestamp {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 10px; color: var(--text-muted); letter-spacing: 0.04em; line-height: 1.5;
  }}

  /* ── Theme toggle button ── */
  .theme-toggle {{
    background: var(--toggle-bg);
    border: 1px solid var(--toggle-border);
    border-radius: 8px;
    padding: 7px 10px;
    cursor: pointer;
    font-size: 16px;
    line-height: 1;
    flex-shrink: 0;
    margin-left: 12px;
    margin-top: 2px;
    transition: background 0.15s, border-color 0.15s;
  }}
  .theme-toggle:hover {{
    background: rgba(200,169,110,0.1);
    border-color: rgba(200,169,110,0.3);
  }}

  /* ── Stats ── */
  .stats {{ display: flex; border-bottom: 1px solid var(--border-filter); background: var(--bg-secondary); }}
  .stat {{ flex: 1; padding: 12px 8px; text-align: center; border-right: 1px solid var(--border-stat); }}
  .stat-number {{ font-family: 'Playfair Display', serif; font-size: 20px; font-weight: 700; line-height: 1; }}
  .stat-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 9px; letter-spacing: 0.1em; color: var(--text-dim); text-transform: uppercase; margin-top: 3px; }}

  /* ── Filters ── */
  .filters {{ display: flex; gap: 6px; padding: 12px 16px; border-bottom: 1px solid var(--border-filter); flex-wrap: wrap; }}
  .filter-btn {{
    background: transparent; border: 1px solid var(--border);
    color: var(--text-muted); border-radius: 6px; padding: 5px 12px;
    font-size: 11px; font-family: 'IBM Plex Mono', monospace;
    letter-spacing: 0.06em; cursor: pointer; transition: all 0.2s ease-out;
  }}
  .filter-btn.active {{
    background: var(--senate-bg);
    border-color: var(--senate-border);
    color: var(--gold);
    transform: scale(1.03);
  }}
  .filter-btn:hover:not(.active) {{ background: rgba(255,255,255,0.04); color: var(--text-primary); }}

  /* ── Cards ── */
  .cards {{ padding: 14px 16px; }}
  .count-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: var(--text-dim); letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 12px; }}

  .card {{
    border: 1px solid var(--border); border-radius: 12px;
    padding: 14px 16px; cursor: pointer; margin-bottom: 9px;
    background: var(--bg-card);
    transition: background 0.2s ease-out, transform 0.2s ease-out, box-shadow 0.2s ease-out;
    box-shadow: 0 1px 3px rgba(0,0,0,0.2);
  }}
  .card:hover {{ transform: translateY(-1px); box-shadow: 0 4px 10px rgba(0,0,0,0.25); }}
  .card.open {{ background: var(--bg-card-open); }}
  .card.cancelled {{ opacity: 0.5; }}
  .card.cancelled .card-committee {{ text-decoration: line-through; }}
  .card.has-changes {{ border-top: 2px solid rgba(255,200,50,0.5); }}

  .chamber-senate {{ border-left: 3px solid var(--senate-accent); }}
  .chamber-house  {{ border-left: 3px solid var(--house-accent); }}
  .chamber-joint  {{ border-left: 3px solid var(--joint-accent); }}

  .card-top {{ display: flex; gap: 10px; justify-content: space-between; align-items: flex-start; }}
  .card-left {{ flex: 1; min-width: 0; }}
  .card-meta {{ display: flex; align-items: center; gap: 7px; margin-bottom: 5px; flex-wrap: wrap; }}

  .tag {{ border-radius: 4px; font-size: 10px; font-weight: 700; letter-spacing: 0.08em; padding: 2px 7px; text-transform: uppercase; font-family: 'IBM Plex Mono', monospace; flex-shrink: 0; }}
  .tag-senate {{ background: var(--senate-bg); color: var(--gold); border: 1px solid var(--senate-border); }}
  .tag-house  {{ background: var(--house-bg);  color: var(--blue); border: 1px solid var(--house-border); }}
  .tag-joint  {{ background: var(--joint-bg);  color: var(--purple); border: 1px solid var(--joint-border); }}
  .tag-cancelled {{ background: rgba(200,60,60,0.15); color: #E07070; border: 1px solid rgba(200,60,60,0.3); }}

  .card-time {{ font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: var(--text-secondary); letter-spacing: 0.04em; }}
  .card-committee {{ font-size: 13px; font-weight: 600; color: var(--text-primary); line-height: 1.4; margin-bottom: 3px; }}
  .card-topic {{ font-size: 12px; color: var(--text-secondary); line-height: 1.4; }}
  .card-right {{ text-align: right; min-width: 96px; flex-shrink: 0; }}
  .card-building {{ font-family: 'IBM Plex Mono', monospace; font-size: 11px; margin-bottom: 2px; }}
  .card-room {{ font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: var(--text-muted); }}

  .bc-senate {{ color: var(--gold); }}
  .bc-house  {{ color: var(--blue); }}
  .bc-joint  {{ color: var(--purple); }}

  .change-pills {{ display: flex; flex-wrap: wrap; gap: 4px; margin-top: 7px; }}
  .change-pill {{ font-family: 'IBM Plex Mono', monospace; font-size: 9px; letter-spacing: 0.05em; padding: 2px 7px; border-radius: 10px; background: rgba(255,200,50,0.1); color: #E0B830; border: 1px solid rgba(255,200,50,0.25); }}
  .change-pill.cancelled-pill {{ background: rgba(200,60,60,0.12); color: #E07070; border-color: rgba(200,60,60,0.3); }}

  .card-body {{ margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border-body); display: none; }}
  .card.open .card-body {{ display: block; }}
  .card-section {{ margin-bottom: 10px; }}
  .card-section-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 5px; }}
  .card-section-value {{ font-size: 12px; color: var(--text-secondary); line-height: 1.65; }}

  .sl-senate {{ color: var(--gold); }}
  .sl-house  {{ color: var(--blue); }}
  .sl-joint  {{ color: var(--purple); }}

  .witness {{ font-size: 12px; color: var(--text-secondary); line-height: 1.5; padding-left: 10px; margin-bottom: 4px; }}
  .wb-senate {{ border-left: 2px solid var(--senate-accent); }}
  .wb-house  {{ border-left: 2px solid var(--house-accent); }}
  .wb-joint  {{ border-left: 2px solid var(--joint-accent); }}

  .source-note {{
    margin-top: 20px; padding: 12px 14px;
    background: var(--bg-source); border: 1px solid var(--border-source);
    border-radius: 6px; font-family: 'IBM Plex Mono', monospace;
    font-size: 10px; color: var(--text-dim); line-height: 1.6;
  }}
  .empty {{ text-align: center; padding: 40px; color: var(--text-faint); font-size: 13px; }}

/* ---- DomeWatch sections ---- */
.dw-section {{
  margin:1.5rem 1rem;padding:1.25rem 1.5rem;
  border:1px solid rgba(255,255,255,0.08);border-radius:8px;
  background:rgba(255,255,255,0.02);
}}
.dw-heading {{
  font-size:0.9rem;font-weight:600;margin:0 0 0.85rem;
  display:flex;align-items:center;gap:0.4rem;color:var(--text-primary,#F0E8D8);
}}
.dw-heading-sub {{ font-size:0.72rem;font-weight:400;color:var(--text-dim,#A09070);margin-left:auto; }}
.whip-meta {{ font-size:0.78rem;color:var(--text-secondary,#C8B89A);margin-bottom:0.85rem;display:flex;gap:1.2rem;flex-wrap:wrap; }}
.whip-items {{ display:flex;flex-direction:column;gap:0.6rem; }}
.whip-item {{
  padding:0.65rem 0.9rem;border-radius:5px;
  border:1px solid rgba(255,255,255,0.06);background:rgba(255,255,255,0.02);
}}
.whip-item__bill {{ font-family:'IBM Plex Mono',monospace;font-size:0.76rem;color:var(--gold,#E0B870); }}
.whip-item__title {{ font-size:0.85rem;margin:0.15rem 0; }}
.whip-item__meta {{ font-size:0.73rem;color:var(--text-dim,#A09070);display:flex;gap:0.8rem;flex-wrap:wrap;margin-top:0.25rem; }}
.wrec {{ font-weight:700;padding:0.1rem 0.35rem;border-radius:3px;font-size:0.68rem; }}
.wrec-YES {{ background:#1b5e20;color:#a5d6a7; }}
.wrec-NO  {{ background:#b71c1c;color:#ef9a9a; }}
.floor-updates-list {{ display:flex;flex-direction:column;gap:0.5rem; }}
.floor-update {{
  padding:0.6rem 0.85rem;border-radius:4px;
  border-left:3px solid var(--gold,#E0B870);
  background:rgba(255,255,255,0.02);font-size:0.83rem;
}}
.floor-update__subject {{ font-weight:600;margin-bottom:0.15rem; }}
.floor-update__body    {{ color:var(--text-secondary,#C8B89A);font-size:0.8rem;line-height:1.5; }}
.floor-update__time    {{ color:var(--text-dim,#A09070);font-size:0.7rem;margin-top:0.25rem;font-family:'IBM Plex Mono',monospace; }}
</style>
</head>
<body>


<div class="header">
  <div class="header-left">
    <div class="header-eyebrow">🏛 Congressional Hearing Tracker</div>
    <h1>Today's Hearings</h1>
    <div class="header-timestamp">As of {generated} · {today_long} · Updates every 20 min · Schedules subject to change.</div>
  </div>
  <button class="theme-toggle" id="theme-toggle" onclick="toggleTheme()" title="Toggle light/dark mode">☀️</button>
</div>
<nav style="display:flex;gap:0;border-bottom:1px solid var(--border-section);background:var(--bg-secondary);padding:0 4px;">
  <a href="index.html" style="font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:0.08em;color:var(--gold);text-decoration:none;padding:10px 14px;border-bottom:2px solid var(--gold);">Hearings</a>
  <a href="members.html" style="font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:0.08em;color:var(--text-muted);text-decoration:none;padding:10px 14px;border-bottom:2px solid transparent;">Members</a>
</nav>

<div class="stats">
  <div class="stat"><div class="stat-number" style="color:#6DBF8A">{ac}</div><div class="stat-label">Active</div></div>
  <div class="stat"><div class="stat-number" style="color:var(--text-secondary)">{tc}</div><div class="stat-label">Total</div></div>
  <div class="stat"><div class="stat-number" style="color:var(--gold)">{sc}</div><div class="stat-label">Senate</div></div>
  <div class="stat"><div class="stat-number" style="color:var(--blue)">{hc}</div><div class="stat-label">House</div></div>
  <div class="stat"><div class="stat-number" style="color:var(--purple)">{jc}</div><div class="stat-label">Joint</div></div>
</div>

<div class="filters">
  <button class="filter-btn active" onclick="setFilter('All')">All</button>
  <button class="filter-btn" onclick="setFilter('Senate')">Senate</button>
  <button class="filter-btn" onclick="setFilter('House')">House</button>
  <button class="filter-btn" onclick="setFilter('Joint')">Joint</button>
  <button class="filter-btn" onclick="setFilter('Updated')">⚡ Updated</button>
  <button class="filter-btn" onclick="setFilter('Cancelled')">✕ Cancelled</button>
</div>

<div class="cards">
  <div class="count-label" id="count-label"></div>
  <div id="card-list"></div>
  <div class="source-note">ℹ Auto-updated every 2 hrs · docs.house.gov · senate.gov · Individual committee pages</div>
</div>

<script>
const HEARINGS = {hearings_json};

// ── Theme system ──────────────────────────────────────────────────────────────
function getSystemTheme() {{
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}}

function applyTheme(theme) {{
  const root = document.documentElement;
  root.classList.remove('light', 'dark');
  root.classList.add(theme);
  const btn = document.getElementById('theme-toggle');
  btn.textContent = theme === 'dark' ? '☀️' : '🌙';
  btn.title = theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';
}}

function toggleTheme() {{
  const current = document.documentElement.classList.contains('light') ? 'light' : 'dark';
  const next = current === 'dark' ? 'light' : 'dark';
  localStorage.setItem('theme', next);
  applyTheme(next);
}}

// On load: use stored preference, or fall back to system
(function() {{
  const stored = localStorage.getItem('theme');
  applyTheme(stored || getSystemTheme());
}})();

// Listen for system theme changes (e.g. auto dark mode at sunset)
window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', e => {{
  if (!localStorage.getItem('theme')) {{
    applyTheme(e.matches ? 'light' : 'dark');
  }}
}});

// ── Cards ─────────────────────────────────────────────────────────────────────
function cls(c) {{ return c==='Senate'?'senate':c==='House'?'house':'joint'; }}

function buildCards(filter) {{
  // No hearings today at all
  if (!HEARINGS.length) {{
    document.getElementById('count-label').textContent = '0 hearings scheduled';
    document.getElementById('card-list').innerHTML =
      '<div class="empty" style="padding:60px 20px">'+
      '<div style="font-size:32px;margin-bottom:12px">🏛</div>'+
      '<div style="font-family:serif;font-size:18px;color:var(--text-muted);margin-bottom:8px">No hearings today</div>'+
      '<div style="font-size:12px;color:var(--text-dim)">Congress may be in recess or no committees are scheduled. Check back tomorrow.</div>'+
      '</div>';
    return;
  }}

  let filtered;
  if (filter==='All')           filtered = HEARINGS;
  else if (filter==='Updated')  filtered = HEARINGS.filter(h=>h.changes&&h.changes.length>0);
  else if (filter==='Cancelled')filtered = HEARINGS.filter(h=>h.cancelled);
  else filtered = HEARINGS.filter(h=>h.chamber===filter);

  document.getElementById('count-label').textContent =
    filtered.length+' hearing'+(filtered.length!==1?'s':'')+' — tap any card to expand';

  const list = document.getElementById('card-list');
  list.innerHTML = '';

  if (!filtered.length) {{
    list.innerHTML='<div class="empty">No '+(filter!=='All'?filter.toLowerCase()+' ':'')+'hearings found.</div>';
    return;
  }}

  filtered.forEach(h => {{
    const c = cls(h.chamber);
    const hasChanges = h.changes&&h.changes.length>0;
    const card = document.createElement('div');
    card.className = ['card','chamber-'+c,h.cancelled?'cancelled':'',hasChanges?'has-changes':''].filter(Boolean).join(' ');

    const pills = hasChanges
      ? '<div class="change-pills">'+h.changes.map(ch=>
          '<span class="change-pill'+(ch.toLowerCase().includes('cancel')?' cancelled-pill':'')+
          '">⚡ '+ch+'</span>').join('')+'</div>'
      : '';

    const chairVal = h.chair
      ? h.chair
      : '<span style="color:var(--text-faint);font-style:italic">Not yet posted</span>';

    const aboutHtml = (h.details && h.details.trim() &&
                       h.details.trim() !== h.topic.trim() &&
                       h.details.length > h.topic.length + 20)
      ? '<div class="card-section"><div class="card-section-label sl-'+c+'">About</div><div class="card-section-value">'+h.details+'</div></div>'
      : '';

    const witnessHtml = h.witnesses && h.witnesses.length &&
                        !h.witnesses.every(w=>w==='Witnesses not yet publicly posted')
      ? h.witnesses.map(w=>'<div class="witness wb-'+c+'">'+w+'</div>').join('')
      : '<div style="color:var(--text-faint);font-style:italic;font-size:12px;padding-left:10px">Not yet posted</div>';

    card.innerHTML = `
      <div class="card-top">
        <div class="card-left">
          <div class="card-meta">
            <span class="tag tag-${{c}}">${{h.chamber}}</span>
            ${{h.cancelled?'<span class="tag tag-cancelled">Cancelled</span>':''}}
            <span class="card-time">${{h.time}}</span>
          </div>
          <div class="card-committee">${{h.committee}}</div>
          <div class="card-topic">${{h.topic}}</div>
          ${{pills}}
        </div>
        <div class="card-right">
          <div class="card-building bc-${{c}}">${{h.building}}</div>
          <div class="card-room">${{h.room}}</div>
        </div>
      </div>
      <div class="card-body">
        <div class="card-section">
          <div class="card-section-label sl-${{c}}">Chair</div>
          <div class="card-section-value">${{chairVal}}</div>
        </div>
        ${{aboutHtml}}
        <div class="card-section">
          <div class="card-section-label sl-${{c}}">Witnesses</div>
          ${{witnessHtml}}
        </div>
      </div>`;

    card.addEventListener('click',()=>card.classList.toggle('open'));
    list.appendChild(card);
  }});
}}

function setFilter(f) {{
  document.querySelectorAll('.filter-btn').forEach(b=>
    b.classList.toggle('active',
      b.textContent.replace('⚡ ','').replace('✕ ','')===f||(f==='All'&&b.textContent==='All')));
  buildCards(f);
}}

buildCards('All');
</script>

<section id="whip-section" class="dw-section" style="display:none">
  <h2 class="dw-heading">Coming to the Floor <span class="dw-heading-sub">via DomeWatch Whip Notice</span></h2>
  <div id="whip-meta" class="whip-meta"></div>
  <div id="whip-items" class="whip-items"></div>
</section>
<section id="floor-updates-section" class="dw-section" style="display:none">
  <h2 class="dw-heading">Floor Updates <span class="dw-heading-sub">via DomeWatch</span></h2>
  <div id="floor-updates-list" class="floor-updates-list"></div>
</section>
<script>
// Read DomeWatch data from local JSON files (no CORS issues)
function fmtTime(iso) {{
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("en-US", {{hour:"numeric",minute:"2-digit",hour12:true}});
}}

function loadWhip() {{
  fetch("/hearing-tracker/domewatch_whip.json")
    .then(function(r) {{ return r.ok ? r.json() : null; }})
    .then(function(data) {{
      if (!data || !data.data || !data.data.length) return;
      var n   = data.data[0];
      var sec = document.getElementById("whip-section");
      var met = document.getElementById("whip-meta");
      var itm = document.getElementById("whip-items");
      if (!sec) return;
      var mh = "";
      if (n.houseMeetsAt) mh += "<span>&#128336; House meets: " + n.houseMeetsAt + "</span>";
      if (n.firstVotes)   mh += "<span>&#9889; First votes: " + n.firstVotes + "</span>";
      if (n.lastVotes)    mh += "<span>&#128276; Last votes: " + n.lastVotes + "</span>";
      met.innerHTML = mh;
      var bh = "";
      (n.items || []).filter(function(b) {{ return b.confidence !== "low"; }}).forEach(function(b) {{
        var rc = b.recommendation ? "wrec wrec-" + b.recommendation : "";
        bh += '<div class="whip-item">';
        if (b.billUrl) {{
          bh += '<a href="' + b.billUrl + '" target="_blank" rel="noopener" class="whip-item__bill">' + (b.billNumber || "") + "</a>";
        }} else {{
          bh += '<span class="whip-item__bill">' + (b.billNumber || "") + "</span>";
        }}
        if (b.title) bh += '<div class="whip-item__title">' + b.title + "</div>";
        bh += '<div class="whip-item__meta">';
        if (rc) bh += '<span class="' + rc + '">' + (b.recommendation || "").replace("_", " ") + "</span>";
        if (b.position) bh += "<span>" + b.position + "</span>";
        bh += "</div></div>";
      }});
      itm.innerHTML = bh || "<p>No upcoming vote items.</p>";
      sec.style.display = "block";
    }})
    .catch(function() {{}});
}}

function loadUpdates() {{
  fetch("/hearing-tracker/domewatch_updates.json")
    .then(function(r) {{ return r.ok ? r.json() : null; }})
    .then(function(data) {{
      if (!data || !data.data || !data.data.length) return;
      var sec = document.getElementById("floor-updates-section");
      var lst = document.getElementById("floor-updates-list");
      if (!sec) return;
      var h = "";
      data.data.forEach(function(u) {{
        h += '<div class="floor-update">';
        h += '<div class="floor-update__subject">' + (u.subject || "Floor Update") + "</div>";
        if (u.bodyText) h += '<div class="floor-update__body">' + u.bodyText + "</div>";
        h += '<div class="floor-update__time">' + fmtTime(u.publishedAt) + "</div>";
        h += "</div>";
      }});
      lst.innerHTML = h;
      sec.style.display = "block";
    }})
    .catch(function() {{}});
}}

document.addEventListener("DOMContentLoaded", function() {{
  loadWhip();
  loadUpdates();
}});
</script>
<script>
if ("serviceWorker" in navigator) {{
  window.addEventListener("load", function() {{
    navigator.serviceWorker.register("/hearing-tracker/sw.js")
      .catch(function(e) {{ console.warn("SW:", e); }});
  }});
}}
</script>
</body>
</html>"""

async def main():
    print(f"🗓  Scraping for {today_long} ({tz_label})...")
    hearings = await scrape()
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(build_html(hearings))
    print("✅ index.html written.")

asyncio.run(main())
