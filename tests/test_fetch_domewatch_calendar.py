"""
Smoke tests for the pure helpers in fetch_domewatch_calendar.py. These do
not launch a browser or hit the network — see the module docstring for why
(tests.yml never installs Playwright's browser binary, unlike update.yml).
"""
from fetch_domewatch_calendar import build_domewatch_calendar_rows, clean_labels, merge_calendar_days


def test_clean_labels_strips_and_dedupes():
    assert clean_labels(["  Voting Day ", "Voting Day", "", None, "Federal holiday"]) == \
        ["Voting Day", "Federal holiday"]


def test_clean_labels_empty_input():
    assert clean_labels([]) == []


def test_merge_calendar_days_overwrites_on_overlap():
    a = {"2026-08-31": ["Voting Day"]}
    b = {"2026-08-31": ["Voting Day", "Added Voting Day"], "2026-09-01": ["Voting Day"]}
    assert merge_calendar_days(a, b) == {
        "2026-08-31": ["Voting Day", "Added Voting Day"],
        "2026-09-01": ["Voting Day"],
    }


def test_merge_calendar_days_no_dicts():
    assert merge_calendar_days() == {}


def test_merge_calendar_days_single_dict_passthrough():
    a = {"2026-09-07": ["Federal holiday"]}
    assert merge_calendar_days(a) == a


def test_build_domewatch_calendar_rows_basic_shape():
    days = {"2026-08-31": ["Voting Day"], "2026-09-07": ["Federal holiday"]}
    rows = build_domewatch_calendar_rows("2026-08-30T12:00:00+00:00", days)
    assert rows == [
        {"date": "2026-08-31", "labels": ["Voting Day"], "fetched_at": "2026-08-30T12:00:00+00:00"},
        {"date": "2026-09-07", "labels": ["Federal holiday"], "fetched_at": "2026-08-30T12:00:00+00:00"},
    ]


def test_build_domewatch_calendar_rows_empty_input():
    assert build_domewatch_calendar_rows("2026-08-30T12:00:00+00:00", {}) == []
