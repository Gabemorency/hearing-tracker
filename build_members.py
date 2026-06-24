"""
Congressional Member Directory Builder
Runs nightly via GitHub Actions alongside build_baseline.py.
Sources:
  - https://unitedstates.github.io/congress-legislators/legislators-current.json
  - https://unitedstates.github.io/congress-legislators/legislators-social-media.json
  - https://bioguide.congress.gov/bioguide/photo/{letter}/{id}.jpg
Outputs: members.json + members.html
"""

import json
import re
import os
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError

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

HEADERS = {"User-Agent": "Mozilla/5.0 hearing-tracker-bot/1.0"}

# ── Leadership role mapping ────────────────────────────────────────────────────
# Maps leadership title strings → display label + tier (lower = higher priority)
LEADERSHIP_ROLES = {
    # Senate
    "President Pro Tempore":            ("President Pro Tempore", 1),
    "Majority Leader":                  ("Majority Leader", 1),
    "Minority Leader":                  ("Minority Leader", 1),
    "Majority Whip":                    ("Majority Whip", 2),
    "Minority Whip":                    ("Minority Whip", 2),
    "Assistant Majority Leader":        ("Asst. Majority Leader", 2),
    "Assistant Minority Leader":        ("Asst. Minority Leader", 2),
    "Majority Conference Chair":        ("Conference Chair", 3),
    "Minority Conference Chair":        ("Conference Chair", 3),
    "Majority Policy Chair":            ("Policy Chair", 3),
    "Minority Policy Chair":            ("Policy Chair", 3),
    # House
    "Speaker of the House":             ("Speaker", 1),
    "House Majority Leader":            ("Majority Leader", 1),
    "House Minority Leader":            ("Minority Leader", 1),
    "House Majority Whip":              ("Majority Whip", 2),
    "House Minority Whip":              ("Minority Whip", 2),
    "House Majority Conference Chair":  ("Conference Chair", 3),
    "House Minority Conference Chair":  ("Conference Chair", 3),
    "Majority Caucus Chair":            ("Caucus Chair", 3),
    "Minority Caucus Chair":            ("Caucus Chair", 3),
}

def fetch_json(url):
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def photo_url(bioguide_id):
    letter = bioguide_id[0].upper()
    return f"https://bioguide.congress.gov/bioguide/photo/{letter}/{bioguide_id}.jpg"

def initials(name):
    parts = name.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return name[:2].upper()

def party_label(party):
    return {"Republican": "R", "Democrat": "D", "Independent": "I"}.get(party, party[0])

def party_class(party):
    return {"Republican": "rep", "Democrat": "dem", "Independent": "ind"}.get(party, "ind")

def build_member(m, leadership_map, committee_roles):
    """Build a clean member dict from raw legislator data."""
    bio   = m.get("bio", {})
    name  = m.get("name", {})
    terms = m.get("terms", [])
    if not terms:
        return None
    term  = terms[-1]  # most recent term

    bioguide_id = m.get("id", {}).get("bioguide", "")
    first = name.get("first", "")
    last  = name.get("last", "")
    full_name = f"{first} {last}".strip()
    if name.get("suffix"):
        full_name += f" {name['suffix']}"
    if name.get("nickname"):
        first = name["nickname"]

    chamber = "senate" if term.get("type") == "sen" else "house"
    state   = term.get("state", "")
    party   = term.get("party", "")
    district = term.get("district", "")

    # Leadership role
    leadership_role = leadership_map.get(bioguide_id)

    # Committee roles
    cmte_roles = committee_roles.get(bioguide_id, [])

    return {
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
        "photo_url":   photo_url(bioguide_id) if bioguide_id else "",
        "initials":    initials(full_name),
        "leadership":  leadership_role,
        "committees":  cmte_roles,
    }

