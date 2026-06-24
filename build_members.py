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
    print("🔗 Building committee role map...")
    cmte_roles_map = {}  # bioguide -> [{committee, role, rank}]
    chair_map    = {}    # bioguide -> leadership dict (for chairs/RMs)
    for thomas_id, members in cmte_membership.items():
        cmte_name = cmte_names.get(thomas_id, thomas_id)
        for m in members:
            bid   = m.get("bioguide", "")
            title = m.get("title", "")
            rank  = m.get("rank", 99)
            party = m.get("party", "")
            if not bid:
                continue
            if bid not in cmte_roles_map:
                cmte_roles_map[bid] = []
            role = title if title else ("Member")
            cmte_roles_map[bid].append({
                "committee": cmte_name,
                "role":      role,
                "rank":      rank,
            })
            # Set chair/RM in leadership map
            tl = title.lower() if title else ""
            if "chair" in tl and "ranking" not in tl:
                if bid not in chair_map:
                    # Shorten committee name for display
                    short = re.sub(r"^(House|Senate)\s+(Committee on|Select Committee on|Special Committee on)\s+", "", cmte_name)
                    short = short[:35]
                    chair_map[bid] = {"label": f"Chair, {short}", "tier": 4}
            elif "ranking" in tl:
                if bid not in chair_map:
                    short = re.sub(r"^(House|Senate)\s+(Committee on|Select Committee on|Special Committee on)\s+", "", cmte_name)
                    short = short[:30]
                    chair_map[bid] = {"label": f"RM, {short}", "tier": 5}

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

        # Leadership: check term title first, then chair_map
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
    --bg:#0D0C0A;--bg-sec:#0A0908;--bg-card:rgba(255,255,255,0.018);--bg-card-h:rgba(255,255,255,0.038);
    --bg-hdr:rgba(200,169,110,0.025);--text:#E8E0D0;--text-h:#F0E8D8;--text-s:#A09080;
    --text-m:#908070;--text-d:#706860;--text-f:#4A4540;
    --bdr:rgba(255,255,255,0.07);--bdr-h:rgba(200,169,110,0.18);--bdr-s:rgba(255,255,255,0.04);
    --bdr-sec:rgba(255,255,255,0.05);--scroll:#2A2820;
    --gold:#C8A96E;--blue:#7FB3D3;--purple:#B39DDB;
    --rep:#E07070;--dem:#7FB3D3;--ind:#B39DDB;
    --rep-bg:rgba(200,80,80,0.1);--dem-bg:rgba(100,160,200,0.1);--ind-bg:rgba(160,120,200,0.1);
    --rep-br:rgba(200,80,80,0.3);--dem-br:rgba(100,160,200,0.3);--ind-br:rgba(160,120,200,0.3);
    --tog-bg:rgba(255,255,255,0.06);--tog-br:rgba(255,255,255,0.12);
  }}
  :root.light {{
    --bg:#F5F3EE;--bg-sec:#EDEAE3;--bg-card:rgba(255,255,255,0.7);--bg-card-h:rgba(255,255,255,0.95);
    --bg-hdr:rgba(200,169,110,0.06);--text:#1A1714;--text-h:#0E0C0A;--text-s:#5A5040;
    --text-m:#7A6A58;--text-d:#9A8A78;--text-f:#C0B0A0;
    --bdr:rgba(0,0,0,0.08);--bdr-h:rgba(200,169,110,0.3);--bdr-s:rgba(0,0,0,0.06);
    --bdr-sec:rgba(0,0,0,0.06);--scroll:#D0C8BC;
    --rep:#C04040;--dem:#3A7AB0;--ind:#7A58B0;
    --rep-bg:rgba(180,60,60,0.08);--dem-bg:rgba(60,120,180,0.08);--ind-bg:rgba(100,60,180,0.08);
    --rep-br:rgba(180,60,60,0.25);--dem-br:rgba(60,120,180,0.25);--ind-br:rgba(100,60,180,0.25);
    --tog-bg:rgba(0,0,0,0.05);--tog-br:rgba(0,0,0,0.12);
  }}
  @media(prefers-color-scheme:light){{:root:not(.dark){{
    --bg:#F5F3EE;--bg-sec:#EDEAE3;--bg-card:rgba(255,255,255,0.7);--bg-card-h:rgba(255,255,255,0.95);
    --bg-hdr:rgba(200,169,110,0.06);--text:#1A1714;--text-h:#0E0C0A;--text-s:#5A5040;
    --text-m:#7A6A58;--text-d:#9A8A78;--text-f:#C0B0A0;
    --bdr:rgba(0,0,0,0.08);--bdr-h:rgba(200,169,110,0.3);--bdr-s:rgba(0,0,0,0.06);
    --bdr-sec:rgba(0,0,0,0.06);--scroll:#D0C8BC;
    --rep:#C04040;--dem:#3A7AB0;--ind:#7A58B0;
    --rep-bg:rgba(180,60,60,0.08);--dem-bg:rgba(60,120,180,0.08);--ind-bg:rgba(100,60,180,0.08);
    --rep-br:rgba(180,60,60,0.25);--dem-br:rgba(60,120,180,0.25);--ind-br:rgba(100,60,180,0.25);
    --tog-bg:rgba(0,0,0,0.05);--tog-br:rgba(0,0,0,0.12);
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

  /* Member card */
  .member-card {{
    border:1px solid var(--bdr);border-radius:10px;
    background:var(--bg-card);margin-bottom:8px;
    cursor:pointer;transition:background 0.15s;
    overflow:hidden;
  }}
  .member-card:hover {{background:var(--bg-card-h)}}
  .card-leader{{border-left:3px solid var(--gold)}}
  .card-chair{{border-left:3px solid rgba(200,169,110,0.5)}}
  .card-ranking{{border-left:3px solid var(--bdr)}}

  /* Collapsed face */
  .card-face {{
    display:flex;align-items:center;gap:12px;padding:10px 12px;
  }}

  /* Photo — 80×100px as requested */
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
  .i-rep{{background:rgba(160,50,50,0.75)}}
  .i-dem{{background:rgba(50,100,160,0.75)}}
  .i-ind{{background:rgba(100,50,160,0.75)}}

  /* Collapsed info */
  .card-face .info {{flex:1;min-width:0}}
  .mname {{
    font-size:13px;font-weight:700;color:var(--text);
    line-height:1.3;margin-bottom:3px;
  }}
  .mmeta {{
    font-family:'IBM Plex Mono',monospace;font-size:10px;
    color:var(--text-m);margin-bottom:5px;
  }}
  .mrole {{
    display:inline-block;font-family:'IBM Plex Mono',monospace;
    font-size:9px;letter-spacing:0.05em;padding:2px 6px;
    border-radius:3px;text-transform:uppercase;font-weight:700;
    line-height:1.4;
  }}
  .role-leader{{background:rgba(200,169,110,0.15);color:var(--gold);border:1px solid rgba(200,169,110,0.35)}}
  .role-whip{{background:rgba(160,120,200,0.1);color:var(--purple);border:1px solid rgba(160,120,200,0.3)}}
  .role-chair{{background:rgba(200,169,110,0.08);color:var(--gold);border:1px solid rgba(200,169,110,0.2)}}
  .role-rm{{background:var(--bg-sec);color:var(--text-s);border:1px solid var(--bdr)}}

  .chevron {{
    font-size:10px;color:var(--text-f);flex-shrink:0;
    transition:transform 0.2s;margin-left:4px;
  }}
  .member-card.open .chevron {{transform:rotate(180deg)}}

  /* Expanded body */
  .card-body {{
    display:none;
    padding:0 12px 14px 12px;
    border-top:1px solid var(--bdr);
    margin-top:0;
  }}
  .member-card.open .card-body {{display:block}}

  .card-body-inner {{
    display:flex;gap:14px;padding-top:12px;
  }}

  /* Larger photo in expanded view */
  .photo-lg {{
    width:100px;height:125px;border-radius:6px;
    object-fit:cover;object-position:top;
    flex-shrink:0;background:var(--bg-sec);
    border:1px solid var(--bdr);
  }}
  .initials-lg {{
    width:100px;height:125px;border-radius:6px;
    display:flex;align-items:center;justify-content:center;
    font-family:'Playfair Display',serif;font-size:36px;font-weight:700;
    flex-shrink:0;color:white;
  }}

  .card-details {{flex:1;min-width:0}}
  .detail-section {{margin-bottom:10px}}
  .detail-label {{
    font-family:'IBM Plex Mono',monospace;font-size:9px;
    letter-spacing:0.1em;text-transform:uppercase;
    color:var(--text-d);margin-bottom:4px;
  }}
  .detail-value {{
    font-size:12px;color:var(--text-s);line-height:1.5;
  }}
  .cmte-row {{
    font-size:11px;color:var(--text-s);line-height:1.6;
    padding-left:10px;border-left:2px solid var(--bdr);
    margin-bottom:3px;
  }}
  .cmte-role-badge {{
    font-family:'IBM Plex Mono',monospace;font-size:9px;
    color:var(--gold);margin-right:4px;font-weight:700;
  }}

  /* Party badge */
  .pbadge{{font-family:'IBM Plex Mono',monospace;font-size:9px;font-weight:700;padding:1px 5px;border-radius:3px;margin-left:4px}}
  .b-rep{{background:var(--rep-bg);color:var(--rep);border:1px solid var(--rep-br)}}
  .b-dem{{background:var(--dem-bg);color:var(--dem);border:1px solid var(--dem-br)}}
  .b-ind{{background:var(--ind-bg);color:var(--ind);border:1px solid var(--ind-br)}}

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
</div>

<div class="chamber-tabs">
  <div class="chamber-tab active" id="tab-senate" onclick="setChamber('senate')">
    <span class="tab-count" id="cnt-senate">—</span>SENATE
  </div>
  <div class="chamber-tab" id="tab-house" onclick="setChamber('house')">
    <span class="tab-count" id="cnt-house">—</span>HOUSE
  </div>
</div>

<div class="content" id="content"></div>

<script>
const DATA     = {members_json};
const SENATORS = DATA.senators || [];
const REPS     = DATA.reps     || [];
let chamber = 'senate';
let group   = 'party';

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
function roleHtml(m, small=true){{
  if(!m.leadership) return '';
  const l = m.leadership.label.toLowerCase();
  let cls = 'role-chair';
  if(l.includes('leader')||l.includes('speaker')||l.includes('pro tempore')) cls='role-leader';
  else if(l.includes('whip')) cls='role-whip';
  else if(l.includes('rm,')||l.includes('ranking')) cls='role-rm';
  return `<span class="mrole ${{cls}}">${{m.leadership.label}}</span>`;
}}

function roleClass(m){{
  if(!m.leadership) return '';
  const t = m.leadership.tier;
  if(t<=3) return 'card-leader';
  if(t===4) return 'card-chair';
  if(t===5) return 'card-ranking';
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

function yearsInOffice(m){{
  // Find earliest term start
  return ''; // data doesn't include term history in current dataset
}}

function fullRoleDescription(m){{
  if(!m.leadership) return '';
  const label = m.leadership.label;
  const tier  = m.leadership.tier;
  if(tier === 1) return label + (m.chamber==='senate' ? ' of the United States Senate' : ' of the United States House of Representatives');
  if(tier === 2) return label + (m.chamber==='senate' ? ', United States Senate' : ', United States House of Representatives');
  // Chair/RM — the label already has committee name
  return label.replace('RM,', 'Ranking Member,').replace('Chair,', 'Chair,');
}}

function committeeRows(m){{
  const cmtes = (m.committees||[]);
  if(!cmtes.length) return '<div class="detail-value" style="color:var(--text-f);font-style:italic">No committee data available</div>';
  // Sort: Chair first, then Ranking Member, then Member
  const order = {{'Chair':0,'Ranking Member':1,'Chairman':0,'Chairwoman':0,'Chairperson':0,'Member':2}};
  const sorted = [...cmtes].sort((a,b)=>((order[a.role]||2)-(order[b.role]||2)));
  return sorted.map(c=>{{
    const isChairRole = c.role && (c.role.toLowerCase().includes('chair') && !c.role.toLowerCase().includes('ranking'));
    const isRM = c.role && c.role.toLowerCase().includes('ranking');
    const badge = isChairRole ? `<span class="cmte-role-badge">Chair</span>`
                : isRM       ? `<span class="cmte-role-badge" style="color:var(--text-s)">Ranking Member</span>`
                : '';
    return `<div class="cmte-row">${{badge}}${{c.committee}}</div>`;
  }}).join('');
}}

function card(m){{
  const pc  = m.party_class;
  const cc  = roleClass(m);
  const dist = m.district ? ` · District ${{m.district}}` : '';
  const partyFull = pc==='rep'?'Republican':pc==='dem'?'Democrat':'Independent';
  const chamberFull = m.chamber==='senate'?'United States Senate':'United States House of Representatives';
  const fullRole = fullRoleDescription(m);

  return `<div class="member-card ${{cc}}" onclick="this.classList.toggle('open')">
    <div class="card-face">
      ${{photoEl(m,'photo','initials-box')}}
      <div class="info">
        <div class="mname">${{m.name}}</div>
        <div class="mmeta">${{m.state}}${{dist}} <span class="pbadge b-${{pc}}">${{m.party_short}}</span></div>
        ${{roleHtml(m)}}
      </div>
      <span class="chevron">▼</span>
    </div>
    <div class="card-body">
      <div class="card-body-inner">
        ${{photoEl(m,'photo-lg','initials-lg')}}
        <div class="card-details">
          <div class="detail-section">
            <div class="detail-label">Full Name</div>
            <div class="detail-value">${{m.name}}</div>
          </div>
          <div class="detail-section">
            <div class="detail-label">Chamber</div>
            <div class="detail-value">${{chamberFull}}</div>
          </div>
          <div class="detail-section">
            <div class="detail-label">Party</div>
            <div class="detail-value">${{partyFull}}</div>
          </div>
          <div class="detail-section">
            <div class="detail-label">State${{m.district?' · District':''}}</div>
            <div class="detail-value">${{m.state}}${{m.district?' · District '+m.district:''}}</div>
          </div>
          ${{fullRole ? `<div class="detail-section">
            <div class="detail-label">Leadership Role</div>
            <div class="detail-value">${{fullRole}}</div>
          </div>` : ''}}
          <div class="detail-section">
            <div class="detail-label">Committee Assignments</div>
            ${{committeeRows(m)}}
          </div>
        </div>
      </div>
    </div>
  </div>`;
}}

// ── Filter ────────────────────────────────────────────────────────────────────
function filtered(){{
  const q = document.getElementById('search').value.toLowerCase().trim();
  const pool = chamber==='senate' ? SENATORS : REPS;
  if(!q) return pool;
  return pool.filter(m=>
    m.name.toLowerCase().includes(q) ||
    m.state.toLowerCase().includes(q) ||
    m.committees.some(c=>c.committee.toLowerCase().includes(q)) ||
    (m.leadership?.label||'').toLowerCase().includes(q)
  );
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
    const mL = leaders.filter(m=>m.party_class==='rep');
    const iL = leaders.filter(m=>m.party_class!=='rep');
    const mx = Math.max(mL.length,iL.length);
    for(let i=0;i<mx;i++){{
      h += mL[i]?card(mL[i]):'<div></div>';
      h += iL[i]?card(iL[i]):'<div></div>';
    }}
    h += '</div>';
  }}

  if(chairs.length||rankings.length){{
    h += `<div class="section-hdr">── Committee Chairs & Ranking Members</div><div class="leader-grid">`;
    const mC = [...chairs,...rankings].filter(m=>m.party_class==='rep');
    const iC = [...chairs,...rankings].filter(m=>m.party_class!=='rep');
    const mx = Math.max(mC.length,iC.length);
    for(let i=0;i<mx;i++){{
      h += mC[i]?card(mC[i]):'<div></div>';
      h += iC[i]?card(iC[i]):'<div></div>';
    }}
    h += '</div>';
  }}

  if(rest.length){{
    h += `<div class="section-hdr">── All Members</div>
    <div class="party-cols">
      <div><div class="party-col-hdr col-rep">Republican · ${{maj.length}}</div>${{maj.map(card).join('')}}</div>
      <div>
        <div class="party-col-hdr col-dem">Democrat · ${{min.length}}</div>${{min.map(card).join('')}}
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
  const members = filtered();
  let html = '';
  if(group==='party')      html = renderParty(members);
  else if(group==='state') html = renderState(members);
  else if(group==='committee') html = renderCommittee(members);
  else html = renderLeadership(members);
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
