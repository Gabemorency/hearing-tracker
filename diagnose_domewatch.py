"""
Temporary diagnostic round 5: plain requests.get() against docs.house.gov
ByEvent.aspx returns an "Error Encountered" page — this is an old ASP.NET
WebForms site (__VIEWSTATE, postback links) that likely needs a real browser
session/cookies. scrape.py already uses Playwright successfully against
other house.gov pages, so try that here instead of bare requests.

Not part of the regular pipeline — delete after use.
"""
import re
from playwright.sync_api import sync_playwright

URLS = [
    "http://docs.house.gov/Committee/Calendar/ByEvent.aspx?EventId=119443",
    "http://docs.house.gov/Committee/Calendar/ByEvent.aspx?EventId=118854",
]

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    for url in URLS:
        print(f"=== {url} ===")
        try:
            page.goto(url, wait_until="networkidle", timeout=20000)
            title = page.title()
            print("page title:", title)
            html = page.content()
            print("html length:", len(html))

            h1 = re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
            print("h1 tags:", h1)
            h2 = re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.S | re.I)
            print("h2 tags:", h2[:5])

            body_text = page.inner_text("body")
            print("visible body text, first 2000 chars:")
            print(body_text[:2000])
        except Exception as e:
            print("FAILED:", repr(e))
        print()
    browser.close()
