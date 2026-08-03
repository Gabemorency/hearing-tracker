"""
TEMPORARY diagnostic script — to be deleted after use.
So far we've only probed DomeWatch's data API (data.domewatch.us/v1), which
has no calendar endpoint. The user is looking at DomeWatch's actual website
(the one showing a projected multi-month session calendar) — check whether
that site is reachable and whether its calendar page is scrapeable.
"""
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
}

CANDIDATES = [
    "https://domewatch.us",
    "https://www.domewatch.us",
    "https://domewatch.us/calendar",
    "https://www.domewatch.us/calendar",
    "https://domewatch.us/schedule",
    "https://www.domewatch.us/schedule",
]

def main():
    for url in CANDIDATES:
        try:
            r = requests.get(url, timeout=15, headers=HEADERS, allow_redirects=True)
            print(f"\n=== {url} -> HTTP {r.status_code} (final: {r.url}), {len(r.text)} bytes ===")
            if r.status_code == 200:
                title_m = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.S | re.I)
                print(f"  title: {title_m.group(1).strip() if title_m else '(none)'}")
                hrefs = re.findall(r'href="([^"]+)"[^>]*>([^<]{0,60})', r.text)
                cal_links = [(h, t.strip()) for h, t in hrefs if "calendar" in (h + t).lower() or "session" in (h + t).lower() or "schedule" in (h+t).lower()]
                print(f"  calendar/session/schedule links: {cal_links[:20]}")
                stripped = re.sub(r"<script.*?</script>|<style.*?</style>", "", r.text, flags=re.S | re.I)
                stripped_text = re.sub(r"<[^>]+>", " ", stripped)
                stripped_text = re.sub(r"\s+", " ", stripped_text).strip()
                print(f"  visible text length: {len(stripped_text)} chars")
                print(f"  snippet[:800]: {stripped_text[:800]!r}")
        except requests.exceptions.RequestException as e:
            print(f"\n=== {url} -> request failed: {e} ===")

if __name__ == "__main__":
    main()
