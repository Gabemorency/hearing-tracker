"""
redirect_to_app.py — Phase 3 cutover. Runs as the LAST step of update.yml
and nightly.yml, after every normal scraper/generator step. Overwrites the
static pages visitors load with a redirect to the new Next.js/Vercel app.

Deliberately does not touch anything upstream: every scraper still runs in
full (JSON files + Supabase writes unchanged), since those also feed the
new app's database. This only changes what the old GitHub Pages URLs show
a visitor, not the data pipeline underneath them.

index.html/calendar.html/members.html are already served network-first by
sw.js (not cached), so this reaches existing visitors on their next load
with no service-worker change needed. Individual bios/*.html pages are
stale-while-revalidate there, so a returning visitor to a specific bio
page is one load behind — the same one-page-behind tradeoff sw.js already
makes for bio content in general.

Usage: python3 redirect_to_app.py
"""

import json
import os

APP_URL = "https://web-beta-ten-88.vercel.app"

PAGE_REDIRECTS = {
    "index.html": "/",
    "calendar.html": "/calendar",
    "members.html": "/members",
}


def redirect_html(target_path):
    url = f"{APP_URL}{target_path}"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="0; url={url}">
<link rel="canonical" href="{url}">
<title>Congressional Hearing Tracker</title>
<style>body{{font:16px/1.5 -apple-system,sans-serif;max-width:480px;margin:80px auto;padding:0 20px;color:#333}}</style>
</head>
<body>
<p>This site has moved. <a href="{url}">Continue to the Congressional Hearing Tracker &rarr;</a></p>
<script>location.replace({json.dumps(url)});</script>
</body>
</html>
"""


def build_bio_redirects(members_data):
    """Pure transform: members.json's shape -> {bio_slug: bioguide_id} for
    every member that has both fields."""
    mapping = {}
    for m in members_data.get("senators", []) + members_data.get("reps", []):
        slug = m.get("bio_slug")
        bioguide = m.get("bioguide_id")
        if slug and bioguide:
            mapping[slug] = bioguide
    return mapping


def main():
    for filename, path in PAGE_REDIRECTS.items():
        with open(filename, "w", encoding="utf-8") as f:
            f.write(redirect_html(path))
        print(f"  {filename} -> {APP_URL}{path}")

    if os.path.exists("members.json"):
        with open("members.json", encoding="utf-8") as f:
            members_data = json.load(f)
        bio_redirects = build_bio_redirects(members_data)
        for slug, bioguide in bio_redirects.items():
            with open(f"bios/{slug}.html", "w", encoding="utf-8") as f:
                f.write(redirect_html(f"/members/{bioguide}"))
        print(f"  redirected {len(bio_redirects)} bio page(s) to their member detail page")
    else:
        print("  members.json not found — skipping bio page redirects")


if __name__ == "__main__":
    main()
