"""
Congressional Hearing Tracker — Nightly Baseline Builder
Runs at 9 PM ET every weekday via GitHub Actions.
Builds baseline.json for TOMORROW's hearings.

Sources (in priority order):
  1. docs.house.gov — House calendar (Playwright, per-day URL, authoritative)
  2. senate.gov     — Senate hearings page (Playwright, DataTables show-all)
  3. congress.gov   — Weekly schedule (Playwright, catches JEC + caucuses)
  4. 36 committee pages — witnesses, chairs, cancellations, PDF witness lists
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

# ── Timezone & dates ───────────────────────────────────────────────────────────
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

ET_OFFSET    = get_et_offset()   # Auto DST — no manual changes needed
now_et       = datetime.now(timezone.utc) + ET_OFFSET
tomorrow_et  = now_et + timedelta(days=1)

# Skip weekends — if tomorrow is Saturday or Sunday, target Monday
if tomorrow_et.weekday() == 5:   # Saturday → Monday
    tomorrow_et = tomorrow_et + timedelta(days=2)
elif tomorrow_et.weekday() == 6: # Sunday → Monday
    tomorrow_et = tomorrow_et + timedelta(days=1)

target_date    = tomorrow_et
target_iso     = target_date.strftime("%Y-%m-%d")
target_str     = target_date.strftime("%B %-d, %Y")      # June 25, 2026
target_long    = target_date.strftime("%A, %B %-d, %Y")  # Thursday, June 25, 2026
target_id      = target_date.strftime("%m%d%Y")          # 06252026
target_weekiso = target_date.strftime("%Y/%m/%d")

# All date format variants the target date might appear as
target_variants = [
    target_str,
    target_long,
    target_date.strftime("%b. %-d, %Y"),
    target_date.strftime("%b %-d, %Y"),
    target_date.strftime("%-d-%b-%Y").upper(),
    target_date.strftime("%-d-%b-%y").upper(),
    target_iso,
    target_date.strftime("%m/%d/%Y"),
    target_date.strftime("%m/%d/%y"),
    target_date.strftime("%m%d%y"),
    target_date.strftime("%m%d%Y"),
    target_date.strftime("%a, %b %-d"),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# ── Committee pages ────────────────────────────────────────────────────────────
SENATE_PAGES = [
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
    ("Foreign Relations",          "https://www.foreign.senate.gov/hearings"),
]

HOUSE_PAGES = [
    ("Agriculture",              "https://agriculture.house.gov/calendar/"),
    ("Appropriations",           "https://appropriations.house.gov/events/hearings"),
    ("Armed Services",           "https://armedservices.house.gov/hearings"),
    ("Education & Workforce",    "https://edworkforce.house.gov/hearings/"),
    ("Energy & Commerce",        "https://energycommerce.house.gov/hearings"),
    ("Financial Services",       "https://financialservices.house.gov/calendar/"),
    ("Foreign Affairs",          "https://foreignaffairs.house.gov/hearings/"),
    ("Homeland Security",        "https://homeland.house.gov/hearings/"),
    ("Judiciary",                "https://judiciary.house.gov/hearings/"),
    ("Natural Resources",        "https://naturalresources.house.gov/hearings/"),
    ("Oversight",                "https://oversight.house.gov/hearings/"),
    ("Science Space Technology", "https://science.house.gov/hearings"),
    ("Transportation",           "https://transportation.house.gov/hearings/"),
    ("Veterans Affairs",         "https://veterans.house.gov/hearings/"),
    ("Ways & Means",             "https://waysandmeans.house.gov/hearings/"),
    ("Rules",                    "https://rules.house.gov/hearings"),
    ("Administration",           "https://cha.house.gov/hearings"),
    ("Intelligence",             "https://intelligence.house.gov/hearings/"),
    ("Small Business",           "https://smallbusiness.house.gov/hearings/"),
]

# ── Helpers ────────────────────────────────────────────────────────────────────
def is_target(text):
    return any(v in text for v in target_variants)

def detect_cancellation(text):
    """Loose check for short strings like topic/committee names."""
    return any(w in text.lower() for w in
               ["postponed", "cancelled", "canceled", "rescheduled",
                "withdrawn", "notice of cancellation"])

def detect_cancellation_near_date(text, variants, window=400):
    """
    Smart cancellation: only returns True if a cancellation keyword
    appears within `window` chars of the target date string.
    Prevents false positives from old hearings listed on the page.
    """
    cancel_words = ["postponed", "cancelled", "canceled", "rescheduled",
                    "withdrawn", "notice of cancellation"]
    for variant in variants:
        idx = text.lower().find(variant.lower())
        if idx == -1:
            continue
        surrounding = text[max(0, idx - window//2) : idx + window].lower()
        if any(w in surrounding for w in cancel_words):
            return True
    return False

BAD_CHAIR_STRINGS = [
    "ranking member", "the ranking", "vice chair", "ex officio",
    "presiding", "members", "staff director", "chief counsel",
]

def extract_witnesses(text):
    witnesses = []
    for line in text.split("\n"):
        line = line.strip()
        if re.match(r"^(Mr\.|Ms\.|Mrs\.|Dr\.|The Honorable|Prof\.|Hon\.)", line):
            clean = re.sub(r"\s+", " ", line).strip(" ,;")
            if clean and 10 < len(clean) < 150:
                witnesses.append(clean)
    return list(dict.fromkeys(witnesses))

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
            if any(bad in chair.lower() for bad in BAD_CHAIR_STRINGS):
                continue
            if 5 < len(chair) < 60:
                return chair
    return ""

def extract_topic_near_date(text, max_chars=400):
    """Extract topic/title near the target date string in a block of text."""
    idx = -1
    for v in target_variants:
        idx = text.find(v)
        if idx != -1:
            break
    if idx == -1:
        return ""
    surrounding = text[idx:idx + max_chars]
    lines = [l.strip() for l in surrounding.split("\n") if len(l.strip()) > 20]
    # Skip the date line itself
    for line in lines[1:]:
        if not any(v in line for v in target_variants):
            return line[:200]
    return ""

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

def norm_cmte(c):
    return re.sub(r"[^a-z0-9]", "", str(c).lower())

def norm_time(t):
    return re.sub(r"\s*(ET|EDT|EST)\s*$", "", str(t)).strip().upper().replace(" ", "")

def fuzzy_match(h1, h2):
    if h1["chamber"] != h2["chamber"]:
        return False
    t1, t2 = norm_time(h1["time"]), norm_time(h2["time"])
    c1, c2 = norm_cmte(h1["committee"]), norm_cmte(h2["committee"])
    time_ok = t1 == t2 or t1[:5] == t2[:5]
    cmte_ok = c1[:20] == c2[:20] or c1 in c2 or c2 in c1
    return time_ok and cmte_ok

def make_hearing(chamber, committee, time_val, room_val, topic, details="",
                 chair="", witnesses=None, cancelled=False):
    return {
        "chamber":   chamber,
        "committee": committee,
        "chair":     chair,
        "time":      f"{time_val} ET" if "ET" not in time_val else time_val,
        "building":  building_from_room(room_val) if chamber in ("Senate","Joint")
                     else house_building_from_room(room_val),
        "room":      room_val,
        "topic":     topic[:200] if topic else "",
        "details":   details[:500] if details else topic[:200] if topic else "",
        "witnesses": witnesses or [],
        "cancelled": cancelled,
        "changes":   [],
    }

# ── Main async builder ─────────────────────────────────────────────────────────
async def build():
    hearings     = []
    witness_cache  = {}
    chair_cache    = {}
    detail_cache   = {}
    cancelled_cache = set()
    seen_dedup     = set()

    def dedup_key(h):
        return f"{h['chamber']}|{norm_cmte(h['committee'])[:20]}|{norm_time(h['time'])[:4]}"

    def add_hearing(h):
        k = dedup_key(h)
        if k not in seen_dedup:
            seen_dedup.add(k)
            hearings.append(h)
            print(f"  ✅ {h['chamber']}: {h['committee']} | {h['time']} | {h['room']}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=HEADERS["User-Agent"])

        # ── 1. House — docs.house.gov (most reliable source) ─────────────────
        print(f"\n🏛  House — docs.house.gov for {target_id}")
        try:
            page = await context.new_page()
            await page.goto(
                f"https://docs.house.gov/Committee/Calendar/ByDay.aspx?DayID={target_id}",
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
                # Check for linked event page to get more detail
                link_el = await cells[0].query_selector("a")
                detail_url = await link_el.get_attribute("href") if link_el else None

                h = make_hearing("House", committee,
                                 time_text or "TBD",
                                 loc_text or "TBD",
                                 topic,
                                 cancelled=detect_cancellation(topic))
                add_hearing(h)

                # Store detail URL for later enrichment
                if detail_url:
                    detail_cache[dedup_key(h)] = detail_url

            await page.close()
            print(f"House total: {sum(1 for h in hearings if h['chamber']=='House')}")
        except Exception as e:
            print(f"❌ House: {e}")

        # ── 2. Senate — senate.gov with DataTables show-all ──────────────────
        print(f"\n🏛  Senate — senate.gov")
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

            # Set DataTables to show all entries
            try:
                await page.evaluate("""
                    () => {
                        const selects = document.querySelectorAll('select');
                        selects.forEach(s => {
                            const vals = Array.from(s.options).map(o=>o.value);
                            const best = ['-1','100','50','25'].find(v=>vals.includes(v));
                            if (best) {
                                s.value = best;
                                s.dispatchEvent(new Event('change',{bubbles:true}));
                            }
                        });
                    }
                """)
                await asyncio.sleep(4)
            except:
                pass

            rows = await page.query_selector_all("table tr")
            print(f"Senate rows after show-all: {len(rows)}")

            seen_senate = set()
            for row in rows:
                text = await row.inner_text()
                if not is_target(text):
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

                topic     = topic_cell.strip()[:200]
                cancelled = detect_cancellation(topic) or detect_cancellation(committee)

                # Determine chamber — JEC and joint caucuses
                chamber = "Joint" if any(x in full_cmte for x in
                          ["Joint Economic", "Joint Committee", "Caucus"]) else "Senate"

                add_hearing(make_hearing(chamber, full_cmte, time_val, room_val,
                                         topic, details=topic, cancelled=cancelled))

            await page.close()
            print(f"Senate total: {sum(1 for h in hearings if h['chamber']=='Senate')}")
            print(f"Joint total: {sum(1 for h in hearings if h['chamber']=='Joint')}")
        except Exception as e:
            print(f"❌ Senate: {e}")

        # ── 3. Congress.gov weekly schedule (catches JEC, caucuses, extras) ──
        print(f"\n🏛  Congress.gov weekly schedule")
        try:
            # Build the Monday-of-week URL
            monday = target_date - timedelta(days=target_date.weekday())
            week_url = f"https://www.congress.gov/committee-schedule/weekly/{monday.strftime('%Y/%m/%d')}"
            page = await context.new_page()
            await page.goto(week_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(3)
            text = await page.inner_text("body")

            if is_target(text):
                print(f"Congress.gov: target date found on weekly page")
                # Parse entries — congress.gov lists them as "Committee · Time · Room · Topic · Witnesses"
                # Extract blocks near our target date
                lines = text.split("\n")
                in_target_section = False
                current_block = []
                blocks = []

                for line in lines:
                    line = line.strip()
                    if is_target(line):
                        in_target_section = True
                        current_block = []
                        continue
                    # Next date header ends our section
                    if in_target_section and re.search(r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),", line) and not is_target(line):
                        if current_block:
                            blocks.append(current_block)
                        in_target_section = False
                        current_block = []
                        continue
                    if in_target_section and line:
                        current_block.append(line)

                if current_block:
                    blocks.append(current_block)

                # Parse each block for committee/time/room/witnesses
                for block in blocks:
                    block_text = "\n".join(block)

                    # Extract time
                    time_match = re.search(r"(\d{1,2}:\d{2}\s*[AP]M)\s*\(?(EDT|EST|ET)?\)?", block_text, re.IGNORECASE)
                    time_val   = time_match.group(1).strip() if time_match else "TBD"

                    # Extract room
                    room_match = re.search(r"([A-Z]{1,3}-[\w]+|\d{3,4}\s*[A-Z]{2,5})", block_text)
                    room_val   = room_match.group(1).strip() if room_match else "TBD"

                    # Extract committee — usually first substantial line
                    cmte_lines = [l for l in block if len(l) > 5 and not re.match(r"^\d", l)
                                  and "Witness" not in l and "AM" not in l and "PM" not in l]
                    committee  = cmte_lines[0] if cmte_lines else ""
                    if not committee:
                        continue

                    # Extract witnesses
                    witnesses = extract_witnesses(block_text)

                    # Extract topic — line after committee
                    topic_candidates = [l for l in block if len(l) > 15
                                       and l != committee and "Witness" not in l
                                       and not re.search(r"\d+:\d+", l)]
                    topic = topic_candidates[0] if topic_candidates else committee

                    # Determine chamber
                    chamber = "Joint" if any(x in committee for x in
                              ["Joint Economic", "Joint Committee", "Helsinki"]) else \
                              "House" if "House" in block_text or any(
                              r in room_val for r in ["RHOB","LHOB","CHOB"]) else "Senate"

                    h = make_hearing(chamber, committee, time_val, room_val,
                                     topic, details=topic, witnesses=witnesses)

                    # Only add if not already in hearings
                    if not any(fuzzy_match(h, existing) for existing in hearings):
                        add_hearing(h)
                        print(f"  ➕ Congress.gov extra: {committee}")

            await page.close()
        except Exception as e:
            print(f"❌ Congress.gov: {e}")

        # ── 4. Individual committee pages — witnesses, chairs, details ────────
        print(f"\n📋 Committee pages — enrichment pass")

        all_cmte_pages = [("Senate", n, u) for n, u in SENATE_PAGES] + \
                         [("House",  n, u) for n, u in HOUSE_PAGES]

        for chamber_label, name, url in all_cmte_pages:
            try:
                page = await context.new_page()
                await page.goto(url, wait_until="networkidle", timeout=20000)
                await asyncio.sleep(1)
                text = await page.inner_text("body")

                if not is_target(text):
                    await page.close()
                    continue

                print(f"  📋 {chamber_label} {name}: target date found")

                # Cancellation
                if detect_cancellation_near_date(text, target_variants):
                    idx = max((text.find(v) for v in target_variants if v in text), default=-1)
                    if idx != -1:
                        surrounding = text[max(0, idx-300):idx+600]
                        if detect_cancellation(surrounding):
                            cancelled_cache.add(name.lower())
                            print(f"  ⚠️  Cancellation detected: {name}")

                # Witnesses
                witnesses = extract_witnesses(text)
                if witnesses:
                    witness_cache[name.lower()] = witnesses
                    print(f"  👤 {name}: {len(witnesses)} witnesses")

                # Chair
                chair = extract_chair(text)
                if chair:
                    chair_cache[name.lower()] = chair
                    print(f"  🪑 {name}: {chair}")

                # Topic/details near target date
                topic = extract_topic_near_date(text)
                if topic and len(topic) > 20:
                    detail_cache[name.lower()] = topic

                # PDF witness lists — look for linked PDFs
                pdf_links = await page.query_selector_all("a[href$='.pdf'], a[href*='witness']")
                for link in pdf_links[:3]:  # check up to 3 PDFs
                    try:
                        pdf_url = await link.get_attribute("href")
                        if not pdf_url:
                            continue
                        if not pdf_url.startswith("http"):
                            base = url.split("/")[0] + "//" + url.split("/")[2]
                            pdf_url = base + pdf_url
                        # Fetch PDF and extract text
                        if HAS_PDF:
                            import requests
                            r = requests.get(pdf_url, headers=HEADERS, timeout=10)
                            if r.status_code == 200:
                                with pdfplumber.open(io.BytesIO(r.content)) as pdf:
                                    pdf_text = "\n".join(
                                        page_obj.extract_text() or ""
                                        for page_obj in pdf.pages[:3]
                                    )
                                pdf_witnesses = extract_witnesses(pdf_text)
                                if pdf_witnesses:
                                    existing = witness_cache.get(name.lower(), [])
                                    merged = list(dict.fromkeys(existing + pdf_witnesses))
                                    witness_cache[name.lower()] = merged
                                    print(f"  📄 PDF witnesses for {name}: {len(pdf_witnesses)}")
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

    # ── Apply enrichment to hearings ──────────────────────────────────────────
    print(f"\n🔗 Applying enrichment to {len(hearings)} hearings...")
    for h in hearings:
        cmte_lower = h["committee"].lower()

        # Apply witnesses
        for key, witnesses in witness_cache.items():
            if key in cmte_lower or any(w in cmte_lower for w in key.split()):
                if witnesses and not h["witnesses"]:
                    h["witnesses"] = witnesses
                    break

        # Apply chair
        for key, chair in chair_cache.items():
            if key in cmte_lower or any(w in cmte_lower for w in key.split()):
                if chair and not h["chair"]:
                    h["chair"] = chair
                    break

        # Apply details
        for key, detail in detail_cache.items():
            if isinstance(key, str) and (key in cmte_lower or any(w in cmte_lower for w in key.split())):
                if detail and (not h["details"] or len(detail) > len(h["details"])):
                    h["details"] = detail
                    break

        # Apply cancellations
        for key in cancelled_cache:
            if key in cmte_lower or any(w in cmte_lower for w in key.split()):
                h["cancelled"] = True
                break

        # Default witnesses
        if not h["witnesses"]:
            h["witnesses"] = ["Witnesses not yet publicly posted"]

    # ── Sort: Senate, House, Joint; then by time ──────────────────────────────
    def sort_key(h):
        order = {"Senate": 0, "House": 1, "Joint": 2}
        return (order.get(h["chamber"], 3), h.get("time", ""))

    hearings.sort(key=sort_key)

    # Filter out placeholder entries that docs.house.gov adds on no-hearing days
    PLACEHOLDER_PHRASES = [
        "no committee hearing scheduled",
        "no hearings scheduled",
        "no hearings",
        "committee recess",
        "congress in recess",
    ]
    hearings = [
        h for h in hearings
        if not any(p in h.get("topic","").lower() or p in h.get("committee","").lower()
                   for p in PLACEHOLDER_PHRASES)
    ]

    sc = sum(1 for h in hearings if h["chamber"] == "Senate")
    hc = sum(1 for h in hearings if h["chamber"] == "House")
    jc = sum(1 for h in hearings if h["chamber"] == "Joint")
    print(f"\n📊 Final baseline: {len(hearings)} hearings ({sc} Senate · {hc} House · {jc} Joint)")
    if not hearings:
        print("⚠️  No hearings found — Congress may be in recess or no committees scheduled")

    # ── Write baseline.json ───────────────────────────────────────────────────
    baseline = {
        "date":      target_iso,
        "generated": now_et.strftime("%-I:%M %p ET · %A, %B %-d, %Y"),
        "hearings":  hearings,
    }

    with open("baseline.json", "w", encoding="utf-8") as f:
        json.dump(baseline, f, indent=2, ensure_ascii=False)

    print(f"✅ baseline.json written for {target_iso} ({target_long})")

asyncio.run(build())
