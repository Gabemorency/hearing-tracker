"""
Congressional Hearing Tracker — Full Playwright scraper
Runs hourly via GitHub Actions.
- Fetches House (docs.house.gov) and Senate (senate.gov) with headless Chromium
- Checks all major committee pages for witnesses + cancellations
- Compares against previous snapshot to detect changes
- Stamps changed cards with what changed and when
"""

import asyncio
import json
import os
import re
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright

# ── Timezone ───────────────────────────────────────────────────────────────────
ET_OFFSET  = timedelta(hours=-4)  # EDT; change to -5 for EST Nov-Mar
now_utc    = datetime.now(timezone.utc)
now_et     = now_utc + ET_OFFSET
today_str  = now_et.strftime("%B %-d, %Y")
today_long = now_et.strftime("%A, %B %-d, %Y")
today_id   = now_et.strftime("%m%d%Y")       # e.g. 06242026
today_iso  = now_et.strftime("%Y-%m-%d")     # e.g. 2026-06-24
generated  = now_et.strftime("%-I:%M %p ET")
change_time = now_et.strftime("%-I:%M %p")

SNAPSHOT_FILE = "snapshot.json"

# ── Committee pages to check for witnesses + cancellations ────────────────────
# Format: (chamber, short_name, url)
COMMITTEE_PAGES = [
    # Senate
    ("Senate", "Armed Services",            "https://www.armed-services.senate.gov/hearings"),
    ("Senate", "Agriculture",               "https://www.agriculture.senate.gov/hearings"),
    ("Senate", "Appropriations",            "https://www.appropriations.senate.gov/hearings"),
    ("Senate", "Banking",                   "https://www.banking.senate.gov/hearings"),
    ("Senate", "Budget",                    "https://www.budget.senate.gov/hearings"),
    ("Senate", "Commerce",                  "https://www.commerce.senate.gov/hearings"),
    ("Senate", "Energy & Natural Resources","https://www.energy.senate.gov/hearings"),
    ("Senate", "Environment & Public Works","https://www.epw.senate.gov/public/index.cfm/hearings"),
    ("Senate", "Finance",                   "https://www.finance.senate.gov/hearings"),
    ("Senate", "Foreign Relations",         "https://www.foreign.senate.gov/hearings"),
    ("Senate", "Health HELP",               "https://www.help.senate.gov/hearings"),
    ("Senate", "Homeland Security",         "https://www.hsgac.senate.gov/hearings"),
    ("Senate", "Indian Affairs",            "https://www.indian.senate.gov/hearings"),
    ("Senate", "Intelligence",              "https://www.intelligence.senate.gov/hearings"),
    ("Senate", "Judiciary",                 "https://www.judiciary.senate.gov/committee-activity/hearings"),
    ("Senate", "Rules",                     "https://www.rules.senate.gov/hearings"),
    ("Senate", "Small Business",            "https://www.sbc.senate.gov/public/index.cfm/hearings"),
    ("Senate", "Veterans Affairs",          "https://www.veterans.senate.gov/hearings"),
    # House
    ("House", "Agriculture",                "https://agriculture.house.gov/calendar/"),
    ("House", "Appropriations",             "https://appropriations.house.gov/events/hearings"),
    ("House", "Armed Services",             "https://armedservices.house.gov/hearings"),
    ("House", "Budget",                     "https://budget.house.gov/hearings"),
    ("House", "Education & Workforce",      "https://edworkforce.house.gov/hearings/"),
    ("House", "Energy & Commerce",          "https://energycommerce.house.gov/hearings"),
    ("House", "Financial Services",         "https://financialservices.house.gov/calendar/"),
    ("House", "Foreign Affairs",            "https://foreignaffairs.house.gov/hearings/"),
    ("House", "Homeland Security",          "https://homeland.house.gov/hearings/"),
    ("House", "Judiciary",                  "https://judiciary.house.gov/hearings/"),
    ("House", "Natural Resources",          "https://naturalresources.house.gov/hearings/"),
    ("House", "Oversight",                  "https://oversight.house.gov/hearings/"),
    ("House", "Rules",                      "https://rules.house.gov/hearings"),
    ("House", "Science Space Technology",   "https://science.house.gov/hearings"),
    ("House", "Transportation",             "https://transportation.house.gov/hearings/"),
    ("House", "Veterans Affairs",           "https://veterans.house.gov/hearings/"),
    ("House", "Ways & Means",               "https://waysandmeans.house.gov/hearings/"),
]

# ── Helpers ───────────────────────────────────────────────────────────────────
def hearing_key(h):
    """Stable key to match hearings across runs."""
    return f"{h['chamber']}|{h['committee'][:40]}|{h['time']}"

