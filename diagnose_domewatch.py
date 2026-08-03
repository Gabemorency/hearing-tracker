"""
TEMPORARY diagnostic script — to be deleted after use.
domewatch.us is a client-side rendered SPA (bare requests only get
"Loading..."). Use Playwright to actually render it, find real
navigation to a calendar/schedule view, and inspect what it shows.
"""
import re
from playwright.sync_api import sync_playwright

CANDIDATE_PATHS = ["/", "/calendar", "/schedule", "/session-calendar"]

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        print("=== Rendering https://domewatch.us/ and dumping nav links ===")
        page.goto("https://domewatch.us/", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)
        links = page.eval_on_selector_all(
            "a[href]", "els => els.map(e => ({text: e.innerText.trim(), href: e.href}))"
        )
        cal_links = [l for l in links if l["text"] and (
            "calendar" in l["text"].lower() or "schedule" in l["text"].lower() or "session" in l["text"].lower()
        )]
        print(f"  all links found: {len(links)}")
        print(f"  calendar/schedule/session-labeled links: {cal_links}")
        print(f"  first 30 links (text, href): {[(l['text'], l['href']) for l in links[:30]]}")

        title = page.title()
        body_text = page.eval_on_selector("body", "el => el.innerText")
        print(f"\n  page title: {title!r}")
        print(f"  body text length: {len(body_text)}")
        print(f"  body text[:1500]: {body_text[:1500]!r}")

        for path in CANDIDATE_PATHS[1:]:
            try:
                page.goto(f"https://domewatch.us{path}", wait_until="networkidle", timeout=20000)
                page.wait_for_timeout(1500)
                bt = page.eval_on_selector("body", "el => el.innerText")
                print(f"\n=== https://domewatch.us{path} rendered body text[:800]: {bt[:800]!r}")
            except Exception as e:
                print(f"\n=== https://domewatch.us{path} failed: {e}")

        browser.close()

if __name__ == "__main__":
    main()
