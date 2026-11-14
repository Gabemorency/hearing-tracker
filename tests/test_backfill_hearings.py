import backfill_hearings as bh


def test_blank_to_none():
    assert bh.blank_to_none("") is None
    assert bh.blank_to_none(None) is None
    assert bh.blank_to_none("Chair Name") == "Chair Name"


def test_build_hearing_rows_basic_shape():
    history = {
        "2026-07-28": {
            "inSession": True,
            "hearings": [
                {
                    "chamber": "Senate",
                    "committee": "Judiciary",
                    "chair": "",
                    "time": "10:00 AM ET",
                    "building": "Dirksen (SD)",
                    "room": "SD-226",
                    "topic": "Nomination hearing",
                    "details": "",
                    "witnesses": ["Jane Doe"],
                    "cancelled": False,
                    "changes": [],
                    "link": "https://example.com",
                }
            ],
        }
    }
    rows, skipped = bh.build_hearing_rows(history)
    assert skipped == 0
    assert len(rows) == 1
    row = rows[0]
    assert row["date"] == "2026-07-28"
    assert row["chamber"] == "Senate"
    assert row["committee"] == "Judiciary"
    # Blank strings become None, not kept as "".
    assert row["chair"] is None
    assert row["details"] is None
    assert row["witnesses"] == ["Jane Doe"]


def test_build_hearing_rows_skips_entries_missing_chamber_or_committee():
    history = {
        "2026-07-29": {
            "hearings": [
                {"chamber": "", "committee": "Judiciary", "topic": "x"},
                {"chamber": "House", "committee": "", "topic": "y"},
                {"chamber": "House", "committee": "Rules", "topic": "z", "time": "1 PM"},
            ]
        }
    }
    rows, skipped = bh.build_hearing_rows(history)
    assert skipped == 2
    assert len(rows) == 1
    assert rows[0]["committee"] == "Rules"


def test_build_hearing_rows_defaults_missing_optional_fields():
    history = {"2026-08-01": {"hearings": [{"chamber": "House", "committee": "Rules", "topic": "x"}]}}
    rows, _ = bh.build_hearing_rows(history)
    row = rows[0]
    assert row["witnesses"] == []
    assert row["changes"] == []
    assert row["cancelled"] is False
    assert row["link"] is None


def test_build_baseline_rows_basic_shape_has_no_link_key():
    # baseline_hearings has no "link" column — must never be sent.
    hearings = [
        {
            "chamber": "Senate",
            "committee": "Judiciary",
            "chair": "",
            "time": "10:00 AM ET",
            "building": "Dirksen (SD)",
            "room": "SD-226",
            "topic": "Nomination hearing",
            "details": "",
            "witnesses": ["Jane Doe"],
            "cancelled": False,
        }
    ]
    rows = bh.build_baseline_rows("2026-07-30", hearings)
    assert len(rows) == 1
    row = rows[0]
    assert row["date"] == "2026-07-30"
    assert "link" not in row
    assert "changes" not in row
    assert row["chair"] is None
    assert row["details"] is None


def test_build_baseline_rows_skips_missing_chamber_or_committee():
    hearings = [
        {"chamber": "", "committee": "Judiciary"},
        {"chamber": "House", "committee": ""},
        {"chamber": "House", "committee": "Rules"},
    ]
    rows = bh.build_baseline_rows("2026-07-30", hearings)
    assert len(rows) == 1
    assert rows[0]["committee"] == "Rules"
