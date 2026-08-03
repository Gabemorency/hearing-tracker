"""
Temporary diagnostic: does a Senate committee's public hearings LISTING page
(e.g. help.senate.gov/hearings) expose a link to each individual hearing's
own page, distinct from the generic listing URL? A user wants the "watch"
link to point at the specific hearing, not the committee's general hearings
page. scrape.py already visits these pages for witnesses/chair extraction —
this checks whether a per-hearing href is even available to grab, and
whether the markup is consistent enough across committees to do reliably.

Not part of the regular pipeline — delete after use.
"""
from playwright.sync_api import sync_playwright

URLS = [
    ("Health HELP", "https://www.help.senate.gov/hearings"),
    ("Indian Affairs", "https://www.indian.senate.gov/hearings"),
    ("Aging", "https://www.aging.senate.gov/hearings"),
    ("Homeland Security", "https://www.hsgac.senate.gov/hearings"),
    ("Energy & Natural Resources", "https://www.energy.senate.gov/hearings"),
]

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    for name, url in URLS:
        print(f"=== {name}: {url} ===")
        try:
            page.goto(url, wait_until="networkidle", timeout=25000)
            page.wait_for_timeout(1000)

            # Look for links whose visible text looks like a hearing title
            # (heuristic: any <a> inside something that looks like a listing
            # item, or any <a> whose href differs from the page's own URL).
            links = page.eval_on_selector_all(
                "a[href]",
                """els => els.map(e => ({
                    text: e.innerText.trim().slice(0, 80),
                    href: e.href,
                    cls: e.className,
                    parentCls: e.parentElement ? e.parentElement.className : ''
                })).filter(l => l.text.length > 15)"""
            )
            print(f"  {len(links)} candidate content links found")
            for l in links[:8]:
                print("   -", l)
        except Exception as e:
            print("  FAILED:", repr(e))
        print()
    browser.close()
