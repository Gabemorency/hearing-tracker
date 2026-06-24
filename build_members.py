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
            # Set chair/RM in leadership map
            tl = title.lower() if title else ""
            if "chair" in tl and "ranking" not in tl:
                if bid not in chair_map:
                    chair_map[bid] = {"label": "Chair", "tier": 4, "committee": cmte_name}
            elif "ranking" in tl:
                if bid not in chair_map:
                    chair_map[bid] = {"label": "Ranking Member", "tier": 5, "committee": cmte_name}

    # ── Caucus membership ──────────────────────────────────────────────────────
    print("📥 Fetching caucus membership lists...")
    caucus_map = {}  # bioguide -> [caucus_key, ...]

    # Caucus definitions: key, display name, scrape URL, fallback bioguide list
    CAUCUSES = [
        ("cbc",        "Black Caucus",                    "https://cbc.house.gov/membership/"),
        ("chc",        "Hispanic Caucus",                 "https://chc.house.gov/members"),
        ("capac",      "Asian Pacific American Caucus",   "https://capac.house.gov/members"),
        ("progressive","Progressive Caucus",              "https://progressives.house.gov/caucus-members"),
        ("newdems",    "New Democrat Coalition",          "https://newdemocratcoalition.house.gov/members"),
        ("rsc",        "Republican Study Committee",      "https://rsc-pfluger.house.gov/members"),
    ]

    # Build a name->bioguide lookup for matching scraped names
    name_to_bio = {}
    for m in legislators:
        name  = m.get("name", {})
        bid   = m.get("id", {}).get("bioguide", "")
        full  = name.get("official_full", "")
        last  = name.get("last", "")
        first = name.get("first", "")
        if bid:
            if full:
                name_to_bio[full.lower()] = bid
            name_to_bio[f"{first} {last}".strip().lower()] = bid
            name_to_bio[last.lower()] = bid  # last name fallback

    def scrape_caucus(url):
        """Fetch a caucus page and extract member names."""
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            if r.status_code != 200:
                return []
            from html.parser import HTMLParser
            class NameParser(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.names = []
                    self.in_name = False
                def handle_starttag(self, tag, attrs):
                    attrs = dict(attrs)
                    cls = attrs.get("class", "")
                    if any(x in cls for x in ["name","member","legislator","title"]):
                        self.in_name = True
                def handle_endtag(self, tag):
                    self.in_name = False
                def handle_data(self, data):
                    if self.in_name:
                        data = data.strip()
                        if len(data) > 3:
                            self.names.append(data)
            # Extract all text and look for "Rep." or "Sen." patterns
            import re as _re
            text = _re.sub(r"<[^>]+>", " ", r.text)
            # Match "Rep. Firstname Lastname" or "Sen. Firstname Lastname"
            matches = _re.findall(
                r"(?:Rep\.|Sen\.|Representative|Senator)\s+([A-Z][a-z]+(?:\s+[A-Z][a-zA-Z\-\']+){1,3})",
                text
            )
            return list(dict.fromkeys(matches))
        except Exception as e:
            print(f"    Caucus scrape error: {e}")
            return []

    def match_names_to_bioguides(names):
        bids = set()
        for name in names:
            nl = name.lower().strip()
            # Try full name first
            if nl in name_to_bio:
                bids.add(name_to_bio[nl])
                continue
            # Try last name
            parts = nl.split()
            if parts:
                last = parts[-1]
                if last in name_to_bio:
                    bids.add(name_to_bio[last])
        return bids

    for key, label, url in CAUCUSES:
        names = scrape_caucus(url)
        bids  = match_names_to_bioguides(names)
        print(f"  {label}: {len(bids)} members matched")
        for bid in bids:
            if bid not in caucus_map:
                caucus_map[bid] = []
            if key not in caucus_map[bid]:
                caucus_map[bid].append(key)

    # Tri-Caucus = CBC + CHC + CAPAC combined
    for bid, keys in caucus_map.items():
        if set(keys) & {"cbc","chc","capac"}:
            if "tricaucus" not in keys:
                caucus_map[bid].append("tricaucus")

    # Freedom Caucus — no official list, use GovTrack known members
    # (static list, updated manually when needed)
    FREEDOM_CAUCUS_BIOGUIDES = [
        "B001306","B001297","B001291","B001302","C001118","C001093",
        "C001108","D000615","D000616","F000475","G000590","G000596",
        "G000578","G000599","H001082","H001071","J000299","L000564",
        "M001177","M001187","M001198","M001205","N000190","O000172",
        "P000609","R000603","R000609","S001212","S001215","T000479",
        "W000806","W000827","W000821",
    ]
    for bid in FREEDOM_CAUCUS_BIOGUIDES:
        if bid not in caucus_map:
            caucus_map[bid] = []
        if "freedom" not in caucus_map[bid]:
            caucus_map[bid].append("freedom")

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

  .card-face .info {{ flex:1;min-width:0;overflow:hidden; }}
  .mname {{ font-size:13px;font-weight:700;color:var(--text);line-height:1.3;margin-bottom:3px; }}
  .mmeta {{ font-family:'IBM Plex Mono',monospace;font-size:10px;color:var(--text-m);margin-bottom:4px; }}
  .mrole {{
    display:inline-block;font-family:'IBM Plex Mono',monospace;
    font-size:9px;letter-spacing:0.05em;padding:2px 6px;
    border-radius:3px;text-transform:uppercase;font-weight:700;line-height:1.4;
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
    <button class="group-btn caucus-btn" onclick="setCaucus('chc',this)">Hispanic Caucus</button>
    <button class="group-btn caucus-btn" onclick="setCaucus('capac',this)">Asian Pacific American Caucus</button>
    <button class="group-btn caucus-btn" onclick="setCaucus('tricaucus',this)">Tri-Caucus</button>
    <button class="group-btn caucus-btn" onclick="setCaucus('progressive',this)">Progressive Caucus</button>
    <button class="group-btn caucus-btn" onclick="setCaucus('newdems',this)">New Democrat Coalition</button>
    <button class="group-btn caucus-btn" onclick="setCaucus('rsc',this)">Republican Study Committee</button>
    <button class="group-btn caucus-btn" onclick="setCaucus('freedom',this)">Freedom Caucus</button>
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
  const label = m.leadership.label;
  const l     = label.toLowerCase();
  let cls = 'role-chair';
  if(l.includes('leader')||l.includes('speaker')||l.includes('pro tempore')) cls='role-leader';
  else if(l.includes('whip')) cls='role-whip';
  else if(l.includes('ranking')) cls='role-rm';
  // Clean short display — never include truncated committee name
  const display = tier<=3 ? label : tier===4 ? 'Chair' : 'Ranking Member';
  return `<span class="mrole ${{cls}}">${{display}}</span>`;
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

function fullRoleDescription(m){{
  if(!m.leadership) return '';
  const label = m.leadership.label;
  const tier  = m.leadership.tier;
  if(tier<=2) return label + (m.chamber==='senate'
    ? ' of the United States Senate'
    : ' of the United States House of Representatives');
  return label.replace(/^RM,\s*/,'Ranking Member, ');
}}

function committeeRows(m){{
  const cmtes = (m.committees||[]);
  if(!cmtes.length) return '<p style="color:var(--text-f);font-style:italic;font-size:14px">No committee data available</p>';

  // Deduplicate by committee name — keep highest-ranked role per committee
  const roleRank = {{'Chair':0,'Chairman':0,'Chairwoman':0,'Chairperson':0,'Ranking Member':1,'Member':2}};
  const seen = {{}};
  cmtes.forEach(c=>{{
    const key = c.committee;
    const rank = roleRank[c.role] ?? 2;
    if(!(key in seen) || rank < seen[key].rank){{
      seen[key] = {{...c, rank}};
    }}
  }});

  // Sort: Chairs first, then Ranking Members, then Members
  const sorted = Object.values(seen).sort((a,b)=> a.rank - b.rank || a.committee.localeCompare(b.committee));

  return sorted.map(c=>{{
    const isChair = c.rank === 0;
    const isRM    = c.rank === 1;
    const badge   = isChair ? `<div><span class="modal-cmte-badge badge-chair">Chair</span></div>`
                  : isRM    ? `<div><span class="modal-cmte-badge badge-rm">Ranking Member</span></div>`
                  : '';
    return `<div class="modal-cmte">${{badge}}${{c.committee}}</div>`;
  }}).join('');
}}

// ── Modal ─────────────────────────────────────────────────────────────────────
function openModal(m){{
  const pc          = m.party_class;
  const partyFull   = pc==='rep'?'Republican':pc==='dem'?'Democrat':'Independent';
  const chamberFull = m.chamber==='senate'
    ? 'United States Senate'
    : 'United States House of Representatives';
  const dist     = m.chamber==='house' && m.district ? `District ${{m.district}} · ` : '';
  const fullRole = fullRoleDescription(m);

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
      ${{dist}}${{m.state}} · ${{partyFull}} <span class="pbadge b-${{pc}}">${{m.party_short}}</span>
    </div>
    ${{fullRole ? `
    <hr class="modal-divider">
    <div class="modal-section-label">Leadership Role</div>
    <div class="modal-section-value">${{fullRole}}</div>` : ''}}
    <hr class="modal-divider">
    <div class="modal-section-label">Committee Assignments</div>
    ${{committeeRows(m)}}
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

// ── Filter ────────────────────────────────────────────────────────────────────
function filtered(){{
  const q = document.getElementById('search').value.toLowerCase().trim();
  // When searching, pull from ALL members regardless of chamber tab
  let pool = q
    ? [...SENATORS, ...REPS]
    : chamber==='senate' ? SENATORS : REPS;

  // Apply caucus filter
  if(caucus !== 'all') {{
    pool = pool.filter(m => (m.caucuses||[]).includes(caucus));
  }}

  // Apply search
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
  render();
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

  // ── Tier 1: Party Leadership (Majority/Minority Leader, Speaker, Whips etc.)
  if(leaders.length){{
    h += `<div class="section-hdr">── Party Leadership</div>`;
    h += `<div class="leader-grid">`;
    const majL = leaders.filter(m=>m.party_class==='rep').sort((a,b)=>a.leadership.tier-b.leadership.tier);
    const minL = leaders.filter(m=>m.party_class!=='rep').sort((a,b)=>a.leadership.tier-b.leadership.tier);
    const mx = Math.max(majL.length, minL.length);
    for(let i=0;i<mx;i++){{
      h += majL[i] ? card(majL[i]) : '<div></div>';
      h += minL[i] ? card(minL[i]) : '<div></div>';
    }}
    h += `</div>`;
  }}

  // ── Tier 2: Committee Chairs (majority) paired with Ranking Members (minority)
  if(chairs.length||rankings.length){{
    h += `<div class="section-hdr">── Committee Chairs & Ranking Members</div>`;
    h += `<div class="leader-grid">`;
    const allChairs   = chairs.sort((a,b)=>  (a.leadership.committee||'').localeCompare(b.leadership.committee||''));
    const allRankings = rankings.sort((a,b)=>(a.leadership.committee||'').localeCompare(b.leadership.committee||''));
    const mx = Math.max(allChairs.length, allRankings.length);
    for(let i=0;i<mx;i++){{
      h += allChairs[i]   ? card(allChairs[i])   : '<div></div>';
      h += allRankings[i] ? card(allRankings[i]) : '<div></div>';
    }}
    h += `</div>`;
  }}

  // ── Tier 3: All other members, two-column party split
  if(rest.length){{
    h += `<div class="section-hdr">── All Members</div>
    <div class="party-cols">
      <div>
        <div class="party-col-hdr col-rep">Republican · ${{maj.length}}</div>
        ${{maj.map(card).join('')}}
      </div>
      <div>
        <div class="party-col-hdr col-dem">Democrat · ${{min.length}}</div>
        ${{min.map(card).join('')}}
        ${{ind.length ? `<div class="party-col-hdr col-ind" style="margin-top:10px">Independent · ${{ind.length}}</div>${{ind.map(card).join('')}}` : ''}}
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
  CURRENT_MEMBERS = []; // reset before each render
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