def build():
    print("📥 Fetching legislators-current.json...")
    legislators = fetch_json(
        "https://unitedstates.github.io/congress-legislators/legislators-current.json")
    print(f"  {len(legislators)} members loaded")

    # Leadership map: bioguide_id -> (role_label, tier)
    print("📥 Fetching leadership data...")
    leadership_map = {}
    try:
        leadership = fetch_json(
            "https://unitedstates.github.io/congress-legislators/legislators-current.json")
        # Leadership roles are embedded in the term data
        for m in legislators:
            terms = m.get("terms", [])
            if not terms:
                continue
            term = terms[-1]
            role_title = term.get("title", "")
            # Check leadership roles list
            for role_key, (role_label, tier) in LEADERSHIP_ROLES.items():
                if role_key.lower() in role_title.lower():
                    bid = m.get("id", {}).get("bioguide", "")
                    if bid:
                        leadership_map[bid] = {"label": role_label, "tier": tier}
    except Exception as e:
        print(f"  Leadership fetch error: {e}")

    # Also try the executive/leadership endpoint
    try:
        exec_data = fetch_json(
            "https://unitedstates.github.io/congress-legislators/executive.json")
    except:
        pass

    # Committee roles — fetch from congress-legislators committees
    print("📥 Fetching committee data...")
    committee_roles = {}  # bioguide_id -> [{committee, role}]
    try:
        cmte_membership = fetch_json(
            "https://unitedstates.github.io/congress-legislators/committees-current.json")
        for cmte in cmte_membership:
            cmte_name = cmte.get("name", "")
            for member in cmte.get("members", []):
                bid   = member.get("bioguide_id", "")
                role  = member.get("rank_in_party", 0)
                title = member.get("title", "")
                if not bid:
                    continue
                if bid not in committee_roles:
                    committee_roles[bid] = []
                # Mark chairs and ranking members
                if title.lower() in ["chair", "chairman", "chairwoman", "chairperson"]:
                    committee_roles[bid].append({"committee": cmte_name, "role": "Chair"})
                    # Also set leadership map if not already set
                    if bid not in leadership_map:
                        leadership_map[bid] = {"label": f"Chair, {cmte_name[:30]}", "tier": 4}
                elif title.lower() in ["ranking member", "ranking minority member"]:
                    committee_roles[bid].append({"committee": cmte_name, "role": "Ranking Member"})
                    if bid not in leadership_map:
                        leadership_map[bid] = {"label": f"RM, {cmte_name[:30]}", "tier": 5}
                else:
                    committee_roles[bid].append({"committee": cmte_name, "role": "Member"})
        print(f"  Committee data loaded for {len(committee_roles)} members")
    except Exception as e:
        print(f"  Committee fetch error: {e}")

    # Build member objects
    print("🔨 Building member objects...")
    senators = []
    reps     = []

    for m in legislators:
        member = build_member(m, leadership_map, committee_roles)
        if not member:
            continue
        if member["chamber"] == "senate":
            senators.append(member)
        else:
            reps.append(member)

    # Sort: leadership first (by tier), then alphabetical by last name
    def sort_key(m):
        tier = m["leadership"]["tier"] if m["leadership"] else 99
        return (tier, m["last"])

    senators.sort(key=sort_key)
    reps.sort(key=sort_key)

    print(f"✅ {len(senators)} senators, {len(reps)} representatives")

    # Save members.json
    members_data = {
        "date":      today_iso,
        "generated": generated,
        "senators":  senators,
        "reps":      reps,
    }
    with open("members.json", "w") as f:
        json.dump(members_data, f, indent=2, ensure_ascii=False)
    print("✅ members.json written")

    # Build members.html
    members_json = json.dumps(members_data, ensure_ascii=False)
    html = build_html(members_json, today_str, today_long, generated)
    with open("members.html", "w") as f:
        f.write(html)
    print("✅ members.html written")

