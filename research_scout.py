"""Throwaway research script — NOT part of the app.

Runs once via a manual GitHub Actions dispatch (real network access, unlike
the sandbox this was written in) to confirm real data shapes for two
roadmap features before writing their permanent scrapers:

  1. Votes — House/Senate roll-call XML: field names, per-member
     identifier format, and how to discover which roll numbers exist.
  2. Member district maps — Census cartographic boundary files: URL
     pattern, format, and whether a browsable directory listing exists
     so the real pipeline can auto-detect the current vintage/year
     instead of a hardcoded value that would need manual bumping after
     every redistricting.

Writes nothing to Supabase or the repo. Prints everything to the job log.
Deleted after use — this file and its workflow should not be merged.
"""
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; hearing-tracker-research/1.0)"}


def check(url, label, show_bytes=2000):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        print(f"[{r.status_code}] {label}: {url} ({len(r.content)} bytes)")
        if r.ok and show_bytes:
            snippet = r.text[:show_bytes] if r.encoding or "xml" in r.headers.get("content-type", "") or "html" in r.headers.get("content-type", "") else f"<binary, {len(r.content)} bytes>"
            print("  ---")
            print("  " + snippet.replace("\n", "\n  "))
            print("  ---")
        return r
    except Exception as e:
        print(f"[ERROR] {label}: {url} -> {e}")
        return None


print("\n========== VOTES: House roll call ==========")
check("https://clerk.house.gov/evs/2026/roll001.xml", "House roll 1, 2026")
check("https://clerk.house.gov/evs/2026/roll500.xml", "House roll 500, 2026 (likely exists later in year)")
check("https://clerk.house.gov/Votes", "House Votes index page")
check("https://clerk.house.gov/evs/2026/index.asp", "House 2026 index")

print("\n========== VOTES: Senate roll call ==========")
for congress, session in [(119, 2), (119, 1)]:
    check(
        f"https://www.senate.gov/legislative/LIS/roll_call_lists/vote_menu_{congress}_{session}.xml",
        f"Senate vote menu {congress}-{session}",
    )
check(
    "https://www.senate.gov/legislative/LIS/roll_call_votes/vote1192/vote_119_2_00001.xml",
    "Senate vote detail guess (119-2, roll 1)",
)
check(
    "https://www.senate.gov/legislative/LIS/roll_call_votes/vote1191/vote_119_1_00001.xml",
    "Senate vote detail guess (119-1, roll 1)",
)

print("\n========== MAPS: Census cartographic boundary files ==========")
for year in [2025, 2024, 2023, 2022]:
    for cd in [119, 118]:
        check(
            f"https://www2.census.gov/geo/tiger/GENZ{year}/shp/cb_{year}_us_cd{cd}_500k.zip",
            f"Census CD cartographic, vintage {year}, cd{cd}",
            show_bytes=0,
        )

print("\n========== MAPS: directory listing (for auto-detecting latest vintage) ==========")
for year in [2025, 2024, 2023]:
    check(f"https://www2.census.gov/geo/tiger/GENZ{year}/shp/", f"GENZ{year} shp directory listing")
check("https://www2.census.gov/geo/tiger/GENZ2023/", "GENZ2023 top-level directory listing")

print("\n========== MAPS: GeoJSON variant (smaller/simpler than shapefile)? ==========")
check("https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_cd118_500k.kml", "Census CD KML variant")

print("\nDone.")
