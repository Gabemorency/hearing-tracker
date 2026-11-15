"""
fetch_votes.py — run by votes.yml, a few times a day while Congress is
likely in session.

Scrapes roll-call votes directly from each chamber's own public feed —
no third-party aggregator:
  - House: Clerk's Electronic Voting System, one XML file per roll call
    at https://clerk.house.gov/evs/{year}/roll{n:03d}.xml. Members are
    identified there by a `name-id` attribute that IS the bioguide ID
    used everywhere else in this app — no crosswalk needed.
  - Senate: the LIS (Legislative Information System), one XML file per
    roll call at .../roll_call_votes/vote{congress}{session}/
    vote_{congress}_{session}_{n:05d}.xml. Members are identified there
    by an LIS member id (e.g. "S307"), NOT a bioguide id, so this also
    fetches legislators-current.yaml (the same source build_members.py
    already uses) to build a lis -> bioguide crosswalk.

Incremental by design: for each chamber, asks Supabase for the highest
roll_number already stored for the current congress/session, then
fetches forward from there one roll call at a time until a fetch 404s
(meaning that roll call doesn't exist yet) — no index/listing page to
parse, and nothing to track in a separate file. `max_fetch` caps how many
new roll calls one run will pull, so a cold start (or a day with an
unusual number of votes) can't turn into an unbounded run; it'll just
pick up where it left off next time.

Only current-year (House) / current-congress-session (Senate) votes are
covered — a senator or rep who left mid-session and crosses the exact
boundary where this script's own crosswalk snapshot was taken is a known,
accepted gap, not something this handles specially.
"""
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

try:
    import requests
    import yaml
except ImportError:
    print("Installing dependencies...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "pyyaml", "--break-system-packages", "-q"])
    import requests
    import yaml

from supabase_client import safe_supabase_upsert, safe_supabase_select

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; hearing-tracker-bot/1.0)"}
LEGISLATORS_YAML = "https://raw.githubusercontent.com/unitedstates/congress-legislators/main/legislators-current.yaml"

MAX_FETCH_PER_RUN = 150  # per chamber, per run — see module docstring

# House `legis-num` values look like "H R 1234" or "H J RES 45" — this
# maps the space-joined, uppercased prefix to its conventional short form.
# Unrecognized prefixes pass through unchanged rather than being dropped;
# this field is informational display text, not something else keys off it.
LEGIS_PREFIXES = {
    "H R": "H.R.", "S": "S.", "H RES": "H.Res.", "S RES": "S.Res.",
    "H J RES": "H.J.Res.", "S J RES": "S.J.Res.",
    "H CON RES": "H.Con.Res.", "S CON RES": "S.Con.Res.",
}

POSITION_MAP = {
    "YEA": "Yea", "AYE": "Yea",
    "NAY": "Nay", "NO": "Nay",
    "PRESENT": "Present",
    "NOT VOTING": "Not Voting", "NV": "Not Voting",
}


def current_congress_and_session(today=None):
    """Same congress formula the dashboard/district-shapes scraper use,
    extended with which session (1st/2nd calendar year of that congress)
    today falls in."""
    d = today or datetime.now(timezone.utc).date()
    effective_year = d.year - 1 if (d.month == 1 and d.day < 3) else d.year
    congress = (effective_year - 1789) // 2 + 1
    session = 1 if (effective_year - 1789) % 2 == 0 else 2
    return congress, session


def congress_start_year(congress):
    return 1789 + (congress - 1) * 2


def findtext_any(elem, tags, default=None):
    """Try several possible tag spellings for the same field — government
    XML feeds aren't always consistent release to release — and return
    the first non-empty match."""
    if elem is None:
        return default
    for tag in tags:
        node = elem.find(tag)
        if node is not None and node.text and node.text.strip():
            return node.text.strip()
    return default


def normalize_position(raw):
    if not raw:
        return None
    return POSITION_MAP.get(raw.strip().upper())


def normalize_bill_number(raw):
    if not raw:
        return None
    raw = raw.strip()
    parts = raw.split()
    if len(parts) >= 2 and parts[-1].isdigit():
        prefix = " ".join(parts[:-1]).upper()
        abbrev = LEGIS_PREFIXES.get(prefix)
        if abbrev:
            return f"{abbrev} {parts[-1]}"
    return raw


