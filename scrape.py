"""
Congressional Hearing Tracker — Full Playwright scraper
Runs every 15 min via GitHub Actions.
Senate source: senate.gov hearings page (Playwright) with fallback to individual committee pages
House source: docs.house.gov (Playwright)
Change detection: snapshot.json diff
"""

import asyncio
import json
import os
import re
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright

# ── Timezone ───────────────────────────────────────────────────────────────────
ET_OFFSET   = timedelta(hours=-4)  # EDT; change to -5 Nov-Mar
now_utc     = datetime.now(timezone.utc)
now_et      = now_utc + ET_OFFSET
today_str   = now_et.strftime("%B %-d, %Y")        # June 24, 2026
today_long  = now_et.strftime("%A, %B %-d, %Y")   # Wednesday, June 24, 2026
today_id    = now_et.strftime("%m%d%Y")            # 06242026
today_iso   = now_et.strftime("%Y-%m-%d")          # 2026-06-24
generated   = now_et.strftime("%-I:%M %p ET")
change_time = now_et.strftime("%-I:%M %p")

# Short month+day variants senate.gov might use
today_variants = [
    today_str,                                      # June 24, 2026
    today_long,                                     # Wednesday, June 24, 2026
    now_et.strftime("%b. %-d, %Y"),                # Jun. 24, 2026
    now_et.strftime("%-d-%b-%Y").upper(),           # 24-JUN-2026
    today_iso,                                      # 2026-06-24
    now_et.strftime("%m/%d/%Y"),                   # 06/24/2026
]

SNAPSHOT_FILE = "snapshot.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ── Senate committee pages — used for witnesses, cancellations, AND fallback ──
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
    ("Indian Affairs",             "https://www.indian.senate.gov/hearings"),
    ("Joint Economic",             "https://www.jec.senate.gov/public/index.cfm/hearings"),
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

def detect_cancellation(text):
    return any(w in text.lower() for w in
               ["postponed", "cancelled", "canceled", "rescheduled", "withdrawn", "notice of cancellation"])

def is_today(text):
    return any(v in text for v in today_variants)

def extract_witnesses(text):
    witnesses = []
    for line in text.split("\n"):
        line = line.strip()
        if re.match(r"^(Mr\.|Ms\.|Mrs\.|Dr\.|The Honorable|Prof\.|Hon\.)", line):
            clean = re.sub(r"\s+", " ", line).strip(" ,;")
            if clean and 10 < len(clean) < 120:
                witnesses.append(clean)
    return list(dict.fromkeys(witnesses))

def building_from_room(room):
    mapping = {
        "SR": "Russell (SR)", "SD": "Dirksen (SD)",
        "SH": "Hart (SH)",   "SV": "Capitol Visitor Center",
        "S-": "Capitol (Senate)",
    }
    for k, v in mapping.items():
        if room.startswith(k):
            return v
    return "Dirksen (SD)"

def house_building_from_room(room):
    if "LHOB" in room:   return "Longworth (LHOB)"
    if "CHOB" in room:   return "Cannon (CHOB)"
    if "RHOB" in room:   return "Rayburn (RHOB)"
    if room.startswith("H-") or room.startswith("H "):
        return "Capitol"
    return "Rayburn (RHOB)"

def load_snapshot():
    if os.path.exists(SNAPSHOT_FILE):
        try:
            with open(SNAPSHOT_FILE) as f:
                return json.load(f)
        except:
            pass
    return {}

def save_snapshot(hearings):
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump({hearing_key(h): h for h in hearings}, f, indent=2)

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
    added = new_w - old_w
    if added:
        preview = ", ".join(list(added)[:2])
        extra   = f" +{len(added)-2} more" if len(added) > 2 else ""
        changes.append(f"Witness{'es' if len(added)>1 else ''} added: {preview}{extra}")
    if not old.get("cancelled") and new.get("cancelled"):
        changes.append("CANCELLED")
    return changes

