"""
Smoke tests for scrape_meeting_committees.py. DomeWatch's /committee-meetings
API has no committee-name field (verified against its full response schema),
so we scrape each meeting's real docs.house.gov page for it instead.
"""
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


def test_recheck_candidates_only_returns_still_known_cached_meetings():
    meetings = [
        {"id": "1", "url": "http://x/1"},
        {"id": "2", "url": "http://x/2"},
    ]
    # "3" is cached but no longer in the meeting list (aged out of the
    # 90-day window) — shouldn't be a recheck candidate, there's no url
    # left to re-fetch it from.
    cache = {"1": "Committee A", "2": "Committee B", "3": "Committee C"}
    candidates = smc.recheck_candidates(meetings, cache, limit=10)
    assert [m["id"] for m in candidates] == ["1", "2"]


def test_recheck_candidates_respects_limit_and_oldest_first():
    meetings = [{"id": str(i), "url": f"http://x/{i}"} for i in range(5)]
    # dict insertion order == check recency; "0" was cached longest ago
    cache = {"0": "A", "1": "B", "2": "C", "3": "D", "4": "E"}
    candidates = smc.recheck_candidates(meetings, cache, limit=2)
    assert [m["id"] for m in candidates] == ["0", "1"]


def test_recheck_candidates_zero_limit_returns_nothing():
    meetings = [{"id": "1", "url": "http://x/1"}]
    cache = {"1": "Committee A"}
    assert smc.recheck_candidates(meetings, cache, limit=0) == []


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
    assert smc.extract_committee_name(REAL_EVENT_HTML) == "Committee on Rules"


def test_extract_committee_name_missing_returns_none():
    assert smc.extract_committee_name(NO_COMMITTEE_HTML) is None


def test_extract_committee_name_strips_nested_tags():
    html = """
    <h1>Meeting: X<small><blockquote>
        <p><b>Committee on <i>Rules</i></b><br></p>
    </blockquote></small></h1>
    """
    assert smc.extract_committee_name(html) == "Committee on Rules"