def build_html(members_json, today_str, today_long, generated):
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
    --bg: #0D0C0A; --bg-secondary: #0A0908; --bg-card: rgba(255,255,255,0.018);
    --bg-card-open: rgba(255,255,255,0.038); --bg-header: rgba(200,169,110,0.025);
    --text-primary: #E8E0D0; --text-heading: #F0E8D8; --text-secondary: #A09080;
    --text-muted: #908070; --text-dim: #706860; --text-faint: #4A4540;
    --border: rgba(255,255,255,0.07); --border-header: rgba(200,169,110,0.18);
    --border-stat: rgba(255,255,255,0.04); --border-section: rgba(255,255,255,0.05);
    --scrollbar: #2A2820;
    --gold: #C8A96E; --blue: #7FB3D3; --purple: #B39DDB;
    --rep-color: #E07070; --dem-color: #7FB3D3; --ind-color: #B39DDB;
    --rep-bg: rgba(200,80,80,0.1); --dem-bg: rgba(100,160,200,0.1); --ind-bg: rgba(160,120,200,0.1);
    --rep-border: rgba(200,80,80,0.3); --dem-border: rgba(100,160,200,0.3); --ind-border: rgba(160,120,200,0.3);
    --toggle-bg: rgba(255,255,255,0.06); --toggle-border: rgba(255,255,255,0.12);
  }}
  :root.light {{
    --bg: #F5F3EE; --bg-secondary: #EDEAE3; --bg-card: rgba(255,255,255,0.7);
    --bg-card-open: rgba(255,255,255,0.95); --bg-header: rgba(200,169,110,0.06);
    --text-primary: #1A1714; --text-heading: #0E0C0A; --text-secondary: #5A5040;
    --text-muted: #7A6A58; --text-dim: #9A8A78; --text-faint: #C0B0A0;
    --border: rgba(0,0,0,0.08); --border-header: rgba(200,169,110,0.3);
    --border-stat: rgba(0,0,0,0.06); --border-section: rgba(0,0,0,0.06);
    --scrollbar: #D0C8BC;
    --rep-color: #C0404040; --dem-color: #3A7AB0; --ind-color: #7A58B0;
    --rep-bg: rgba(180,60,60,0.08); --dem-bg: rgba(60,120,180,0.08); --ind-bg: rgba(100,60,180,0.08);
    --rep-border: rgba(180,60,60,0.25); --dem-border: rgba(60,120,180,0.25); --ind-border: rgba(100,60,180,0.25);
    --toggle-bg: rgba(0,0,0,0.05); --toggle-border: rgba(0,0,0,0.12);
  }}
  @media (prefers-color-scheme: light) {{
    :root:not(.dark) {{
      --bg: #F5F3EE; --bg-secondary: #EDEAE3; --bg-card: rgba(255,255,255,0.7);
      --bg-card-open: rgba(255,255,255,0.95); --bg-header: rgba(200,169,110,0.06);
      --text-primary: #1A1714; --text-heading: #0E0C0A; --text-secondary: #5A5040;
      --text-muted: #7A6A58; --text-dim: #9A8A78; --text-faint: #C0B0A0;
      --border: rgba(0,0,0,0.08); --border-header: rgba(200,169,110,0.3);
      --border-stat: rgba(0,0,0,0.06); --border-section: rgba(0,0,0,0.06);
      --scrollbar: #D0C8BC;
      --rep-color: #C04040; --dem-color: #3A7AB0; --ind-color: #7A58B0;
      --rep-bg: rgba(180,60,60,0.08); --dem-bg: rgba(60,120,180,0.08); --ind-bg: rgba(100,60,180,0.08);
      --rep-border: rgba(180,60,60,0.25); --dem-border: rgba(60,120,180,0.25); --ind-border: rgba(100,60,180,0.25);
      --toggle-bg: rgba(0,0,0,0.05); --toggle-border: rgba(0,0,0,0.12);
    }}
  }}

  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text-primary); font-family: 'IBM Plex Sans', sans-serif; min-height: 100vh; transition: background 0.2s, color 0.2s; }}
  ::-webkit-scrollbar {{ width: 4px; }}
  ::-webkit-scrollbar-thumb {{ background: var(--scrollbar); border-radius: 2px; }}

  /* ── Nav + Header ── */
  .header {{ border-bottom: 1px solid var(--border-header); padding: 20px 20px 0; background: var(--bg-header); }}
  .header-top {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 14px; }}
  .header-eyebrow {{ font-family: 'IBM Plex Mono', monospace; font-size: 10px; letter-spacing: 0.18em; color: var(--gold); text-transform: uppercase; margin-bottom: 6px; }}
  .header h1 {{ font-family: 'Playfair Display', serif; font-size: clamp(20px,5vw,26px); font-weight: 700; color: var(--text-heading); letter-spacing: -0.01em; margin-bottom: 4px; }}
  .header-timestamp {{ font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: var(--text-muted); letter-spacing: 0.04em; }}
  .theme-toggle {{ background: var(--toggle-bg); border: 1px solid var(--toggle-border); border-radius: 8px; padding: 7px 10px; cursor: pointer; font-size: 16px; line-height: 1; flex-shrink: 0; margin-left: 12px; margin-top: 2px; transition: background 0.15s; }}
  .theme-toggle:hover {{ background: rgba(200,169,110,0.1); border-color: rgba(200,169,110,0.3); }}

  /* ── Page nav tabs ── */
  .page-nav {{ display: flex; gap: 0; margin-top: 2px; }}
  .page-nav a {{
    font-family: 'IBM Plex Mono', monospace; font-size: 11px; letter-spacing: 0.08em;
    color: var(--text-muted); text-decoration: none; padding: 10px 16px 10px;
    border-bottom: 2px solid transparent; transition: all 0.15s;
  }}
  .page-nav a:hover {{ color: var(--gold); }}
  .page-nav a.active {{ color: var(--gold); border-bottom-color: var(--gold); }}

  /* ── Search + controls ── */
  .controls {{ padding: 14px 16px; border-bottom: 1px solid var(--border-section); display: flex; flex-direction: column; gap: 10px; }}
  .search-wrap {{ position: relative; }}
  .search-icon {{ position: absolute; left: 12px; top: 50%; transform: translateY(-50%); font-size: 14px; pointer-events: none; }}
  .search-box {{
    width: 100%; padding: 9px 12px 9px 36px;
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: 8px; color: var(--text-primary);
    font-family: 'IBM Plex Sans', sans-serif; font-size: 13px;
    outline: none; transition: border-color 0.15s;
  }}
  .search-box:focus {{ border-color: rgba(200,169,110,0.4); }}
  .search-box::placeholder {{ color: var(--text-faint); }}

  .group-row {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
  .group-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: var(--text-dim); letter-spacing: 0.08em; text-transform: uppercase; }}
  .group-btn {{
    background: transparent; border: 1px solid var(--border);
    color: var(--text-muted); border-radius: 5px; padding: 4px 10px;
    font-size: 11px; font-family: 'IBM Plex Mono', monospace;
    letter-spacing: 0.05em; cursor: pointer; transition: all 0.15s;
  }}
  .group-btn.active {{ background: rgba(200,169,110,0.13); border-color: rgba(200,169,110,0.4); color: var(--gold); }}

  /* ── Chamber tabs ── */
  .chamber-tabs {{ display: flex; border-bottom: 1px solid var(--border-section); background: var(--bg-secondary); }}
  .chamber-tab {{
    flex: 1; padding: 12px 8px; text-align: center; cursor: pointer;
    font-family: 'IBM Plex Mono', monospace; font-size: 11px; letter-spacing: 0.08em;
    color: var(--text-dim); border-bottom: 2px solid transparent; transition: all 0.15s;
  }}
  .chamber-tab.active {{ color: var(--gold); border-bottom-color: var(--gold); }}
  .chamber-tab-count {{ font-family: 'Playfair Display', serif; font-size: 18px; font-weight: 700; display: block; margin-bottom: 2px; }}

  /* ── Content ── */
  .content {{ padding: 14px 16px; }}
  .section-header {{
    font-family: 'IBM Plex Mono', monospace; font-size: 10px; letter-spacing: 0.12em;
    text-transform: uppercase; color: var(--text-dim);
    padding: 10px 0 8px; margin-bottom: 10px;
    border-bottom: 1px solid var(--border-section);
  }}

  /* ── Two-column party layout ── */
  .party-columns {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }}
  .party-col-header {{
    font-family: 'IBM Plex Mono', monospace; font-size: 9px; letter-spacing: 0.12em;
    text-transform: uppercase; padding: 4px 0; margin-bottom: 6px;
    border-bottom: 2px solid;
  }}
  .party-col-header.rep {{ color: var(--rep-color); border-color: var(--rep-color); }}
  .party-col-header.dem {{ color: var(--dem-color); border-color: var(--dem-color); }}
  .party-col-header.ind {{ color: var(--ind-color); border-color: var(--ind-color); }}

  /* ── Leadership row (side by side) ── */
  .leadership-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }}

  /* ── Member card ── */
  .member-card {{
    border: 1px solid var(--border); border-radius: 8px;
    padding: 12px; background: var(--bg-card);
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 8px; transition: background 0.15s;
  }}
  .member-card:hover {{ background: var(--bg-card-open); }}
  .member-card.leadership {{ border-left: 3px solid var(--gold); }}
  .member-card.chair {{ border-left: 3px solid var(--gold); }}
  .member-card.ranking {{ border-left: 3px solid var(--text-secondary); }}

  /* ── Photo ── */
  .member-photo {{
    width: 44px; height: 54px; border-radius: 4px;
    object-fit: cover; flex-shrink: 0;
    background: var(--bg-secondary);
  }}
  .member-initials {{
    width: 44px; height: 54px; border-radius: 4px;
    display: flex; align-items: center; justify-content: center;
    font-family: 'Playfair Display', serif; font-size: 16px; font-weight: 700;
    flex-shrink: 0; color: white;
  }}
  .initials-rep {{ background: rgba(200,80,80,0.6); }}
  .initials-dem {{ background: rgba(60,120,180,0.6); }}
  .initials-ind {{ background: rgba(120,80,180,0.6); }}

  /* ── Member info ── */
  .member-info {{ flex: 1; min-width: 0; }}
  .member-name {{ font-size: 13px; font-weight: 600; color: var(--text-primary); line-height: 1.3; margin-bottom: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .member-meta {{ font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: var(--text-muted); margin-bottom: 4px; }}
  .member-role {{
    display: inline-block; font-family: 'IBM Plex Mono', monospace;
    font-size: 9px; letter-spacing: 0.06em; padding: 2px 6px;
    border-radius: 3px; text-transform: uppercase; font-weight: 700;
  }}
  .role-leader {{ background: rgba(200,169,110,0.15); color: var(--gold); border: 1px solid rgba(200,169,110,0.35); }}
  .role-chair  {{ background: rgba(200,169,110,0.1);  color: var(--gold); border: 1px solid rgba(200,169,110,0.25); }}
  .role-ranking {{ background: var(--bg-secondary); color: var(--text-secondary); border: 1px solid var(--border); }}
  .role-whip   {{ background: rgba(160,120,200,0.1); color: var(--purple); border: 1px solid rgba(160,120,200,0.3); }}

  /* ── Party badge ── */
  .party-badge {{
    font-family: 'IBM Plex Mono', monospace; font-size: 9px; font-weight: 700;
    padding: 1px 5px; border-radius: 3px; margin-left: 4px;
  }}
  .badge-rep {{ background: var(--rep-bg); color: var(--rep-color); border: 1px solid var(--rep-border); }}
  .badge-dem {{ background: var(--dem-bg); color: var(--dem-color); border: 1px solid var(--dem-border); }}
  .badge-ind {{ background: var(--ind-bg); color: var(--ind-color); border: 1px solid var(--ind-border); }}

  .empty {{ text-align: center; padding: 40px; color: var(--text-faint); font-size: 13px; }}
  .source-note {{ margin-top: 20px; padding: 12px 14px; background: rgba(255,255,255,0.012); border: 1px solid var(--border); border-radius: 6px; font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: var(--text-dim); line-height: 1.6; }}

  /* ── State group view ── */
  .state-group {{ margin-bottom: 16px; }}
  .state-header {{ font-family: 'IBM Plex Mono', monospace; font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--gold); padding: 6px 0; margin-bottom: 6px; border-bottom: 1px solid var(--border); }}

  /* ── Committee group view ── */
  .cmte-group {{ margin-bottom: 16px; }}
  .cmte-header {{ font-family: 'IBM Plex Mono', monospace; font-size: 11px; letter-spacing: 0.08em; color: var(--text-muted); padding: 6px 0; margin-bottom: 6px; border-bottom: 1px solid var(--border); }}

  .hidden {{ display: none !important; }}
</style>
</head>
<body>

<div class="header">
  <div class="header-top">
    <div>
      <div class="header-eyebrow">🏛 Congressional Hearing Tracker</div>
      <h1>Congressional Directory</h1>
      <div class="header-timestamp">Updated {generated} · {today_long} · Refreshes daily</div>
    </div>
    <button class="theme-toggle" id="theme-toggle" onclick="toggleTheme()" title="Toggle light/dark mode">☀️</button>
  </div>
  <nav class="page-nav">
    <a href="index.html">Hearings</a>
    <a href="members.html" class="active">Members</a>
  </nav>
</div>

<div class="controls">
  <div class="search-wrap">
    <span class="search-icon">🔍</span>
    <input class="search-box" id="search" type="text" placeholder="Search by name, state, or committee..." oninput="applyFilters()">
  </div>
  <div class="group-row">
    <span class="group-label">Group by</span>
    <button class="group-btn active" onclick="setGroup('party')">Party</button>
    <button class="group-btn" onclick="setGroup('state')">State</button>
    <button class="group-btn" onclick="setGroup('committee')">Committee</button>
    <button class="group-btn" onclick="setGroup('leadership')">Leadership</button>
  </div>
</div>

<div class="chamber-tabs">
  <div class="chamber-tab active" id="tab-senate" onclick="setChamber('senate')">
    <span class="chamber-tab-count" id="senate-count">100</span>
    SENATE
  </div>
  <div class="chamber-tab" id="tab-house" onclick="setChamber('house')">
    <span class="chamber-tab-count" id="house-count">435</span>
    HOUSE
  </div>
</div>

<div class="content" id="content"></div>

<script>
const DATA = {members_json};
const SENATORS = DATA.senators || [];
const REPS     = DATA.reps || [];

let currentChamber = 'senate';
let currentGroup   = 'party';
let searchTerm     = '';

// ── Theme ─────────────────────────────────────────────────────────────────────
function getSystemTheme() {{ return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'; }}
function applyTheme(t) {{
  document.documentElement.classList.remove('light','dark');
  document.documentElement.classList.add(t);
  document.getElementById('theme-toggle').textContent = t==='dark'?'☀️':'🌙';
}}
function toggleTheme() {{
  const next = document.documentElement.classList.contains('light') ? 'dark' : 'light';
  localStorage.setItem('theme', next); applyTheme(next);
}}
(function() {{ applyTheme(localStorage.getItem('theme') || getSystemTheme()); }})();
window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', e => {{
  if (!localStorage.getItem('theme')) applyTheme(e.matches ? 'light' : 'dark');
}});