# ── Scraper ────────────────────────────────────────────────────────────────────
async def scrape():
    hearings     = []
    witness_cache    = {}   # committee_key -> [witnesses]
    cancelled_cache  = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=HEADERS["User-Agent"])

        # ── 1. HOUSE — docs.house.gov ─────────────────────────────────────────
        try:
            page = await context.new_page()
            url  = f"https://docs.house.gov/Committee/Calendar/ByDay.aspx?DayID={today_id}"
            await page.goto(url, wait_until="networkidle", timeout=30000)
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
                cancelled = detect_cancellation(topic) or detect_cancellation(committee)

                hearings.append({
                    "chamber":   "House",
                    "committee": committee,
                    "chair":     "",
                    "time":      f"{time_text} ET" if time_text else "TBD",
                    "building":  house_building_from_room(loc_text),
                    "room":      loc_text if loc_text else "Closed",
                    "topic":     topic,
                    "witnesses": [],
                    "details":   "",
                    "cancelled": cancelled,
                    "changes":   [],
                })
            await page.close()
            print(f"✅ House: {sum(1 for h in hearings if h['chamber']=='House')} hearings")
        except Exception as e:
            print(f"❌ House scrape error: {e}")

        # ── 2. SENATE — senate.gov main page ─────────────────────────────────
        senate_from_main = []
        try:
            page = await context.new_page()
            await page.goto(
                "https://www.senate.gov/committees/hearings_meetings.htm",
                wait_until="networkidle", timeout=30000
            )
            # Wait for DataTables to render — look for the search box it injects
            try:
                await page.wait_for_selector("input[type='search'], .dataTables_filter, table tbody tr td",
                                              timeout=15000)
            except:
                pass
            await asyncio.sleep(3)  # extra buffer for DataTables

            # Get all text content and look for today's date
            full_text = await page.inner_text("body")
            print(f"Senate page loaded — today found: {is_today(full_text)}")

            # Try to find the data table rows
            rows = await page.query_selector_all("table tr, .committee-table tr")
            print(f"Senate rows found: {len(rows)}")

            for row in rows:
                text = await row.inner_text()
                if not is_today(text):
                    continue

                cells = await row.query_selector_all("td")
                if len(cells) < 2:
                    continue

                cell_texts = [(await c.inner_text()).strip() for c in cells]
                print(f"  Senate row cells: {cell_texts[:3]}")

                # Date/time/room is in cell 0, committee in cell 1, topic in cell 2
                date_cell  = cell_texts[0] if len(cell_texts) > 0 else ""
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

                topic     = topic_cell.strip()[:200]
                cancelled = detect_cancellation(topic) or detect_cancellation(committee)

                senate_from_main.append({
                    "chamber":   "Senate",
                    "committee": full_cmte,
                    "chair":     "",
                    "time":      f"{time_val} ET",
                    "building":  building_from_room(room_val),
                    "room":      room_val,
                    "topic":     topic,
                    "witnesses": [],
                    "details":   topic,
                    "cancelled": cancelled,
                    "changes":   [],
                })

            await page.close()
            print(f"✅ Senate main page: {len(senate_from_main)} hearings found")

        except Exception as e:
            print(f"❌ Senate main page error: {e}")

        hearings.extend(senate_from_main)

        # ── 3. SENATE committee pages — witnesses + cancellations + fallback ──
        # If main page got 0 Senate hearings, use committee pages as primary source
        use_as_fallback = len(senate_from_main) == 0
        if use_as_fallback:
            print("⚠️  Senate main page returned 0 — using committee pages as primary source")

        for name, url in SENATE_COMMITTEE_PAGES:
            try:
                page = await context.new_page()
                await page.goto(url, wait_until="networkidle", timeout=20000)
                await asyncio.sleep(1)
                text = await page.inner_text("body")

                if not is_today(text):
                    await page.close()
                    continue

                print(f"  📋 {name}: today found on page")

                # Cancellation check
                if detect_cancellation(text):
                    idx = max(text.find(v) for v in today_variants if v in text)
                    if idx != -1:
                        surrounding = text[max(0, idx-300):idx+600]
                        if detect_cancellation(surrounding):
                            cancelled_cache.add(name.lower())
                            print(f"  ⚠️  Cancellation: {name}")

                # Witness extraction
                witnesses = extract_witnesses(text)
                if witnesses:
                    witness_cache[name.lower()] = witnesses
                    print(f"  👤 {name}: {len(witnesses)} witnesses")

                # Fallback: build hearing from committee page if main page got nothing
                if use_as_fallback:
                    # Look for time and room near today's date
                    idx = max((text.find(v) for v in today_variants if v in text), default=-1)
                    if idx != -1:
                        surrounding = text[idx:idx+500]
                        time_match  = re.search(r"(\d{1,2}:\d{2}\s*[AP]M)", surrounding, re.IGNORECASE)
                        room_match  = re.search(r"([A-Z]{1,3}-[\w]+)", surrounding)
                        time_val    = time_match.group(1).strip() if time_match else "TBD"
                        room_val    = room_match.group(1).strip() if room_match else "TBD"

                        # Extract topic — first substantial line after date
                        lines = [l.strip() for l in surrounding.split("\n") if len(l.strip()) > 20]
                        topic = lines[1] if len(lines) > 1 else "Hearing scheduled"
                        topic = topic[:150]

                        hearings.append({
                            "chamber":   "Senate",
                            "committee": name,
                            "chair":     "",
                            "time":      f"{time_val} ET",
                            "building":  building_from_room(room_val) if room_val != "TBD" else "Dirksen (SD)",
                            "room":      room_val,
                            "topic":     topic,
                            "witnesses": witnesses,
                            "details":   topic,
                            "cancelled": name.lower() in cancelled_cache,
                            "changes":   [],
                        })

                await page.close()
            except Exception as e:
                print(f"  ❌ {name}: {e}")
                try:
                    await page.close()
                except:
                    pass

        # ── 4. HOUSE committee pages — witnesses + cancellations ──────────────
        for name, url in HOUSE_COMMITTEE_PAGES:
            try:
                page = await context.new_page()
                await page.goto(url, wait_until="networkidle", timeout=20000)
                await asyncio.sleep(1)
                text = await page.inner_text("body")

                if not is_today(text):
                    await page.close()
                    continue

                print(f"  📋 House {name}: today found")

                if detect_cancellation(text):
                    idx = max((text.find(v) for v in today_variants if v in text), default=-1)
                    if idx != -1:
                        surrounding = text[max(0, idx-300):idx+600]
                        if detect_cancellation(surrounding):
                            cancelled_cache.add(name.lower())
                            print(f"  ⚠️  House cancellation: {name}")

                witnesses = extract_witnesses(text)
                if witnesses:
                    witness_cache[name.lower()] = witnesses
                    print(f"  👤 House {name}: {len(witnesses)} witnesses")

                await page.close()
            except Exception as e:
                print(f"  ❌ House {name}: {e}")
                try:
                    await page.close()
                except:
                    pass

        await browser.close()

    # ── Apply witnesses + cancellations to hearings ───────────────────────────
    for h in hearings:
        cmte_lower = h["committee"].lower()
        for key, witnesses in witness_cache.items():
            if key in cmte_lower or any(w in cmte_lower for w in key.split()):
                if witnesses and not h["witnesses"]:
                    h["witnesses"] = witnesses
                    break
        for key in cancelled_cache:
            if key in cmte_lower or any(w in cmte_lower for w in key.split()):
                h["cancelled"] = True
                break

    # ── Change detection ──────────────────────────────────────────────────────
    snapshot = load_snapshot()
    for h in hearings:
        key = hearing_key(h)
        if key in snapshot:
            old     = snapshot[key]
            changes = diff_hearing(old, h)
            if changes:
                h["changes"] = [f"{c} · {change_time}" for c in changes]
                print(f"  🔄 Changed: {h['committee']}: {changes}")
            else:
                # Preserve existing change stamps
                h["changes"] = old.get("changes", [])

    save_snapshot(hearings)

    # ── Sort: Senate first, then House, then Joint; within each by time ───────
    def sort_key(h):
        order = {"Senate": 0, "House": 1, "Joint": 2}
        return (order.get(h["chamber"], 3), h.get("time", ""))

    hearings.sort(key=sort_key)

    senate_n = sum(1 for h in hearings if h["chamber"] == "Senate")
    house_n  = sum(1 for h in hearings if h["chamber"] == "House")
    joint_n  = sum(1 for h in hearings if h["chamber"] == "Joint")
    print(f"\n📊 Total: {len(hearings)} ({senate_n} Senate · {house_n} House · {joint_n} Joint)")

    return hearings

