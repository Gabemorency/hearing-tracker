"""
Smoke tests for the pure helpers in fetch_domewatch_calendar.py. These do
not launch a browser or hit the network — see the module docstring for why
(tests.yml never installs Playwright's browser binary, unlike update.yml).
"""
from fetch_domewatch_calendar import clean_labels, merge_calendar_days


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