def highest_known_roll(chamber, congress, session):
    rows = safe_supabase_select("votes", {
        "select": "roll_number",
        "chamber": f"eq.{chamber}",
        "congress": f"eq.{congress}",
        "session": f"eq.{session}",
        "order": "roll_number.desc",
        "limit": "1",
    })
    return rows[0]["roll_number"] if rows else 0


def fetch_lis_crosswalk():
    """lis member id (e.g. "S307") -> bioguide id, from the same source
    build_members.py already treats as ground truth for member identity."""
    r = requests.get(LEGISLATORS_YAML, headers=HEADERS, timeout=30)
    r.raise_for_status()
    legislators = yaml.safe_load(r.text)
    crosswalk = {}
    for person in legislators:
        ids = person.get("id", {})
        lis_id = ids.get("lis")
        bioguide_id = ids.get("bioguide")
        if lis_id and bioguide_id:
            crosswalk[lis_id] = bioguide_id
    return crosswalk


def parse_house_vote(content, congress, session):
    root = ET.fromstring(content)
    metadata = root.find("vote-metadata")
    if metadata is None:
        return None, []

    roll_raw = findtext_any(metadata, ["rollcall-num", "vote-num"])
    if not roll_raw:
        return None, []

    date_raw = findtext_any(metadata, ["action-date"])
    date_iso = None
    if date_raw:
        for fmt in ("%d-%b-%Y", "%B %d, %Y", "%Y-%m-%d"):
            try:
                date_iso = datetime.strptime(date_raw, fmt).date().isoformat()
                break
            except ValueError:
                continue
    if not date_iso:
        return None, []

    totals = metadata.find("vote-totals")
    by_vote = totals.find("totals-by-vote") if totals is not None else None

    vote_row = {
        "congress": congress,
        "session": session,
        "chamber": "House",
        "roll_number": int(roll_raw),
        "date": date_iso,
        "question": findtext_any(metadata, ["vote-question", "vote-question-text"]) or "Roll Call Vote",
        "description": findtext_any(metadata, ["vote-desc"]),
        "bill_number": normalize_bill_number(findtext_any(metadata, ["legis-num"])),
        "result": findtext_any(metadata, ["vote-result"]) or "Unknown",
        "yea_count": int(findtext_any(by_vote, ["yea-total"]) or 0),
        "nay_count": int(findtext_any(by_vote, ["nay-total"]) or 0),
        "present_count": int(findtext_any(by_vote, ["present-total"]) or 0),
        "not_voting_count": int(findtext_any(by_vote, ["not-voting-total"]) or 0),
    }

    member_rows = []
    vote_data = root.find("vote-data")
    for rv in (vote_data.findall("recorded-vote") if vote_data is not None else []):
        legislator = rv.find("legislator")
        bioguide_id = legislator.get("name-id") if legislator is not None else None
        position = normalize_position(findtext_any(rv, ["vote"]))
        if bioguide_id and position:
            member_rows.append({
                "congress": congress, "session": session, "chamber": "House",
                "roll_number": vote_row["roll_number"],
                "member_id": bioguide_id, "position": position,
            })

    return vote_row, member_rows