// ── Helpers ───────────────────────────────────────────────────────────────────
function roleClass(label) {{
  if (!label) return '';
  const l = label.toLowerCase();
  if (l.includes('leader') || l.includes('speaker') || l.includes('pro tempore')) return 'role-leader';
  if (l.includes('whip')) return 'role-whip';
  if (l.includes('chair') && !l.includes('rm') && !l.includes('ranking')) return 'role-chair';
  if (l.includes('ranking') || l.includes('rm,')) return 'role-ranking';
  return 'role-chair';
}}

function memberCard(m) {{
  const pc = m.party_class;
  const roleLabel  = m.leadership ? m.leadership.label : '';
  const roleTier   = m.leadership ? m.leadership.tier  : 99;
  const cardClass  = roleTier <= 3 ? 'leadership' : roleTier <= 4 ? 'chair' : roleTier <= 5 ? 'ranking' : '';
  const roleHtml   = roleLabel
    ? `<span class="member-role ${{roleClass(roleLabel)}}">${{roleLabel}}</span>`
    : '';
  const district = m.district ? ` · Dist. ${{m.district}}` : '';
  const meta = `${{m.state}}${{district}} <span class="party-badge badge-${{pc}}">${{m.party_short}}</span>`;

  // Photo with initials fallback
  const photoHtml = m.photo_url
    ? `<img class="member-photo" src="${{m.photo_url}}"
         onerror="this.style.display='none';this.nextElementSibling.style.display='flex';"
         alt="${{m.name}}" loading="lazy">
       <div class="member-initials initials-${{pc}}" style="display:none">${{m.initials}}</div>`
    : `<div class="member-initials initials-${{pc}}">${{m.initials}}</div>`;

  return `
    <div class="member-card ${{cardClass}}"
         data-name="${{m.name.toLowerCase()}}"
         data-state="${{m.state.toLowerCase()}}"
         data-party="${{m.party_class}}"
         data-committees="${{m.committees.map(c=>c.committee).join('|').toLowerCase()}}"
         data-role="${{roleLabel.toLowerCase()}}">
      ${{photoHtml}}
      <div class="member-info">
        <div class="member-name">${{m.name}}</div>
        <div class="member-meta">${{meta}}</div>
        ${{roleHtml}}
      </div>
    </div>`;
}}

