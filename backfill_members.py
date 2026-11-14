"""
One-time(ish) backfill: loads every member of Congress — current and
historical, back to 1789 — into Supabase.

Designed to be idempotent/safe to re-run: every write is an upsert keyed
on a real uniqueness constraint (bioguide_id for members; member_id +
chamber + state + district + start_date for member_terms), so running
this again after an election, a resignation, or any other roster change
just updates/adds rows rather than duplicating them. That idempotency —
not any election-specific logic — is what keeps this current over time.

Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (service_role bypasses
RLS, which is required here — these are the only tables public content
is read-only for, writes are service_role-only by design).

Usage: python3 backfill_members.py
"""

import os

import requests
import yaml

BASE = "https://raw.githubusercontent.com/unitedstates/congress-legislators/main"
HEADERS_FETCH = {"User-Agent": "Mozilla/5.0 (compatible; hearing-tracker-backfill/1.0)"}
TERRITORIES = {"DC", "PR", "VI", "GU", "AS", "MP"}


def fetch_yaml(url):
    r = requests.get(url, headers=HEADERS_FETCH, timeout=60)
    r.raise_for_status()
    return yaml.safe_load(r.text)


def load_json(path):
    import json

    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def supabase_upsert(base_url, service_key, table, rows, on_conflict):
    if not rows:
        print(f"  (nothing to upsert into {table})")
        return
    url = f"{base_url}/rest/v1/{table}?on_conflict={on_conflict}"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    chunk_size = 500
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        r = requests.post(url, headers=headers, json=chunk, timeout=60)
        if not r.ok:
            print(f"  ERROR upserting into {table}: {r.status_code} {r.text[:500]}")
            r.raise_for_status()
    print(f"  upserted {len(rows)} rows into {table}")


def build_member_row(person, is_current, bios):
    bioguide = person.get("id", {}).get("bioguide")
    if not bioguide:
        return None
    name = person.get("name", {})
    full_name = name.get("official_full") or f"{name.get('first', '')} {name.get('last', '')}".strip()
    terms = person.get("terms", [])
    delegate = any(t.get("type") == "rep" and t.get("state") in TERRITORIES for t in terms)
    return {
        "bioguide_id": bioguide,
        "first_name": name.get("first"),
        "last_name": name.get("last"),
        "full_name": full_name,
        "nickname": name.get("nickname"),
        "delegate": delegate,
        "is_current": is_current,
        "bio": bios.get(bioguide),
    }


def build_term_rows(person):
    bioguide = person.get("id", {}).get("bioguide")
    if not bioguide:
        return []
    rows = []
    for t in person.get("terms", []):
        ttype = t.get("type")
        chamber = "House" if ttype == "rep" else "Senate" if ttype == "sen" else None
        if chamber is None or not t.get("start") or not t.get("end") or not t.get("state"):
            continue
        rows.append(
            {
                "member_id": bioguide,
                "chamber": chamber,
                "state": t["state"],
                "district": str(t["district"]) if chamber == "House" and t.get("district") is not None else None,
                "party": t.get("party"),
                "start_date": t["start"],
                "end_date": t["end"],
            }
        )
    return rows


def main():
    base_url = os.environ["SUPABASE_URL"].rstrip("/")
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    bios = load_json("bios_hardcoded.json")

    print("Fetching legislators-current.yaml...")
    current = fetch_yaml(f"{BASE}/legislators-current.yaml")
    print(f"  {len(current)} current members")

    print("Fetching legislators-historical.yaml...")
    historical = fetch_yaml(f"{BASE}/legislators-historical.yaml")
    print(f"  {len(historical)} historical members")

    members = []
    terms = []
    for person in current:
        row = build_member_row(person, is_current=True, bios=bios)
        if row:
            members.append(row)
            terms.extend(build_term_rows(person))
    for person in historical:
        row = build_member_row(person, is_current=False, bios=bios)
        if row:
            members.append(row)
            terms.extend(build_term_rows(person))

    print(f"Upserting {len(members)} members...")
    supabase_upsert(base_url, service_key, "members", members, on_conflict="bioguide_id")

    print(f"Upserting {len(terms)} member_terms...")
    supabase_upsert(
        base_url,
        service_key,
        "member_terms",
        terms,
        on_conflict="member_id,chamber,state,district,start_date",
    )

    leadership_src = load_json("institutional_leadership.json")
    leadership_rows = [
        {"bioguide_id": bioguide, "label": info["label"], "full_title": info["full_title"], "tier": info["tier"]}
        for bioguide, info in leadership_src.items()
    ]
    print(f"Upserting {len(leadership_rows)} institutional_leadership rows...")
    supabase_upsert(
        base_url, service_key, "institutional_leadership", leadership_rows, on_conflict="bioguide_id"
    )

    vacant_src = load_json("vacant_seats.json")
    vacant_rows = [
        {
            "state": v["state"],
            "district": str(v["district"]) if v.get("district") is not None else None,
            "label": v["label"],
            "reason": v.get("reason"),
            "election": v.get("election"),
            "party": v.get("party"),
        }
        for v in vacant_src
    ]
    print(f"Upserting {len(vacant_rows)} vacant_seats rows...")
    supabase_upsert(base_url, service_key, "vacant_seats", vacant_rows, on_conflict="state,district")

    print("Done.")


if __name__ == "__main__":
    main()