def parse_senate_vote(content, congress, session, lis_crosswalk):
    root = ET.fromstring(content)

    roll_raw = findtext_any(root, ["vote_number"])
    if not roll_raw:
        return None, []

    date_raw = findtext_any(root, ["vote_date"])
    date_iso = None
    if date_raw:
        for fmt in ("%B %d, %Y, %I:%M %p", "%B %d, %Y"):
            try:
                date_iso = datetime.strptime(date_raw, fmt).date().isoformat()
                break
            except ValueError:
                continue
    if not date_iso:
        return None, []

    count = root.find("count")

    vote_row = {
        "congress": congress,
        "session": session,
        "chamber": "Senate",
        "roll_number": int(roll_raw),
        "date": date_iso,
        "question": findtext_any(root, ["vote_question_text", "question"]) or "Roll Call Vote",
        "description": findtext_any(root, ["vote_document_text"]),
        "bill_number": findtext_any(root, ["vote_document_text"]),
        "result": findtext_any(root, ["vote_result_text", "vote_result"]) or "Unknown",
        "yea_count": int(findtext_any(count, ["yeas"]) or 0),
        "nay_count": int(findtext_any(count, ["nays"]) or 0),
        "present_count": int(findtext_any(count, ["present"]) or 0),
        "not_voting_count": int(findtext_any(count, ["absent", "not_voting"]) or 0),
    }

    member_rows = []
    unmapped = 0
    members_el = root.find("members")
    for m in (members_el.findall("member") if members_el is not None else []):
        lis_id = findtext_any(m, ["lis_member_id"])
        position = normalize_position(findtext_any(m, ["vote_cast"]))
        bioguide_id = lis_crosswalk.get(lis_id) if lis_id else None
        if bioguide_id and position:
            member_rows.append({
                "congress": congress, "session": session, "chamber": "Senate",
                "roll_number": vote_row["roll_number"],
                "member_id": bioguide_id, "position": position,
            })
        elif lis_id and position:
            unmapped += 1
    if unmapped:
        print(f"    (roll {vote_row['roll_number']}: {unmapped} senator(s) with no bioguide match)")

    return vote_row, member_rows


def fetch_house_votes(congress, session, year):
    start = highest_known_roll("House", congress, session) + 1
    vote_rows, member_rows = [], []
    for roll in range(start, start + MAX_FETCH_PER_RUN):
        url = f"https://clerk.house.gov/evs/{year}/roll{roll:03d}.xml"
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 404:
            break
        if not r.ok:
            print(f"  WARNING: House roll {roll} fetch failed: {r.status_code} — stopping this run")
            break
        try:
            vote_row, members = parse_house_vote(r.content, congress, session)
        except ET.ParseError as e:
            print(f"  WARNING: House roll {roll} didn't parse as expected XML ({e}) — skipping")
            continue
        if vote_row:
            vote_rows.append(vote_row)
            member_rows.extend(members)
    return vote_rows, member_rows


def fetch_senate_votes(congress, session, lis_crosswalk):
    start = highest_known_roll("Senate", congress, session) + 1
    vote_rows, member_rows = [], []
    for roll in range(start, start + MAX_FETCH_PER_RUN):
        url = (
            f"https://www.senate.gov/legislative/LIS/roll_call_votes/"
            f"vote{congress}{session}/vote_{congress}_{session}_{roll:05d}.xml"
        )
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 404:
            break
        if not r.ok:
            print(f"  WARNING: Senate roll {roll} fetch failed: {r.status_code} — stopping this run")
            break
        try:
            vote_row, members = parse_senate_vote(r.content, congress, session, lis_crosswalk)
        except ET.ParseError as e:
            print(f"  WARNING: Senate roll {roll} didn't parse as expected XML ({e}) — skipping")
            continue
        if vote_row:
            vote_rows.append(vote_row)
            member_rows.extend(members)
    return vote_rows, member_rows


def main():
    congress, session = current_congress_and_session()
    year = congress_start_year(congress) + session - 1
    print(f"Congress {congress}, session {session} (House calendar year {year})")

    print("Fetching House roll call votes...")
    house_votes, house_members = fetch_house_votes(congress, session, year)
    print(f"  {len(house_votes)} new House votes, {len(house_members)} member positions")

    print("Fetching lis_member_id -> bioguide crosswalk...")
    lis_crosswalk = fetch_lis_crosswalk()
    print(f"  {len(lis_crosswalk)} senators mapped")

    print("Fetching Senate roll call votes...")
    senate_votes, senate_members = fetch_senate_votes(congress, session, lis_crosswalk)
    print(f"  {len(senate_votes)} new Senate votes, {len(senate_members)} member positions")

    all_votes = house_votes + senate_votes
    all_member_votes = house_members + senate_members

    print(f"Upserting {len(all_votes)} votes to Supabase...")
    safe_supabase_upsert("votes", all_votes, on_conflict="chamber,congress,session,roll_number")

    print(f"Upserting {len(all_member_votes)} member vote positions to Supabase...")
    safe_supabase_upsert(
        "member_votes", all_member_votes,
        on_conflict="chamber,congress,session,roll_number,member_id",
        chunk_size=200,
    )


if __name__ == "__main__":
    main()
