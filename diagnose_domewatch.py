"""
TEMPORARY diagnostic script — to be deleted after use.
Round 3: majorityleader.gov/calendar's own nav mentions a "2026 Calendar"
link but the events widget itself is JS-rendered (empty via bare
requests). Extract the real href for that nav link, and any other
calendar-like links on the page, to find the actual projected-calendar
URL. Also retry clerk.house.gov with a browser-like User-Agent (got 403
with a generic UA last round).
"""
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def show_links(label, url, keyword):
    try:
        r = requests.get(url, timeout=15, headers=HEADERS)
        print(f"\n=== {label} ({url}) -> HTTP {r.status_code}, {len(r.text)} bytes ===")
        if r.status_code == 200:
            hrefs = re.findall(r'href="([^"]+)"[^>]*>([^<]{0,60})', r.text)
            matches = [(h, t.strip()) for h, t in hrefs if keyword.lower() in (h + t).lower()]
            print(f"  links matching {keyword!r}: {matches[:20]}")
        else:
            print(f"  body[:300]: {r.text[:300]!r}")
    except requests.exceptions.RequestException as e:
        print(f"\n=== {label} ({url}) -> request failed: {e} ===")

def main():
    show_links("Majority Leader calendar page", "https://www.majorityleader.gov/calendar", "calendar")

    # Retry clerk.house.gov with a browser UA
    for label, url in [
        ("Clerk of the House home", "https://clerk.house.gov/"),
        ("Clerk of the House Legislative Activities", "https://clerk.house.gov/Legislative"),
    ]:
        try:
            r = requests.get(url, timeout=15, headers=HEADERS)
            print(f"\n=== {label} ({url}) -> HTTP {r.status_code}, {len(r.text)} bytes ===")
            if r.status_code == 200:
                title_m = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.S | re.I)
                print(f"  title: {title_m.group(1).strip() if title_m else '(none)'}")
                hrefs = re.findall(r'href="([^"]+)"[^>]*>([^<]{0,60})', r.text)
                matches = [(h, t.strip()) for h, t in hrefs if "calendar" in (h + t).lower() or "session" in (h+t).lower()]
                print(f"  calendar/session links: {matches[:20]}")
        except requests.exceptions.RequestException as e:
            print(f"\n=== {label} ({url}) -> request failed: {e} ===")

if __name__ == "__main__":
    main()
