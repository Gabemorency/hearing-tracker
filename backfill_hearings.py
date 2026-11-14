"""
One-time backfill: loads every accumulated day in calendar_history.json
into the Supabase `hearings` table.

Idempotent — safe to re-run; each hearing upserts on (date, chamber,
committee, time), matching the unique constraint in
supabase/migrations/0001_init.sql.

Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.

Usage: python3 backfill_hearings.py
"""

import json
import os

import requests


def blank_to_none(s):
    return s if s else None


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


def build_hearing_rows(history):
    """Pure transform: calendar_history.json's shape -> hearings table rows.
    Returns (rows, skipped_count)."""
    rows = []
    skipped = 0
    for date_key, entry in history.items():
        for h in entry.get("hearings", []):
            if not h.get("chamber") or not h.get("committee"):
                skipped += 1
                continue
            rows.append(
                {
                    "date": date_key,
                    "chamber": h.get("chamber"),
                    "committee": h.get("committee"),
                    "chair": blank_to_none(h.get("chair")),
                    "time": blank_to_none(h.get("time")),
                    "building": blank_to_none(h.get("building")),
                    "room": blank_to_none(h.get("room")),
                    "topic": h.get("topic"),
                    "details": blank_to_none(h.get("details")),
                    "witnesses": h.get("witnesses", []),
                    "cancelled": bool(h.get("cancelled", False)),
                    "changes": h.get("changes", []),
                    "link": blank_to_none(h.get("link")),
                }
            )
    return rows, skipped


def main():
    base_url = os.environ["SUPABASE_URL"].rstrip("/")
    service_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    with open("calendar_history.json", encoding="utf-8") as f:
        history = json.load(f)

    print(f"calendar_history.json has {len(history)} days")

    rows, skipped = build_hearing_rows(history)

    if skipped:
        print(f"  skipped {skipped} entries missing chamber/committee")
    print(f"Upserting {len(rows)} hearings...")
    supabase_upsert(base_url, service_key, "hearings", rows, on_conflict="date,chamber,committee,time")

    print("Done.")


if __name__ == "__main__":
    main()