// ── Group: Party ──────────────────────────────────────────────────────────────
function renderParty(members) {{
  const leaders   = members.filter(m => m.leadership && m.leadership.tier <= 3);
  const chairs    = members.filter(m => m.leadership && m.leadership.tier === 4);
  const rankings  = members.filter(m => m.leadership && m.leadership.tier === 5);
  const rest      = members.filter(m => !m.leadership || m.leadership.tier > 5);

  const majParty  = currentChamber === 'senate' ? 'rep' : 'rep'; // R is majority in both currently
  const minParty  = 'dem';

  let html = '';

  // Leadership
  if (leaders.length) {{
    html += `<div class="section-header">── Party Leadership</div>`;
    html += `<div class="leadership-grid">`;
    const majLeaders = leaders.filter(m => m.party_class === majParty);
    const minLeaders = leaders.filter(m => m.party_class !== majParty);
    const maxL = Math.max(majLeaders.length, minLeaders.length);
    for (let i = 0; i < maxL; i++) {{
      html += majLeaders[i] ? memberCard(majLeaders[i]) : '<div></div>';
      html += minLeaders[i] ? memberCard(minLeaders[i]) : '<div></div>';
    }}
    html += `</div>`;
  }}

  // Chairs + Ranking Members
  if (chairs.length || rankings.length) {{
    html += `<div class="section-header">── Committee Chairs & Ranking Members</div>`;
    html += `<div class="leadership-grid">`;
    const allChairs   = [...chairs, ...rankings].filter(m => m.party_class === majParty);
    const allRankings = [...chairs, ...rankings].filter(m => m.party_class !== majParty);
    const maxC = Math.max(allChairs.length, allRankings.length);
    for (let i = 0; i < maxC; i++) {{
      html += allChairs[i]   ? memberCard(allChairs[i])   : '<div></div>';
      html += allRankings[i] ? memberCard(allRankings[i]) : '<div></div>';
    }}
    html += `</div>`;
  }}

  // All members — two column party split
  if (rest.length) {{
    html += `<div class="section-header">── All Members</div>`;
    const majority = rest.filter(m => m.party_class === majParty);
    const minority = rest.filter(m => m.party_class === minParty);
    const indies   = rest.filter(m => m.party_class === 'ind');
    html += `<div class="party-columns">
      <div>
        <div class="party-col-header rep">Republican · ${{majority.length}}</div>
        ${{majority.map(memberCard).join('')}}
      </div>
      <div>
        <div class="party-col-header dem">Democrat · ${{minority.length}}</div>
        ${{minority.map(memberCard).join('')}}
        ${{indies.length ? `<div class="party-col-header ind" style="margin-top:10px">Independent · ${{indies.length}}</div>${{indies.map(memberCard).join('')}}` : ''}}
      </div>
    </div>`;
  }}

  return html || '<div class="empty">No members found.</div>';
}}

