"""
Temporary diagnostic — checking whether the 16 committee pages not covered
by HEARING_LINK_RULES actually expose a real, distinguishable per-hearing
link (and if so, what CSS selector would find it), or whether the original
PR #21 scope (20/36) is a genuine structural limit. Removed after use.
"""
import asyncio
from playwright.async_api import async_playwright

PAGES = [
    ("Senate", "Finance", "https://www.finance.senate.gov/hearings"),
    ("Senate", "Intelligence", "https://www.intelligence.senate.gov/hearings"),
    ("Senate", "Agriculture", "https://www.agriculture.senate.gov/hearings"),
    ("Senate", "Narcotics Control", "https://www.drugcaucus.senate.gov/"),
    ("House", "Agriculture", "https://agriculture.house.gov/calendar/"),
    ("House", "Appropriations", "https://appropriations.house.gov/events/hearings"),
    ("House", "Armed Services", "https://armedservices.house.gov/hearings"),
    ("House", "Education & Workforce", "https://edworkforce.house.gov/hearings/"),
    ("House", "Energy & Commerce", "https://energycommerce.house.gov/hearings"),
    ("House", "Foreign Affairs", "https://foreignaffairs.house.gov/hearings/"),
    ("House", "Homeland Security", "https://homeland.house.gov/hearings/"),
    ("House", "Judiciary", "https://judiciary.house.gov/hearings/"),
    ("House", "Natural Resources", "https://naturalresources.house.gov/hearings/"),
    ("House", "Oversight", "https://oversight.house.gov/hearings/"),
    ("House", "Transportation", "https://transportation.house.gov/hearings/"),
    ("House", "Veterans Affairs", "https://veterans.house.gov/hearings/"),
]

SCAN_JS = """
() => {
    const anchors = Array.from(document.querySelectorAll('a'));
    const candidates = anchors
        .filter(a => {
            const t = (a.innerText || '').trim();
            return t.length > 25 && t.length < 300 && a.href;
        })
        .slice(0, 6)
        .map(a => {
            function cssPath(el) {
                if (!el || el.nodeType !== 1) return '';
                let path = [];
                while (el && el.nodeType === 1 && path.length < 4) {
                    let sel = el.tagName.toLowerCase();
                    if (el.className && typeof el.className === 'string' && el.className.trim()) {
                        sel += '.' + el.className.trim().split(/\\s+/).join('.');
                    }
                    path.unshift(sel);
                    el = el.parentElement;
                }
                return path.join(' > ');
            }
            return {
                text: a.innerText.trim().slice(0, 80),
                href: a.href,
                class: a.className,
                path: cssPath(a),
            };
        });
    return { totalAnchors: anchors.length, candidates };
}
"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context()
        for chamber, name, url in PAGES:
            page = await context.new_page()
            print("=" * 15, chamber, name, url, "=" * 15)
            try:
                await page.goto(url, wait_until="networkidle", timeout=25000)
                await asyncio.sleep(1)
                result = await page.evaluate(SCAN_JS)
                print("total anchors on page:", result["totalAnchors"])
                for c in result["candidates"]:
                    print("  TEXT:", repr(c["text"]))
                    print("    href:", c["href"])
                    print("    class:", repr(c["class"]))
                    print("    path:", c["path"])
            except Exception as e:
                print("ERROR:", e)
            await page.close()
        await browser.close()

asyncio.run(main())
