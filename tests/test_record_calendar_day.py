"""
Smoke tests for record_calendar_day.py's backfill_missing_links(). A user
reported hearing entries on the calendar with no clickable link — traced to
historical calendar_history.json entries written before scrape.py's link
was persisted to snapshot.json correctly. watch_link() is a pure fuzzy-match
against a static committee-page table, so it's safe to recompute for any
hearing still missing a link.
"""
from record_calendar_day import backfill_missing_links


def test_fills_missing_link_for_known_committee():
    history = {
        "2026-07-28": {
            "hearings": [
                {"chamber": "Senate", "committee": "Indian Affairs", "link": None},
            ],
            "inSession": True,
        }
    }
    filled = backfill_missing_links(history)
    assert filled == 1
    assert history["2026-07-28"]["hearings"][0]["link"] == "https://www.indian.senate.gov/hearings"


def test_leaves_existing_link_untouched():
    history = {
        "2026-07-28": {
            "hearings": [
                {"chamber": "Senate", "committee": "Indian Affairs", "link": "https://example.com/keep-me"},
            ],
        }
    }
    filled = backfill_missing_links(history)
    assert filled == 0
    assert history["2026-07-28"]["hearings"][0]["link"] == "https://example.com/keep-me"


def test_no_match_leaves_link_empty_not_crashing():
    history = {
        "2026-07-28": {
            "hearings": [
                {"chamber": "Senate", "committee": "Not A Real Committee At All", "link": ""},
            ],
        }
    }
    filled = backfill_missing_links(history)
    assert filled == 0
    assert history["2026-07-28"]["hearings"][0]["link"] == ""


def test_handles_missing_hearings_key():
    history = {"2026-07-28": {"inSession": False}}
    assert backfill_missing_links(history) == 0
