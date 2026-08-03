"""
Smoke tests for scrape_meeting_committees.py. DomeWatch's /committee-meetings
API has no committee-name field (verified against its full response schema),
so we scrape each meeting's real docs.house.gov page for it instead.
"""
from playwright.sync_api import sync_playwright

import scrape_meeting_committees as smc


def test_pending_meetings_skips_cached():
    meetings = [
        {"id": "1", "url": "http://x/1"},
        {"id": "2", "url": "http://x/2"},
    ]
    cache = {"1": "Committee on Rules"}
    pending = smc.pending_meetings(meetings, cache)
    assert [m["id"] for m in pending] == ["2"]


def test_pending_meetings_skips_missing_id_or_url():
    meetings = [
        {"id": "1"},
        {"url": "http://x/2"},
        {"id": "3", "url": "http://x/3"},
    ]
    pending = smc.pending_meetings(meetings, {})
    assert [m["id"] for m in pending] == ["3"]


def test_pending_meetings_respects_cap():
    meetings = [{"id": str(i), "url": f"http://x/{i}"} for i in range(10)]
    pending = smc.pending_meetings(meetings, {}, max_per_run=3)
    assert len(pending) == 3


# Real shape confirmed against a live docs.house.gov ByEvent.aspx page:
# <h1>Meeting: <title><small class="text-tiny"><blockquote>
#   <p>Committee on Rules<br></p></blockquote></small></h1>
REAL_EVENT_HTML = """
<html><body>
<h1>
    Meeting:
    H.R. 139 &ndash; Sunshine Protection Act of 2025
    <small class="text-tiny"><blockquote>
        <p>Committee on Rules<br></p>
    </blockquote></small>
</h1>
</body></html>
"""

NO_COMMITTEE_HTML = "<html><body><h2>Error Encountered</h2></body></html>"


def test_extract_committee_name_real_shape():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        page = browser.new_page()
        page.set_content(REAL_EVENT_HTML)
        assert smc.extract_committee_name(page) == "Committee on Rules"
        browser.close()


def test_extract_committee_name_missing_returns_none():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        page = browser.new_page()
        page.set_content(NO_COMMITTEE_HTML)
        assert smc.extract_committee_name(page) is None
        browser.close()
