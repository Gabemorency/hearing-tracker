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


def supabase_upsert(base_url, service_key, table, rows, on_conflict, chunk_size=500):
    """chunk_size defaults to 500, fine for the small rows most callers
    write. Callers upserting rows with a large payload per row (e.g. a
    GeoJSON geometry column) should pass a much smaller chunk_size —
    Supabase can time out processing one request that bundles hundreds of
    large rows, even though the same rows split into smaller batches
    write fine (confirmed against district_shapes: a single 497-row
    request timed out at 60s; 50-row batches did not)."""
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
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        r = requests.post(url, headers=headers, json=chunk, timeout=60)
        if not r.ok:
            print(f"  ERROR upserting into {table}: {r.status_code} {r.text[:500]}")
            r.raise_for_status()
    print(f"  upserted {len(rows)} rows into {table}")


def safe_supabase_upsert(table, rows, on_conflict, chunk_size=500):
    """Best-effort upsert for the live scraper path: logs and returns
    instead of raising if Supabase env vars are missing or the request
    fails, so callers can add this one line without risking the JSON
    write + git commit that runs alongside it."""
    base_url, service_key = supabase_env()
    if not base_url:
        print(f"  (SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY not set — skipping {table} upsert)")
        return
    try:
        supabase_upsert(base_url, service_key, table, rows, on_conflict, chunk_size=chunk_size)
    except Exception as e:
        print(f"  WARNING: Supabase upsert into {table} failed, continuing anyway: {e}")


def safe_supabase_select(table, params, default=None):
    """Best-effort GET for the live scraper path: never raises. `params` is
    a dict of raw PostgREST query params (e.g. {"select": "roll_number",
    "chamber": "eq.House", "order": "roll_number.desc", "limit": "1"}).
    Returns `default` (an empty list, unless overridden) on any failure —
    callers doing incremental fetches should treat that the same as "no
    rows yet" rather than crashing the run."""
    base_url, service_key = supabase_env()
    if not base_url:
        print(f"  (SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY not set — skipping {table} select)")
        return default if default is not None else []
    headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
    try:
        r = requests.get(f"{base_url}/rest/v1/{table}", headers=headers, params=params, timeout=30)
        if not r.ok:
            print(f"  WARNING: select on {table} failed: {r.status_code} {r.text[:300]}")
            return default if default is not None else []
        return r.json()
    except Exception as e:
        print(f"  WARNING: select on {table} failed, continuing anyway: {e}")
        return default if default is not None else []


def safe_supabase_delete(table, filter_query):
    """Best-effort DELETE for the live scraper path: never raises.
    filter_query is a raw PostgREST filter, e.g. "id=gt.0" to match every
    row — used for tables resynced as a full snapshot each run (no stable
    boolean to flip like members.is_current), so a member dropped from a
    committee actually disappears instead of lingering forever."""
    base_url, service_key = supabase_env()
    if not base_url:
        print(f"  (SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY not set — skipping {table} delete)")
        return
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Prefer": "return=minimal",
    }
    try:
        r = requests.delete(f"{base_url}/rest/v1/{table}?{filter_query}", headers=headers, timeout=30)
        if not r.ok:
            print(f"  WARNING: delete on {table} failed: {r.status_code} {r.text[:300]}")
            return
        print(f"  deleted rows from {table} where {filter_query}")
    except Exception as e:
        print(f"  WARNING: delete on {table} failed, continuing anyway: {e}")


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