// ── Group: State ──────────────────────────────────────────────────────────────
function renderState(members) {{
  const byState = {{}};
  members.forEach(m => {{
    if (!byState[m.state]) byState[m.state] = [];
    byState[m.state].push(m);
  }});
  const states = Object.keys(byState).sort();
  return states.map(s => `
    <div class="state-group">
      <div class="state-header">${{s}}</div>
      ${{byState[s].map(memberCard).join('')}}
    </div>`).join('') || '<div class="empty">No members found.</div>';
}}

// ── Group: Committee ──────────────────────────────────────────────────────────
function renderCommittee(members) {{
  const byCmte = {{}};
  members.forEach(m => {{
    if (!m.committees || !m.committees.length) {{
      if (!byCmte['No Committee Data']) byCmte['No Committee Data'] = [];
      byCmte['No Committee Data'].push(m);
      return;
    }}
    m.committees.filter(c => c.role !== 'Member').forEach(c => {{
      if (!byCmte[c.committee]) byCmte[c.committee] = [];
      byCmte[c.committee].push(m);
    }});
  }});
  const cmtes = Object.keys(byCmte).sort();
  return cmtes.map(c => `
    <div class="cmte-group">
      <div class="cmte-header">${{c}}</div>
      ${{byCmte[c].map(memberCard).join('')}}
    </div>`).join('') || '<div class="empty">No members found.</div>';
}}

