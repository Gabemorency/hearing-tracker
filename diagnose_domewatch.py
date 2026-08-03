"""
TEMPORARY diagnostic script — to be deleted after use.
Round 2: DomeWatch's own API has no forward-looking session-calendar
endpoint (confirmed round 1 — all candidates 404). The House Majority
Leader's office and the Senate leadership both publish official
projected floor schedules months in advance; check whether those are
fetchable/parseable server-side.
"""
import requests

TARGETS = [
    ("House Majority Leader calendar", "https://www.majorityleader.gov/calendar"),
    ("House Majority Leader legislative calendar", "https://www.majorityleader.gov/legislative-calendar"),
    ("Clerk of the House legislative calendar", "https://clerk.house.gov/Legislative"),
    ("docs.house.gov calendar", "https://docs.house.gov/Committee/Calendar/index.aspx"),
    ("Senate floor schedule", "https://www.senate.gov/legislative/schedule.htm"),
    ("Senate floor activity", "https://www.senate.gov/legislative/floor_activity.htm"),
]

def main():
    for label, url in TARGETS:
        try:
            r = requests.get(url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (compatible; hearing-tracker-diagnostic/1.0)"
            })
            print(f"\n=== {label} ({url}) -> HTTP {r.status_code}, {len(r.text)} bytes ===")
            if r.status_code == 200:
                # Print a stripped-down snippet: title + first chunk of visible-ish text
                text = r.text
                import re
                title_m = re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I)
                print(f"  title: {title_m.group(1).strip() if title_m else '(none)'}")
                # crude strip of script/style then tags, to eyeball if real calendar content is there
                stripped = re.sub(r"<script.*?</script>|<style.*?</style>", "", text, flags=re.S | re.I)
                stripped = re.sub(r"<[^>]+>", " ", stripped)
                stripped = re.sub(r"\s+", " ", stripped).strip()
                print(f"  body snippet[:1500]: {stripped[:1500]!r}")
            else:
                print(f"  body[:300]: {r.text[:300]!r}")
        except requests.exceptions.RequestException as e:
            print(f"\n=== {label} ({url}) -> request failed: {e} ===")

if __name__ == "__main__":
    main()
