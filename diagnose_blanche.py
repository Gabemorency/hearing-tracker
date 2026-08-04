"""
Temporary diagnostic script — investigating why today's Senate Judiciary
Committee business meeting on Todd Blanche's AG nomination isn't showing
up on the site. Removed after use.
"""
import asyncio
from playwright.async_api import async_playwright
from scrape import today_variants, is_today, detect_cancellation_near_date, today_str, today_long, today_iso

async def main():
    print("today_variants:", today_variants)
    print()

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context()

        # 1. Main Senate hearings/meetings listing page
        page = await context.new_page()
        try:
            await page.goto("https://www.senate.gov/committees/hearings_meetings.htm",
                             wait_until="networkidle", timeout=30000)
            await asyncio.sleep(3)
            full_text = await page.inner_text("body")
            print("=== MAIN SENATE PAGE ===")
            print("is_today(full_text):", is_today(full_text))
            print("length:", len(full_text))
            # dump any line containing 'Judiciary' or 'Blanche'
            for line in full_text.split("\n"):
                if "judiciary" in line.lower() or "blanche" in line.lower():
                    print("MATCH LINE:", repr(line))
            # dump first 3000 chars for manual date-format inspection
            print("--- first 3000 chars ---")
            print(full_text[:3000])
        except Exception as e:
            print("MAIN PAGE ERROR:", e)
        await page.close()

        # 2. Judiciary committee's own page
        page2 = await context.new_page()
        try:
            await page2.goto("https://www.judiciary.senate.gov/committee-activity/hearings",
                              wait_until="networkidle", timeout=20000)
            await asyncio.sleep(1)
            text2 = await page2.inner_text("body")
            print()
            print("=== JUDICIARY COMMITTEE PAGE ===")
            print("is_today(text2):", is_today(text2))
            print("detect_cancellation_near_date(text2):", detect_cancellation_near_date(text2))
            for variant in today_variants:
                idx = text2.lower().find(variant.lower())
                if idx != -1:
                    window = text2[max(0, idx-500):idx+500]
                    print(f"--- context around matched variant {variant!r} ---")
                    print(window)
                    print("---")
            # dump any line containing blanche
            for line in text2.split("\n"):
                if "blanche" in line.lower():
                    print("BLANCHE LINE:", repr(line))
        except Exception as e:
            print("JUDICIARY PAGE ERROR:", e)
        await page2.close()

        await browser.close()

asyncio.run(main())
