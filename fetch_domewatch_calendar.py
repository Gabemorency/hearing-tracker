"""
fetch_domewatch_calendar.py — run twice daily by domewatch_calendar.yml,
not tied to the 2-hour update.yml cadence, since DomeWatch's projected
session calendar rarely changes within a day.

domewatch.us/calendar renders a real, forward-looking multi-month calendar
(Voting Day / Federal holiday / Added Voting Day / CANCELLED VOTES labels
on specific dates) using FullCalendar.js — a well-documented open-source
calendar library, so this scrapes its stable DOM conventions rather than a
hand-calibrated layout. Confirmed live against the real site: a day cell
is <td data-date="2026-08-31">...<div class="fc-event-title">Voting
Day</div>...</td>, and clicking .fc-next-button reliably re-renders the
grid to the next month (verified August 2026 -> September 2026 with real
dates in both views).

Covers the current month plus the next NUM_MONTHS-1 months by reading the
grid, clicking "next", and reading again. Only dates with at least one
real label are kept in the output — DomeWatch itself doesn't mark every
day, and we don't invent an "in session"/"recess" status for the rest.

NUM_MONTHS is 5, not 4: FullCalendar's month-grid view pads out the last
row with a few leading days of the following month (e.g. November's grid
also shows Dec 1-11 as real, correctly-labeled filler days) — which looks
like partial next-month coverage but isn't a full read of that month's
own page. A user caught this directly: DomeWatch showed Dec 14-17 as
Voting Days, but our data stopped at Dec 11 because we never actually
advanced to December's own grid. Reading one extra month closes that gap
for real, rather than relying on whatever a neighboring month's filler
days happen to include.
"""
import json
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

OUT_FILE     = "domewatch_calendar.json"
NUM_MONTHS   = 5
CALENDAR_URL = "https://domewatch.us/calendar"


def clean_labels(labels):
    """Strip whitespace, drop empties, dedupe while preserving order."""
    seen = []
    for label in labels:
        label = (label or "").strip()
        if label and label not in seen:
            seen.append(label)
    return seen


def merge_calendar_days(*day_dicts):
    """Merge multiple {date: [labels]} dicts, later ones winning on overlap.
    Adjacent FullCalendar month views repeat a few leading/trailing days of
    each other (e.g. the last days of August also appear as filler in
    September's grid) — the later scrape of a repeated date is just as
    fresh, so a plain overwrite is fine."""
    merged = {}
    for days in day_dicts:
        merged.update(days)
    return merged


def scrape_calendar(num_months=NUM_MONTHS):
    all_days = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(CALENDAR_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1500)

        for i in range(num_months):
            month_days = page.eval_on_selector_all(
                "td.fc-daygrid-day",
                """els => Object.fromEntries(
                    Array.from(els).map(td => {
                        const date = td.getAttribute('data-date');
                        const titles = Array.from(td.querySelectorAll('.fc-event-title'))
                            .map(e => e.innerText.trim()).filter(Boolean);
                        return [date, titles];
                    }).filter(([date, titles]) => titles.length > 0)
                )"""
            )
            month_days = {d: clean_labels(labels) for d, labels in month_days.items()}
            all_days = merge_calendar_days(all_days, month_days)

            if i < num_months - 1:
                title_before = page.eval_on_selector(".fc-toolbar-title", "el => el.innerText")
                page.click(".fc-next-button")
                page.wait_for_function(
                    """(prevTitle) => {
                        const el = document.querySelector('.fc-toolbar-title');
                        return el && el.innerText !== prevTitle;
                    }""",
                    arg=title_before,
                    timeout=10000,
                )
                page.wait_for_timeout(500)

        browser.close()
    return all_days


def main():
    try:
        days = scrape_calendar()
    except Exception as e:
        print(f"fetch_domewatch_calendar: failed ({e}) — keeping existing {OUT_FILE}")
        return

    if not days:
        print(f"fetch_domewatch_calendar: scrape returned 0 labeled days — "
              f"keeping existing {OUT_FILE} rather than overwriting with empty data")
        return

    out = {
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "days": days,
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"fetch_domewatch_calendar: saved {len(days)} labeled day(s) "
          f"across {NUM_MONTHS} months to {OUT_FILE}")


if __name__ == "__main__":
    main()
