"""
TEMPORARY diagnostic script — to be deleted after use.
Found the real calendar: https://domewatch.us/calendar renders a real
month grid with per-day status labels (Voting Day, FEDERAL HOLIDAY,
CANCELLED VOTES, etc.) via client-side JS. Now inspect the actual DOM
structure (selectors, per-cell HTML) and figure out how to navigate to
future months (URL param vs. click-based "next" nav) so we can cover
~4 months ahead.
"""
from playwright.sync_api import sync_playwright

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        print("=== Loading /calendar and inspecting structure ===")
        page.goto("https://domewatch.us/calendar", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        # Dump the calendar container's outerHTML (find something calendar-ish)
        html = page.content()
        # Save a trimmed version focused on any element with class containing "cal" or "day"
        candidates = page.eval_on_selector_all(
            "[class*='cal'], [class*='day'], [class*='month']",
            "els => els.slice(0, 5).map(e => ({tag: e.tagName, cls: e.className, html: e.outerHTML.slice(0, 500)}))"
        )
        print(f"Elements with cal/day/month in class name (first 5): {len(candidates)}")
        for c in candidates:
            print(f"  <{c['tag']} class={c['cls']!r}>: {c['html'][:500]}")

        # Try to find "next month" control
        next_candidates = page.eval_on_selector_all(
            "button, a, [role='button']",
            "els => els.map(e => ({text: e.innerText.trim(), aria: e.getAttribute('aria-label'), cls: e.className})).filter(x => x.text || x.aria)"
        )
        print(f"\nButtons/links with text or aria-label ({len(next_candidates)} total):")
        for c in next_candidates[:40]:
            print(f"  {c}")

        print(f"\nCurrent URL: {page.url}")

        # Try common query-param patterns for navigating months
        for test_url in [
            "https://domewatch.us/calendar?month=9&year=2026",
            "https://domewatch.us/calendar/2026-09",
            "https://domewatch.us/calendar/9/2026",
        ]:
            try:
                page.goto(test_url, wait_until="networkidle", timeout=15000)
                page.wait_for_timeout(1500)
                bt = page.eval_on_selector("body", "el => el.innerText")
                print(f"\n=== {test_url} -> body[:300]: {bt[:300]!r}")
            except Exception as e:
                print(f"\n=== {test_url} failed: {e}")

        browser.close()

if __name__ == "__main__":
    main()
