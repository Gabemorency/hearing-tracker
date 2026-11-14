"""
Shared Supabase REST helper for every script that writes to Supabase —
the one-time backfill scripts and the live scraper scripts alike.

Two entry points, because the two callers need different failure modes:
- `supabase_upsert` raises on error. The backfill scripts want this —
  there's no live site depending on them, so a loud failure is correct.
- `safe_supabase_upsert` never raises. The live scraper scripts
  (scrape.py, build_members.py, etc.) run alongside the JSON-file writes
  that the real GitHub Pages site depends on — a Supabase hiccup must
  never block the git commit that keeps that site updating.
"""

import os

import requests


def supabase_env():
    """Returns (base_url, service_key), or (None, None) if either is unset."""
    base_url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not base_url or not service_key:
        return None, None
    return base_url.rstrip("/"), service_key


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


def safe_supabase_upsert(table, rows, on_conflict):
    """Best-effort upsert for the live scraper path: logs and returns
    instead of raising if Supabase env vars are missing or the request
    fails, so callers can add this one line without risking the JSON
    write + git commit that runs alongside it."""
    base_url, service_key = supabase_env()
    if not base_url:
        print(f"  (SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY not set — skipping {table} upsert)")
        return
    try:
        supabase_upsert(base_url, service_key, table, rows, on_conflict)
    except Exception as e:
        print(f"  WARNING: Supabase upsert into {table} failed, continuing anyway: {e}")


def safe_supabase_patch(table, filter_query, patch_body):
    """Best-effort PATCH for the live scraper path: never raises.
    filter_query is a raw PostgREST filter, e.g. "is_current=eq.true"."""
    base_url, service_key = supabase_env()
    if not base_url:
        print(f"  (SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY not set — skipping {table} patch)")
        return
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    try:
        r = requests.patch(f"{base_url}/rest/v1/{table}?{filter_query}", headers=headers, json=patch_body, timeout=30)
        if not r.ok:
            print(f"  WARNING: patch on {table} failed: {r.status_code} {r.text[:300]}")
            return
        print(f"  patched {table} where {filter_query}")
    except Exception as e:
        print(f"  WARNING: patch on {table} failed, continuing anyway: {e}")
