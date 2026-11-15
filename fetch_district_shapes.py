"""
fetch_district_shapes.py — run on a weekly schedule by district_shapes.yml.

Census publishes "cartographic boundary" files (1:500,000 generalized,
meant for small reference maps — not survey-grade TIGER/Line) for the
current Congress's district lines and for state outlines. This fetches
both, converts each shape to GeoJSON via pyshp's __geo_interface__, and
upserts into district_shapes.

Auto-detects both axes instead of hardcoding either one, so a new Congress
or a new boundary vintage is picked up on the next scheduled run with no
manual change required:
  - the current Congress number, from the same self-computing formula the
    dashboard uses (a new Congress is sworn in at noon ET on January 3 of
    each odd year)
  - the latest published vintage year for that Congress's files, by
    trying descending years until one resolves (confirmed live: Census
    republishes the same district lines under newer vintage folders right
    up until the next Congress/redistricting, e.g. GENZ2025 and GENZ2024
    both serve cb_*_us_cd119_500k.zip, while GENZ2023 only has cd118)

Only ever grows: a new Congress's rows land under a new `congress` number,
so older rows are never deleted — they're historical record, not stale
data that needs cleanup (unlike committee memberships, which really do
need a departed member's row removed).
"""
import io
import sys
import zipfile
from datetime import datetime, timezone

try:
    import requests
    import shapefile  # pyshp
except ImportError:
    print("Installing dependencies...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "pyshp", "--break-system-packages", "-q"])
    import requests
    import shapefile

from supabase_client import safe_supabase_upsert

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; hearing-tracker-bot/1.0)"}
BASE = "https://www2.census.gov/geo/tiger"

# Census FIPS state/territory code -> USPS postal abbreviation. Static —
# this table hasn't changed since Hawaii statehood in 1959. Used as a
# fallback when a shapefile doesn't carry a STUSPS field directly (the
# congressional-district cartographic files typically don't; the
# state-outline ones typically do).
FIPS_TO_USPS = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY",
    "60": "AS", "66": "GU", "69": "MP", "72": "PR", "78": "VI",
}


def current_congress(today=None):
    """Same formula as the Next.js dashboard's currentCongress()."""
    d = today or datetime.now(timezone.utc).date()
    effective_year = d.year - 1 if (d.month == 1 and d.day < 3) else d.year
    return (effective_year - 1789) // 2 + 1


def normalize_district(value):
    """'00' (at-large) -> '0', '01' -> '1', '12' -> '12' — matches the
    str(int(...)) convention member_terms.district already stores."""
    return str(int(value))


def state_abbrev(record):
    """Prefer a direct STUSPS field; fall back to the FIPS crosswalk."""
    if record.get("STUSPS"):
        return record["STUSPS"]
    return FIPS_TO_USPS.get(record.get("STATEFP"))


def find_latest_zip(filename_template, years):
    """Try descending vintage years; return (year, zip_bytes) for the
    first that exists, or (None, None) if none do."""
    for year in years:
        url = f"{BASE}/GENZ{year}/shp/{filename_template.format(year=year)}"
        r = requests.get(url, headers=HEADERS, timeout=60)
        if r.ok and r.content[:2] == b"PK":  # a real zip, not an error page
            return year, r.content
    return None, None


def shapes_from_zip(zip_bytes):
    """Read every shape + record from the shapefile bundled in a zip."""
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    names = zf.namelist()
    base = next(n[:-4] for n in names if n.endswith(".shp"))
    reader = shapefile.Reader(
        shp=io.BytesIO(zf.read(base + ".shp")),
        dbf=io.BytesIO(zf.read(base + ".dbf")),
        shx=io.BytesIO(zf.read(base + ".shx")),
    )
    return list(reader.shapeRecords())


def build_district_rows(shape_records, congress, cd_field):
    rows = []
    for sr in shape_records:
        rec = sr.record.as_dict()
        state = state_abbrev(rec)
        if not state or cd_field not in rec:
            continue
        rows.append({
            "congress": congress,
            "state": state,
            "district": normalize_district(rec[cd_field]),
            "geometry": sr.shape.__geo_interface__,
        })
    return rows


def build_state_rows(shape_records, congress):
    rows = []
    for sr in shape_records:
        rec = sr.record.as_dict()
        state = state_abbrev(rec)
        if not state:
            continue
        rows.append({
            "congress": congress,
            "state": state,
            "district": "",  # '' = whole-state outline, used for Senators
            "geometry": sr.shape.__geo_interface__,
        })
    return rows


def main():
    congress = current_congress()
    current_year = datetime.now(timezone.utc).year
    years = range(current_year, current_year - 4, -1)

    print(f"Fetching district boundaries for the {congress}th Congress...")
    cd_field = f"CD{congress}FP"
    year, cd_zip = find_latest_zip(f"cb_{{year}}_us_cd{congress}_500k.zip", years)
    if not cd_zip:
        print(f"  No district cartographic file found for Congress {congress} across {list(years)} — skipping this run")
        return
    print(f"  Using vintage {year}")
    district_rows = build_district_rows(shapes_from_zip(cd_zip), congress, cd_field)
    print(f"  {len(district_rows)} district shapes")

    print("Fetching state boundaries...")
    year, state_zip = find_latest_zip("cb_{year}_us_state_500k.zip", years)
    state_rows = []
    if state_zip:
        print(f"  Using vintage {year}")
        state_rows = build_state_rows(shapes_from_zip(state_zip), congress)
        print(f"  {len(state_rows)} state shapes")
    else:
        print("  No state cartographic file found — skipping state outlines")

    all_rows = district_rows + state_rows
    print(f"Upserting {len(all_rows)} shapes to Supabase...")
    # Small chunks — these rows carry a full GeoJSON geometry each, and a
    # single request bundling hundreds of them can time out Supabase even
    # though the same rows split into small batches write fine (confirmed
    # live: one 497-row request timed out at 60s).
    safe_supabase_upsert("district_shapes", all_rows, on_conflict="congress,state,district", chunk_size=50)


if __name__ == "__main__":
    main()
