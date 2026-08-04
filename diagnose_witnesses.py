"""
Temporary diagnostic — checking whether witness/chair info exists on
individual hearing pages (vs. the committee listing page the scraper
currently reads). Removed after use.
"""
import asyncio
from playwright.async_api import async_playwright
from scrape import extract_witnesses, extract_chair

URLS = [
    "https://www.judiciary.senate.gov/committee-activity/hearings/the-nomination-of-the-honorable-todd-blanche-to-be-attorney-general-of-the-united-states-day-2",
    "https://www.judiciary.senate.gov/committee-activity/hearings/your-data-their-profit-the-consumer-cost-of-ai-surveillance-pricing",
    "https://www.indian.senate.gov/hearings/roundtable-titled-tracking-prediction-markets-exponential-growth-tribal-implications-and-beyond/",
]

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context()
        for url in URLS:
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=20000)
                await asyncio.sleep(1)
                text = await page.inner_text("body")
                print("=" * 20, url, "=" * 20)
                print("length:", len(text))
                w = extract_witnesses(text)
                c = extract_chair(text)
                print("extract_witnesses found:", w)
                print("extract_chair found:", repr(c))
                # Manually check for any lines that look witness/chair-like
                for line in text.split("\n"):
                    l = line.strip()
                    if not l:
                        continue
                    low = l.lower()
                    if "witness" in low or "chair" in low or l.startswith(("Mr.", "Ms.", "Mrs.", "Dr.", "The Honorable", "Hon.", "Prof.")):
                        print("  CANDIDATE LINE:", repr(l))
            except Exception as e:
                print(url, "ERROR:", e)
            await page.close()
        await browser.close()

asyncio.run(main())