// ── Group: Leadership only ────────────────────────────────────────────────────
function renderLeadership(members) {{
  const leaders = members.filter(m => m.leadership);
  if (!leaders.length) return '<div class="empty">No leadership data found.</div>';
  return `<div class="section-header">── Leadership & Committee Chairs</div>` +
    leaders.map(memberCard).join('');
}}

// ── Filter + Render ───────────────────────────────────────────────────────────
function getMembers() {{
  return currentChamber === 'senate' ? SENATORS : REPS;
}}

function applyFilters() {{
  searchTerm = document.getElementById('search').value.toLowerCase().trim();
  render();
}}

function filterMembers(members) {{
  if (!searchTerm) return members;
  return members.filter(m => {{
    return m.name.toLowerCase().includes(searchTerm) ||
           m.state.toLowerCase().includes(searchTerm) ||
           m.committees.some(c => c.committee.toLowerCase().includes(searchTerm)) ||
           (m.leadership && m.leadership.label.toLowerCase().includes(searchTerm));
  }});
}}

function render() {{
  const members  = filterMembers(getMembers());
  const content  = document.getElementById('content');

  let html = '';
  if (currentGroup === 'party')      html = renderParty(members);
  else if (currentGroup === 'state') html = renderState(members);
  else if (currentGroup === 'committee') html = renderCommittee(members);
  else if (currentGroup === 'leadership') html = renderLeadership(members);

  content.innerHTML = html + `
    <div class="source-note">ℹ Data: unitedstates.github.io/congress-legislators · Photos: bioguide.congress.gov · Refreshes daily</div>`;
}}

function setChamber(c) {{
  currentChamber = c;
  document.querySelectorAll('.chamber-tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + c).classList.add('active');
  render();
}}

function setGroup(g) {{
  currentGroup = g;
  document.querySelectorAll('.group-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  render();
}}

// ── Init ──────────────────────────────────────────────────────────────────────
document.getElementById('senate-count').textContent = SENATORS.length;
document.getElementById('house-count').textContent  = REPS.length;
render();
</script>
</body>
</html>"""

build()
