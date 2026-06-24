"""
Congressional Hearing Tracker — Full Playwright scraper
- Merge strategy: nightly verified baseline is never overwritten, only enriched
- Extracts chair, witnesses, and descriptions from committee pages
- Change detection via snapshot.json diff
- Runs every 15 min via GitHub Actions
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
today_str   = now_et.strftime("%B %-d, %Y")
today_long  = now_et.strftime("%A, %B %-d, %Y")
today_id    = now_et.strftime("%m%d%Y")
today_iso   = now_et.strftime("%Y-%m-%d")
generated   = now_et.strftime("%-I:%M %p ET")
change_time = now_et.strftime("%-I:%M %p")

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

SNAPSHOT_FILE  = "snapshot.json"
BASELINE_FILE  = "baseline.json"  # nightly verified data — never overwritten by scraper

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

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

def detect_cancellation(text):
    return any(w in text.lower() for w in
               ["postponed", "cancelled", "canceled", "rescheduled",
                "withdrawn", "notice of cancellation"])

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

def extract_chair(text):
    patterns = [
        r"(?:Chairman|Chairwoman|Chair)\s+(Sen\.|Rep\.)?\s*([\w\s]+?)\s*\([RD]",
        r"(?:Sen\.|Rep\.)\s+([\w\s]+),\s+Chair",
        r"Chaired by[:\s]+([\w\s,\.]+?)(?:\n|$)",
        r"Chair(?:man|woman)?[:\s]+([\w\s]+?)(?:\n|,|\.|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            chair = match.group(match.lastindex).strip().strip(".,")
            if 5 < len(chair) < 60:
                return chair
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
    scraped       = []
    witness_cache = {}
    chair_cache   = {}
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
                    "cancelled": detect_cancellation(topic) or detect_cancellation(committee),
                    "changes":   [],
                })
            await page.close()
            print(f"✅ House: {sum(1 for h in scraped if h['chamber']=='House')} hearings")
        except Exception as e:
            print(f"❌ House: {e}")

        # ── Senate — senate.gov ───────────────────────────────────────────────
        senate_from_main = []
        try:
            page = await context.new_page()
            await page.goto(
                "https://www.senate.gov/committees/hearings_meetings.htm",
                wait_until="networkidle", timeout=30000)
            try:
                await page.wait_for_selector(
                    "input[type='search'], .dataTables_filter, table tbody tr td",
                    timeout=15000)
            except:
                pass
            await asyncio.sleep(5)

            full_text = await page.inner_text("body")
            date_lines = [l.strip() for l in full_text.split("\n")
                         if re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", l)
                         and len(l.strip()) < 80]
            print(f"Senate date lines: {date_lines[:6]}")
            print(f"Senate today found: {is_today(full_text)}")

            rows = await page.query_selector_all("table tr, .committee-table tr")
            print(f"Senate rows: {len(rows)}")
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

                topic = topic_cell.strip()[:200]
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
                    "cancelled": detect_cancellation(topic) or detect_cancellation(committee),
                    "changes":   [],
                })
                print(f"  Senate row: {full_cmte} | {time_val} | {room_val}")

            await page.close()
            print(f"✅ Senate main: {len(senate_from_main)} hearings")
        except Exception as e:
            print(f"❌ Senate main: {e}")

        scraped.extend(senate_from_main)

        # ── Committee pages — chairs, witnesses, cancellations ────────────────
        for chamber_label, pages in [("Senate", SENATE_COMMITTEE_PAGES),
                                      ("House",  HOUSE_COMMITTEE_PAGES)]:
            for name, url in pages:
                try:
                    page = await context.new_page()
                    await page.goto(url, wait_until="networkidle", timeout=20000)
                    await asyncio.sleep(1)
                    text = await page.inner_text("body")

                    if not is_today(text):
                        await page.close()
                        continue

                    print(f"  📋 {chamber_label} {name}: today found")

                    # Cancellation
                    if detect_cancellation(text):
                        idx = max((text.find(v) for v in today_variants if v in text), default=-1)
                        if idx != -1:
                            surrounding = text[max(0, idx-300):idx+600]
                            if detect_cancellation(surrounding):
                                cancelled_cache.add(name.lower())
                                print(f"  ⚠️  Cancellation: {name}")

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

                    await page.close()
                except Exception as e:
                    print(f"  ❌ {name}: {e}")
                    try:
                        await page.close()
                    except:
                        pass

        await browser.close()

    # ── Apply enrichment to scraped hearings ──────────────────────────────────
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

    # ── Merge with baseline ───────────────────────────────────────────────────
    # Baseline = nightly verified data written by me each evening
    # Scraper enriches baseline — never deletes hearings from it
    baseline = load_json(BASELINE_FILE)
    scraped_by_key = {hearing_key(h): h for h in scraped}

    merged = []

    if baseline and baseline.get("date") == today_iso:
        # We have a verified baseline for today — use it as foundation
        print(f"✅ Baseline found for {today_iso} — merging")
        for h in baseline.get("hearings", []):
            key = hearing_key(h)
            scraped_version = scraped_by_key.get(key)

            if scraped_version:
                # Update mutable fields from scraper, keep verified fields
                enriched = dict(h)
                # Only update time/room if scraper found something different
                if scraped_version["time"] != "TBD ET" and scraped_version["time"] != h["time"]:
                    enriched["time"]     = scraped_version["time"]
                if scraped_version["room"] != "TBD" and scraped_version["room"]:
                    enriched["room"]     = scraped_version["room"]
                if scraped_version["building"] and scraped_version["building"] != "Dirksen (SD)":
                    enriched["building"] = scraped_version["building"]
                # Enrich witnesses — merge, don't replace
                existing_w = set(h.get("witnesses", []))
                new_w      = set(scraped_version.get("witnesses", []))
                enriched["witnesses"] = list(existing_w | new_w) or h.get("witnesses", [])
                # Enrich chair
                if scraped_version.get("chair") and not h.get("chair"):
                    enriched["chair"] = scraped_version["chair"]
                # Cancellation
                if scraped_version.get("cancelled"):
                    enriched["cancelled"] = True
                enriched["changes"] = h.get("changes", [])
                merged.append(enriched)
            else:
                # Hearing not found by scraper — keep from baseline, mark as unconfirmed
                kept = dict(h)
                kept["changes"] = h.get("changes", [])
                merged.append(kept)
                print(f"  📌 Kept from baseline (not found by scraper): {h['committee']}")
    else:
        # No baseline for today — use scraped data directly
        print(f"⚠️  No baseline for today — using scraped data only")
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
                # Append to existing changes, don't replace
                existing = old.get("changes", [])
                h["changes"] = existing + [s for s in new_stamps if s not in existing]
                print(f"  🔄 {h['committee']}: {changes}")
            else:
                h["changes"] = old.get("changes", [])

    save_json(SNAPSHOT_FILE, {hearing_key(h): h for h in merged})

    # Sort: Senate, House, Joint; then by time
    def sort_key(h):
        order = {"Senate": 0, "House": 1, "Joint": 2}
        return (order.get(h["chamber"], 3), h.get("time", ""))
    merged.sort(key=sort_key)

    s = sum(1 for h in merged if h["chamber"] == "Senate")
    ho = sum(1 for h in merged if h["chamber"] == "House")
    j  = sum(1 for h in merged if h["chamber"] == "Joint")
    print(f"\n📊 Total: {len(merged)} ({s} Senate · {ho} House · {j} Joint)")
    return merged

# ── Build HTML ─────────────────────────────────────────────────────────────────
def build_html(hearings):
    sc = sum(1 for h in hearings if h["chamber"] == "Senate")
    hc = sum(1 for h in hearings if h["chamber"] == "House")
    jc = sum(1 for h in hearings if h["chamber"] == "Joint")
    tc = len(hearings)
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
  .card-section {{ margin-bottom: 10px; }}
  .card-section-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 5px; }}
  .card-section-value {{ font-family: 'IBM Plex Sans', sans-serif; font-size: 12px; color: #A09080; line-height: 1.65; }}
  .card-section-value.dim {{ color: #4A4540; font-style: italic; }}
  .witness {{ font-size: 12px; color: #B0A090; line-height: 1.5; padding-left: 10px; margin-bottom: 4px; }}
  .source-note {{ margin-top: 20px; padding: 12px 14px; background: rgba(255,255,255,0.012); border: 1px solid rgba(255,255,255,0.04); border-radius: 6px; font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #706860; line-height: 1.6; }}
  .empty {{ text-align: center; padding: 40px; color: #3A3530; font-size: 13px; }}
  .chamber-senate {{ border-left: 3px solid rgba(200,169,110,0.5); }}
  .chamber-house  {{ border-left: 3px solid rgba(100,160,200,0.45); }}
  .chamber-joint  {{ border-left: 3px solid rgba(160,120,200,0.45); }}
  .bc-senate {{ color: #C8A96E; }} .bc-house {{ color: #7FB3D3; }} .bc-joint {{ color: #B39DDB; }}
  .sl-senate {{ color: #C8A96E; }} .sl-house {{ color: #7FB3D3; }} .sl-joint {{ color: #B39DDB; }}
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
  <div class="stat"><div class="stat-number" style="color:#888">{tc}</div><div class="stat-label">Total</div></div>
  <div class="stat"><div class="stat-number" style="color:#C8A96E">{sc}</div><div class="stat-label">Senate</div></div>
  <div class="stat"><div class="stat-number" style="color:#7FB3D3">{hc}</div><div class="stat-label">House</div></div>
  <div class="stat"><div class="stat-number" style="color:#B39DDB">{jc}</div><div class="stat-label">Joint</div></div>
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
  <div class="source-note">ℹ Auto-updated every 15 min · docs.house.gov · senate.gov · Individual committee pages</div>
</div>
<script>
const HEARINGS = {hearings_json};
function cls(c) {{ return c==='Senate'?'senate':c==='House'?'house':'joint'; }}
function buildCards(filter) {{
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
    const chairVal   = h.chair     || '<span class="dim">Not yet posted</span>';
    const detailsVal = h.details   || h.topic || '';
    const witnessHtml = h.witnesses && h.witnesses.length
      ? h.witnesses.map(w=>'<div class="witness wb-'+c+'">'+w+'</div>').join('')
      : '<div class="witness wb-'+c+'" style="color:#4A4540;font-style:italic">Not yet posted</div>';

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
        ${{detailsVal ? '<div class="card-section"><div class="card-section-label sl-'+c+'">About</div><div class="card-section-value">'+detailsVal+'</div></div>' : ''}}
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
</body>
</html>"""

# ── Entry point ────────────────────────────────────────────────────────────────
async def main():
    print(f"🗓  Scraping for {today_long}...")
    hearings = await scrape()
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(build_html(hearings))
    print("✅ index.html written.")

asyncio.run(main())
