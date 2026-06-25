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

# ── 119th Congress institutional leadership (hardcoded by bioguide ID) ─────────
# Changes only after elections or resignations — update once per Congress.
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
            if not is_full_cmte:
                continue
            tl = title.lower() if title else ""
            if "chair" in tl and "ranking" not in tl:
                if bid not in chair_map:
                    chair_map[bid] = {"label": "Chair", "tier": 4, "committee": cmte_name}
            elif "ranking" in tl:
                if bid not in chair_map:
                    chair_map[bid] = {"label": "Ranking Member", "tier": 5, "committee": cmte_name}

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
        }

        if chamber == "senate":
            senators.append(member)
        else:
            reps.append(member)

    # Sort: leaders first (by tier), then alpha by last name
    def sort_key(m):
        tier = m["leadership"]["tier"] if m["leadership"] else 99
        return (tier, m["last"])

    senators.sort(key=sort_key)
    reps.sort(key=sort_key)

    print(f"✅ {len(senators)} senators, {len(reps)} representatives")

    # Count leaders
    sen_leaders = sum(1 for m in senators if m["leadership"])
    rep_leaders = sum(1 for m in reps if m["leadership"])
    print(f"  Senate leaders/chairs: {sen_leaders}")
    print(f"  House leaders/chairs:  {rep_leaders}")

    members_data = {
        "date":      today_iso,
        "generated": generated,
        "senators":  senators,
        "reps":      reps,
    }

    with open("members.json", "w", encoding="utf-8") as f:
        json.dump(members_data, f, indent=2, ensure_ascii=False)
    print("✅ members.json written")

    members_json = json.dumps(members_data, ensure_ascii=False)
    with open("members.html", "w", encoding="utf-8") as f:
        f.write(build_html(members_json))
    print("✅ members.html written")

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
  .group-btn{{background:transparent;border:1px solid var(--bdr);color:var(--text-m);border-radius:5px;padding:4px 10px;font-size:11px;font-family:'IBM Plex Mono',monospace;letter-spacing:0.05em;cursor:pointer;transition:all 0.15s}}
  .group-btn.active{{background:rgba(200,169,110,0.13);border-color:rgba(200,169,110,0.4);color:var(--gold)}}

  /* Chamber tabs */
  .chamber-tabs{{display:flex;border-bottom:1px solid var(--bdr-sec);background:var(--bg-sec)}}
  .chamber-tab{{flex:1;padding:12px 8px;text-align:center;cursor:pointer;font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:0.08em;color:var(--text-d);border-bottom:2px solid transparent;transition:all 0.15s}}
  .chamber-tab.active{{color:var(--gold);border-bottom-color:var(--gold)}}
  .tab-count{{font-family:'Playfair Display',serif;font-size:18px;font-weight:700;display:block;margin-bottom:2px}}

  /* Content */
  .content{{padding:14px 16px}}
  .section-hdr{{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;color:var(--text-d);padding:10px 0 8px;margin-bottom:10px;border-bottom:1px solid var(--bdr-sec)}}

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
    border:1px solid var(--bdr);border-radius:10px;
    background:var(--bg-card);margin-bottom:8px;
    cursor:pointer;transition:background 0.15s, transform 0.15s;
    overflow:hidden;
  }}
  .member-card:hover {{ background:var(--bg-card-h); transform:translateY(-1px); }}
  .card-leader {{ border-left:3px solid var(--gold); }}
  .card-chair  {{ border-left:3px solid rgba(200,169,110,0.5); }}
  .card-ranking{{ border-left:3px solid var(--bdr); }}

  .card-face {{ display:flex;align-items:center;gap:12px;padding:12px 14px; }}

  /* Photo — 80×100px */
  .photo {{
    width:80px;height:100px;border-radius:6px;
    object-fit:cover;object-position:top;
    flex-shrink:0;background:var(--bg-sec);
    border:1px solid var(--bdr);
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
const DATA     = {members_json};
const SENATORS = DATA.senators || [];
const REPS     = DATA.reps     || [];
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
  // Only show badge for institutional party leaders (tier 1-3)
  // Chairs and Ranking Members (tier 4-5) are shown in the modal only
  if(tier > 3) return '';
  const label = m.leadership.label;
  const l     = label.toLowerCase();
  let cls = 'role-chair';
  if(l.includes('leader')||l.includes('speaker')||l.includes('pro tempore')) cls='role-leader';
  else if(l.includes('whip')) cls='role-whip';
  else if(l.includes('conference')||l.includes('caucus')||l.includes('policy')) cls='role-chair';
  return `<span class="mrole ${{cls}}">${{label}}</span>`;
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
  // Show/hide CBC panel
  const panel = document.getElementById('cbc-panel');
  if(panel) panel.style.display = c==='cbc' ? 'block' : 'none';
  render();
}}

// ── CBC Panel ─────────────────────────────────────────────────────────────────
function buildCbcPanel(){{
  const cbcMembers = [...SENATORS,...REPS].filter(m=>(m.caucuses||[]).includes('cbc'));
  if(!cbcMembers.length) return '';
  const senate = cbcMembers.filter(m=>m.chamber==='senate');
  const house   = cbcMembers.filter(m=>m.chamber==='house');

  const memberList = (arr) => arr.map(m=>{{
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
  }}).join('');

  return `
    <div style="margin-bottom:6px">
      <div class="section-hdr">── Congressional Black Caucus · ${{cbcMembers.length}} Members</div>
      ${{senate.length ? `<div class="party-col-hdr col-dem" style="margin-bottom:8px">Senate · ${{senate.length}}</div>
        <div class="party-cols">${{memberList(senate)}}</div>` : ''}}
      ${{house.length ? `<div class="party-col-hdr col-dem" style="margin-top:10px;margin-bottom:8px">House · ${{house.length}}</div>
        <div class="party-cols">${{memberList(house)}}</div>` : ''}}
    </div>`;
}}

// ── Render modes ──────────────────────────────────────────────────────────────
function renderParty(members){{
  const leaders  = members.filter(m=>m.leadership&&m.leadership.tier<=3);
  const chairs   = members.filter(m=>m.leadership&&m.leadership.tier===4);
  const rankings = members.filter(m=>m.leadership&&m.leadership.tier===5);
  const rest     = members.filter(m=>!m.leadership||m.leadership.tier>5);
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

  if(rest.length){{
    h += `<div class="section-hdr">── Members (${{rest.length}})</div>
    <div class="party-cols">
      <div>
        <div class="party-col-hdr col-rep">Republican · ${{maj.length}}</div>
        ${{maj.map(card).join('')}}
      </div>
      <div>
        <div class="party-col-hdr col-dem">Democrat · ${{min.length}}</div>
        ${{min.map(card).join('')}}
        ${{ind.length?`<div class="party-col-hdr col-ind" style="margin-top:10px">Independent · ${{ind.length}}</div>${{ind.map(card).join('')}}`:''}}
      </div>
    </div>`;
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

// ── Main render ───────────────────────────────────────────────────────────────
function render(){{
  CURRENT_MEMBERS = [];

  // CBC panel — always rebuild so indices are fresh
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

  document.getElementById('content').innerHTML = html +
    `<div class="source-note">ℹ Data: github.com/unitedstates/congress-legislators · Photos: bioguide.congress.gov · Refreshes daily</div>`;
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
document.getElementById('cnt-house').textContent  = REPS.length;
render();
</script>
</body>
</html>"""

build()
