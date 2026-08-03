"""
TEMPORARY diagnostic script — to be deleted after use.
Final confirmation before writing fetch_domewatch_calendar.py: get the
exact outerHTML of a day cell that has an event ("Voting Day" on Aug 31),
confirm the "next month" button selector works and advances the grid,
and confirm the legend text so we capture every status label variant.
"""
from playwright.sync_api import sync_playwright

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto("https://domewatch.us/calendar", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        print("=== Day cell with a known event (Aug 31, 2026 = Voting Day) ===")
        cell_html = page.eval_on_selector(
            "td[data-date='2026-08-31']",
            "el => el ? el.outerHTML : null"
        )
        print(cell_html)

        print("\n=== A day cell with NO event, for contrast (Aug 10, 2026) ===")
        cell_html2 = page.eval_on_selector(
            "td[data-date='2026-08-10']",
            "el => el ? el.outerHTML : null"
        )
        print(cell_html2)

        print("\n=== Legend text (search for legend-ish containers) ===")
        legend = page.eval_on_selector_all(
            "[class*='legend'], [class*='key']",
            "els => els.map(e => ({cls: e.className, html: e.outerHTML.slice(0,800)}))"
        )
        print(legend)

        print("\n=== Next-month button candidates ===")
        next_btns = page.eval_on_selector_all(
            "button[class*='next'], .fc-next-button",
            "els => els.map(e => ({cls: e.className, title: e.title, disabled: e.disabled}))"
        )
        print(next_btns)

        print("\n=== Clicking next-month button and re-checking month title ===")
        title_before = page.eval_on_selector(".fc-toolbar-title", "el => el ? el.innerText : null")
        page.click(".fc-next-button")
        page.wait_for_timeout(1500)
        title_after = page.eval_on_selector(".fc-toolbar-title", "el => el ? el.innerText : null")
        print(f"title before: {title_before!r}, after clicking next: {title_after!r}")

        # Confirm a day cell exists in the new month and check its date format
        sample_cells = page.eval_on_selector_all(
            "td.fc-daygrid-day",
            "els => els.slice(0,3).map(e => e.getAttribute('data-date'))"
        )
        print(f"first 3 day cells' data-date in new month: {sample_cells}")

        browser.close()

if __name__ == "__main__":
    main()