# ── Build HTML ─────────────────────────────────────────────────────────────────
def build_html(hearings):
    senate_count = sum(1 for h in hearings if h["chamber"] == "Senate")
    house_count  = sum(1 for h in hearings if h["chamber"] == "House")
    joint_count  = sum(1 for h in hearings if h["chamber"] == "Joint")
    total_count  = len(hearings)
    hearings_json = json.dumps(hearings, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Congressional Hearing Tracker — {today_str}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;700&family=IBM+Plex+Sans:wght@300;400;600;700&family=Playfair+Display:wght@700&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0D0C0A; color: #E8E0D0; font-family: 'IBM Plex Sans', sans-serif; min-height: 100vh; }}
  ::-webkit-scrollbar {{ width: 4px; }}
  ::-webkit-scrollbar-thumb {{ background: #2A2820; border-radius: 2px; }}
  .header {{ border-bottom: 1px solid rgba(200,169,110,0.18); padding: 20px 20px 16px; background: rgba(200,169,110,0.025); }}
  .header-eyebrow {{ font-family: 'IBM Plex Mono', monospace; font-size: 10px; letter-spacing: 0.18em; color: #C8A96E; text-transform: uppercase; margin-bottom: 6px; }}
  .header h1 {{ font-family: 'Playfair Display', serif; font-size: clamp(20px,5vw,26px); font-weight: 700; color: #F0E8D8; letter-spacing: -0.01em; margin-bottom: 6px; }}
  .header-timestamp {{ font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #908070; letter-spacing: 0.04em; line-height: 1.5; }}
  .stats {{ display: flex; border-bottom: 1px solid rgba(255,255,255,0.05); background: #0A0908; }}
  .stat {{ flex: 1; padding: 12px 8px; text-align: center; border-right: 1px solid rgba(255,255,255,0.04); }}
  .stat-number {{ font-family: 'Playfair Display', serif; font-size: 20px; font-weight: 700; line-height: 1; }}
  .stat-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 9px; letter-spacing: 0.1em; color: #706860; text-transform: uppercase; margin-top: 3px; }}
  .filters {{ display: flex; gap: 6px; padding: 12px 16px; border-bottom: 1px solid rgba(255,255,255,0.05); flex-wrap: wrap; }}
  .filter-btn {{ background: transparent; border: 1px solid rgba(255,255,255,0.07); color: #908070; border-radius: 5px; padding: 5px 12px; font-size: 11px; font-family: 'IBM Plex Mono', monospace; letter-spacing: 0.06em; cursor: pointer; transition: all 0.15s; }}
  .filter-btn.active {{ background: rgba(200,169,110,0.13); border-color: rgba(200,169,110,0.4); color: #C8A96E; }}
  .cards {{ padding: 14px 16px; }}
  .count-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #706860; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 12px; }}
  .card {{ border: 1px solid rgba(255,255,255,0.07); border-radius: 8px; padding: 14px 16px; cursor: pointer; margin-bottom: 9px; background: rgba(255,255,255,0.018); transition: background 0.15s; }}
  .card.open {{ background: rgba(255,255,255,0.038); }}
  .card.cancelled {{ opacity: 0.5; }}
  .card.cancelled .card-committee {{ text-decoration: line-through; }}
  .card.has-changes {{ border-top: 2px solid rgba(255,200,50,0.5); }}
  .card-top {{ display: flex; gap: 10px; justify-content: space-between; align-items: flex-start; }}
  .card-left {{ flex: 1; min-width: 0; }}
  .card-meta {{ display: flex; align-items: center; gap: 7px; margin-bottom: 5px; flex-wrap: wrap; }}
  .tag {{ border-radius: 4px; font-size: 10px; font-weight: 700; letter-spacing: 0.08em; padding: 2px 7px; text-transform: uppercase; font-family: 'IBM Plex Mono', monospace; flex-shrink: 0; }}
  .tag-senate {{ background: rgba(200,169,110,0.13); color: #C8A96E; border: 1px solid rgba(200,169,110,0.35); }}
  .tag-house  {{ background: rgba(100,160,200,0.11); color: #7FB3D3; border: 1px solid rgba(100,160,200,0.30); }}
  .tag-joint  {{ background: rgba(160,120,200,0.11); color: #B39DDB; border: 1px solid rgba(160,120,200,0.30); }}
  .tag-cancelled {{ background: rgba(200,60,60,0.15); color: #E07070; border: 1px solid rgba(200,60,60,0.3); }}
  .card-time {{ font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #A09080; letter-spacing: 0.04em; }}
  .card-committee {{ font-size: 13px; font-weight: 600; color: #DDD5C5; line-height: 1.4; margin-bottom: 3px; }}
  .card-topic {{ font-size: 12px; color: #A09080; line-height: 1.4; }}
  .card-right {{ text-align: right; min-width: 96px; flex-shrink: 0; }}
  .card-building {{ font-family: 'IBM Plex Mono', monospace; font-size: 11px; margin-bottom: 2px; }}
  .card-room {{ font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #908070; }}
  .change-pills {{ display: flex; flex-wrap: wrap; gap: 4px; margin-top: 7px; }}
  .change-pill {{ font-family: 'IBM Plex Mono', monospace; font-size: 9px; letter-spacing: 0.05em; padding: 2px 7px; border-radius: 10px; background: rgba(255,200,50,0.1); color: #E0B830; border: 1px solid rgba(255,200,50,0.25); }}
  .change-pill.cancelled-pill {{ background: rgba(200,60,60,0.12); color: #E07070; border-color: rgba(200,60,60,0.3); }}
  .card-body {{ margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.06); display: none; }}
  .card.open .card-body {{ display: block; }}
  .card-chair {{ font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #A09080; letter-spacing: 0.05em; margin-bottom: 10px; }}
  .card-details {{ font-size: 12px; color: #A09080; line-height: 1.65; margin-bottom: 10px; }}
  .witnesses-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 6px; }}
  .witness {{ font-size: 12px; color: #B0A090; line-height: 1.5; padding-left: 10px; margin-bottom: 4px; }}
  .source-note {{ margin-top: 20px; padding: 12px 14px; background: rgba(255,255,255,0.012); border: 1px solid rgba(255,255,255,0.04); border-radius: 6px; font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #706860; line-height: 1.6; }}
  .empty {{ text-align: center; padding: 40px; color: #3A3530; font-size: 13px; }}
  .chamber-senate {{ border-left: 3px solid rgba(200,169,110,0.5); }}
  .chamber-house  {{ border-left: 3px solid rgba(100,160,200,0.45); }}
  .chamber-joint  {{ border-left: 3px solid rgba(160,120,200,0.45); }}
  .bc-senate {{ color: #C8A96E; }} .bc-house {{ color: #7FB3D3; }} .bc-joint {{ color: #B39DDB; }}
  .wl-senate {{ color: #C8A96E; }} .wl-house {{ color: #7FB3D3; }} .wl-joint {{ color: #B39DDB; }}
  .wb-senate {{ border-left: 2px solid rgba(200,169,110,0.5); }}
  .wb-house  {{ border-left: 2px solid rgba(100,160,200,0.45); }}
  .wb-joint  {{ border-left: 2px solid rgba(160,120,200,0.45); }}
</style>
</head>
<body>
<div class="header">
  <div class="header-eyebrow">🏛 Congressional Hearing Tracker</div>
  <h1>Today's Hearings</h1>
  <div class="header-timestamp">As of {generated} · {today_long} · Updates every 15 min · Schedules subject to change.</div>
</div>
<div class="stats">
  <div class="stat"><div class="stat-number" style="color:#888">{total_count}</div><div class="stat-label">Total</div></div>
  <div class="stat"><div class="stat-number" style="color:#C8A96E">{senate_count}</div><div class="stat-label">Senate</div></div>
  <div class="stat"><div class="stat-number" style="color:#7FB3D3">{house_count}</div><div class="stat-label">House</div></div>
  <div class="stat"><div class="stat-number" style="color:#B39DDB">{joint_count}</div><div class="stat-label">Joint</div></div>
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
  <div class="source-note">ℹ Auto-updated every 15 min · docs.house.gov · senate.gov · Individual committee pages </div>
</div>
<script>
const HEARINGS = {hearings_json};
function cls(c) {{ return c==='Senate'?'senate':c==='House'?'house':'joint'; }}
function buildCards(filter) {{
  let filtered;
  if (filter==='All')        filtered = HEARINGS;
  else if (filter==='Updated')    filtered = HEARINGS.filter(h=>h.changes&&h.changes.length>0);
  else if (filter==='Cancelled')  filtered = HEARINGS.filter(h=>h.cancelled);
  else filtered = HEARINGS.filter(h=>h.chamber===filter);
  document.getElementById('count-label').textContent =
    filtered.length+' hearing'+(filtered.length!==1?'s':'')+' — tap any card to expand';
  const list = document.getElementById('card-list');
  list.innerHTML = '';
  if (!filtered.length) {{
    list.innerHTML = '<div class="empty">No '+(filter!=='All'?filter.toLowerCase()+' ':'')+'hearings found.</div>';
    return;
  }}
  filtered.forEach(h => {{
    const c = cls(h.chamber);
    const hasChanges = h.changes&&h.changes.length>0;
    const card = document.createElement('div');
    card.className = ['card','chamber-'+c,h.cancelled?'cancelled':'',hasChanges?'has-changes':''].filter(Boolean).join(' ');
    const pills = hasChanges
      ? '<div class="change-pills">'+h.changes.map(ch=>'<span class="change-pill'+(ch.toLowerCase().includes('cancel')?' cancelled-pill':'')+'">⚡ '+ch+'</span>').join('')+'</div>'
      : '';
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
        ${{h.chair?'<div class="card-chair">◆ '+h.chair+'</div>':''}}
        ${{h.details?'<div class="card-details">'+h.details+'</div>':''}}
        ${{h.witnesses&&h.witnesses.length?'<div class="witnesses-label wl-'+c+'">Witnesses</div>'+h.witnesses.map(w=>'<div class="witness wb-'+c+'">'+w+'</div>').join(''):''}}
      </div>`;
    card.addEventListener('click',()=>card.classList.toggle('open'));
    list.appendChild(card);
  }});
}}
function setFilter(f) {{
  document.querySelectorAll('.filter-btn').forEach(b=>b.classList.toggle('active',b.textContent.replace('⚡ ','').replace('✕ ','')===f||(f==='All'&&b.textContent==='All')));
  buildCards(f);
}}
buildCards('All');
</script>
</body>
</html>"""

# ── Entry point ────────────────────────────────────────────────────────────────
async def main():
    print(f"🗓  Scraping for {today_long}...")
    hearings = await scrape()
    html = build_html(hearings)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("✅ index.html written.")

asyncio.run(main())