def detect_cancellation(text):
    text_l = text.lower()
    return any(w in text_l for w in ["postponed", "cancelled", "canceled", "rescheduled", "withdrawn"])

def extract_witnesses(text):
    """
    Naive but effective: look for lines that start with 'Mr.', 'Ms.', 'Mrs.',
    'Dr.', 'The Honorable', or 'Prof.' as witness indicators.
    """
    witnesses = []
    for line in text.split("\n"):
        line = line.strip()
        if re.match(r"^(Mr\.|Ms\.|Mrs\.|Dr\.|The Honorable|Prof\.)", line):
            clean = re.sub(r"\s+", " ", line).strip(" ,;")
            if clean and len(clean) < 120:
                witnesses.append(clean)
    return list(dict.fromkeys(witnesses))  # dedupe, preserve order

def load_snapshot():
    if os.path.exists(SNAPSHOT_FILE):
        try:
            with open(SNAPSHOT_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_snapshot(hearings):
    snap = {hearing_key(h): h for h in hearings}
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(snap, f, indent=2)

def diff_hearing(old, new):
    """Return list of change strings between old and new hearing dicts."""
    changes = []
    if old.get("time") != new.get("time"):
        changes.append(f"Time changed to {new.get('time', 'TBD')}")
    if old.get("room") != new.get("room"):
        changes.append(f"Room changed to {new.get('room', 'TBD')}")
    if old.get("building") != new.get("building"):
        changes.append(f"Location changed to {new.get('building', 'TBD')}")
    old_w = set(old.get("witnesses", []))
    new_w = set(new.get("witnesses", []))
    added = new_w - old_w
    if added:
        changes.append(f"Witness{'es' if len(added) > 1 else ''} added: {', '.join(list(added)[:2])}" +
                       (f" +{len(added)-2} more" if len(added) > 2 else ""))
    if not old.get("cancelled") and new.get("cancelled"):
        changes.append("CANCELLED")
    return changes

# ── Main async scraper ────────────────────────────────────────────────────────
async def scrape():
    hearings = []
    committee_witness_cache = {}  # committee_name -> [witnesses]
    committee_cancelled_cache = set()  # committee names with cancellations today

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # ── House calendar ────────────────────────────────────────────────────
        try:
            page = await context.new_page()
            url = f"https://docs.house.gov/Committee/Calendar/ByDay.aspx?DayID={today_id}"
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_selector("table", timeout=10000)
            rows = await page.query_selector_all("table tr")
            for row in rows:
                cells = await row.query_selector_all("td")
                if len(cells) < 3:
                    continue
                title_text = await cells[0].inner_text()
                time_text  = (await cells[1].inner_text()).strip()
                loc_text   = (await cells[2].inner_text()).strip()

                lines = [l.strip() for l in title_text.split("\n") if l.strip()]
                if len(lines) < 2:
                    continue
                topic     = lines[0].strip('""\u201c\u201d')
                committee = lines[1]

                building = "Rayburn (RHOB)"
                if "LHOB" in loc_text:    building = "Longworth (LHOB)"
                elif "CHOB" in loc_text:  building = "Cannon (CHOB)"
                elif loc_text.startswith("H-") or loc_text.startswith("H "):
                    building = "Capitol"
                elif not loc_text:        building = "Classified"

                cancelled = detect_cancellation(topic) or detect_cancellation(committee)

                hearings.append({
                    "chamber":   "House",
                    "committee": committee,
                    "chair":     "",
                    "time":      f"{time_text} ET" if time_text else "TBD",
                    "building":  building,
                    "room":      loc_text if loc_text else "Closed",
                    "topic":     topic,
                    "witnesses": [],
                    "details":   "",
                    "cancelled": cancelled,
                    "changes":   [],
                })
            await page.close()
            print(f"House: {sum(1 for h in hearings if h['chamber']=='House')} hearings")
        except Exception as e:
            print(f"House scrape error: {e}")

        # ── Senate calendar ───────────────────────────────────────────────────
        try:
            page = await context.new_page()
            await page.goto(
                "https://www.senate.gov/committees/hearings_meetings.htm",
                wait_until="networkidle", timeout=30000
            )
            # Wait for the data table to render via JS
            await page.wait_for_selector("table.committee-table, table, .table-responsive",
                                          timeout=15000)
            await asyncio.sleep(2)  # give JS a moment to fully populate
            content = await page.content()
            soup_page = await page.query_selector_all("tr")

            # Parse rendered table rows
            for row in soup_page:
                text = await row.inner_text()
                if today_str not in text and today_long not in text:
                    continue
                cells = await row.query_selector_all("td")
                if len(cells) < 3:
                    continue
                date_cell  = await cells[0].inner_text()
                cmte_cell  = await cells[1].inner_text()
                topic_cell = await cells[2].inner_text()

                # Extract time and room from date cell
                time_match = re.search(r"(\d+:\d+\s*[AP]M)", date_cell, re.IGNORECASE)
                room_match = re.search(r"([A-Z]{1,3}-[\w]+|[A-Z]{1,2}\d{2,4}[A-Z]?)", date_cell)
                time_val   = time_match.group(1).strip() if time_match else "TBD"
                room_val   = room_match.group(1).strip() if room_match else "TBD"

                cmte_lines = [l.strip() for l in cmte_cell.split("\n") if l.strip()]
                committee  = cmte_lines[0] if cmte_lines else cmte_cell.strip()
                sub        = cmte_lines[1] if len(cmte_lines) > 1 else ""
                full_cmte  = f"{committee} — {sub}" if sub else committee

                building_map = {
                    "SR": "Russell (SR)", "SD": "Dirksen (SD)",
                    "SH": "Hart (SH)",   "SV": "Capitol Visitor Center",
                    "S-": "Capitol (Senate)",
                }
                building = "Dirksen (SD)"
                for k, v in building_map.items():
                    if room_val.startswith(k):
                        building = v
                        break

                topic     = topic_cell.strip()[:200]
                cancelled = detect_cancellation(topic) or detect_cancellation(committee)

                hearings.append({
                    "chamber":   "Senate",
                    "committee": full_cmte,
                    "chair":     "",
                    "time":      f"{time_val} ET",
                    "building":  building,
                    "room":      room_val,
                    "topic":     topic,
                    "witnesses": [],
                    "details":   topic,
                    "cancelled": cancelled,
                    "changes":   [],
                })
            await page.close()
            print(f"Senate: {sum(1 for h in hearings if h['chamber']=='Senate')} hearings")
        except Exception as e:
            print(f"Senate scrape error: {e}")

        # ── Committee pages — witnesses + cancellations ───────────────────────
        for chamber, name, url in COMMITTEE_PAGES:
            try:
                page = await context.new_page()
                await page.goto(url, wait_until="networkidle", timeout=20000)
                await asyncio.sleep(1)
                text = await page.inner_text("body")

                # Check for today's date on this page
                if today_str not in text and today_iso not in text:
                    await page.close()
                    continue

                # Look for cancellation notices
                if detect_cancellation(text):
                    # Check if the cancellation is near today's date
                    idx = text.find(today_str)
                    if idx == -1:
                        idx = text.find(today_iso)
                    if idx != -1:
                        surrounding = text[max(0, idx-200):idx+500]
                        if detect_cancellation(surrounding):
                            committee_cancelled_cache.add(name.lower())
                            print(f"  Cancellation detected: {name}")

                # Extract witnesses
                witnesses = extract_witnesses(text)
                if witnesses:
                    committee_witness_cache[name.lower()] = witnesses
                    print(f"  Witnesses found for {name}: {len(witnesses)}")

                await page.close()
            except Exception as e:
                print(f"  Committee page error ({name}): {e}")
                try:
                    await page.close()
                except:
                    pass

        await browser.close()

    # ── Apply committee data to hearings ──────────────────────────────────────
    for h in hearings:
        cmte_lower = h["committee"].lower()
        # Check witnesses
        for key, witnesses in committee_witness_cache.items():
            if key in cmte_lower or cmte_lower in key:
                if witnesses and not h["witnesses"]:
                    h["witnesses"] = witnesses
                break
        # Check cancellations
        for key in committee_cancelled_cache:
            if key in cmte_lower or cmte_lower in key:
                h["cancelled"] = True
                break

    # ── Diff against snapshot ─────────────────────────────────────────────────
    snapshot = load_snapshot()
    for h in hearings:
        key = hearing_key(h)
        if key in snapshot:
            old = snapshot[key]
            changes = diff_hearing(old, h)
            if changes:
                h["changes"] = [f"{c} · {change_time}" for c in changes]
                print(f"  Change detected on {h['committee']}: {changes}")
        # Preserve previously detected changes so they survive across runs
        elif key in snapshot and snapshot[key].get("changes"):
            h["changes"] = snapshot[key]["changes"]

    save_snapshot(hearings)

    # ── Sort ──────────────────────────────────────────────────────────────────
    def sort_key(h):
        order = {"Senate": 0, "House": 1, "Joint": 2}
        return (order.get(h["chamber"], 3), h.get("time", ""))
    hearings.sort(key=sort_key)

    return hearings

# ── Build HTML ────────────────────────────────────────────────────────────────
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

  .card {{ border: 1px solid rgba(255,255,255,0.07); border-radius: 8px; padding: 14px 16px; cursor: pointer; margin-bottom: 9px; background: rgba(255,255,255,0.018); transition: background 0.15s; position: relative; }}
  .card.open {{ background: rgba(255,255,255,0.038); }}
  .card.cancelled {{ opacity: 0.5; }}
  .card.cancelled .card-committee {{ text-decoration: line-through; }}
  .card.has-changes {{ border-top: 2px solid rgba(255, 200, 50, 0.5); }}

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
  <div class="header-timestamp">As of {generated} · {today_long} · Auto-updates hourly · Schedules subject to change.</div>
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
  <div class="source-note">
    ℹ Auto-updated hourly via GitHub Actions · Sources: docs.house.gov · senate.gov · Individual committee pages · Nightly verification by Claude
  </div>
</div>

<script>
const HEARINGS = {hearings_json};

function cls(c) {{ return c === 'Senate' ? 'senate' : c === 'House' ? 'house' : 'joint'; }}

function buildCards(filter) {{
  let filtered;
  if (filter === 'All')       filtered = HEARINGS;
  else if (filter === 'Updated')   filtered = HEARINGS.filter(h => h.changes && h.changes.length > 0);
  else if (filter === 'Cancelled') filtered = HEARINGS.filter(h => h.cancelled);
  else filtered = HEARINGS.filter(h => h.chamber === filter);

  document.getElementById('count-label').textContent =
    filtered.length + ' hearing' + (filtered.length !== 1 ? 's' : '') + ' — tap any card to expand';

  const list = document.getElementById('card-list');
  list.innerHTML = '';

  if (!filtered.length) {{
    list.innerHTML = '<div class="empty">No ' + (filter !== 'All' ? filter.toLowerCase() + ' ' : '') + 'hearings found.</div>';
    return;
  }}

  filtered.forEach(h => {{
    const c = cls(h.chamber);
    const card = document.createElement('div');
    const hasChanges = h.changes && h.changes.length > 0;
    card.className = [
      'card',
      'chamber-' + c,
      h.cancelled ? 'cancelled' : '',
      hasChanges   ? 'has-changes' : '',
    ].filter(Boolean).join(' ');

    const changePills = hasChanges
      ? '<div class="change-pills">' +
          h.changes.map(ch => {{
            const isCancelled = ch.toLowerCase().includes('cancel');
            return '<span class="change-pill' + (isCancelled ? ' cancelled-pill' : '') + '">⚡ ' + ch + '</span>';
          }}).join('') +
        '</div>'
      : '';

    const cancelledTag = h.cancelled
      ? '<span class="tag tag-cancelled">Cancelled</span>' : '';

    card.innerHTML = `
      <div class="card-top">
        <div class="card-left">
          <div class="card-meta">
            <span class="tag tag-${{c}}">${{h.chamber}}</span>
            ${{cancelledTag}}
            <span class="card-time">${{h.time}}</span>
          </div>
          <div class="card-committee">${{h.committee}}</div>
          <div class="card-topic">${{h.topic}}</div>
          ${{changePills}}
        </div>
        <div class="card-right">
          <div class="card-building bc-${{c}}">${{h.building}}</div>
          <div class="card-room">${{h.room}}</div>
        </div>
      </div>
      <div class="card-body">
        ${{h.chair ? '<div class="card-chair">◆ ' + h.chair + '</div>' : ''}}
        ${{h.details ? '<div class="card-details">' + h.details + '</div>' : ''}}
        ${{h.witnesses && h.witnesses.length
          ? '<div class="witnesses-label wl-' + c + '">Witnesses</div>' +
            h.witnesses.map(w => '<div class="witness wb-' + c + '">' + w + '</div>').join('')
          : ''}}
      </div>
    `;
    card.addEventListener('click', () => card.classList.toggle('open'));
    list.appendChild(card);
  }});
}}

function setFilter(f) {{
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.toggle('active', b.textContent.includes(f) || (f==='All' && b.textContent==='All')));
  buildCards(f);
}}

buildCards('All');
</script>
</body>
</html>"""

# ── Entry point ───────────────────────────────────────────────────────────────
async def main():
    print(f"Scraping for {today_long}...")
    hearings = await scrape()
    print(f"Total: {len(hearings)} hearings")
    html = build_html(hearings)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("index.html written.")

asyncio.run(main())
