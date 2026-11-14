import backfill_members as bm


def test_build_member_row_basic():
    person = {
        "id": {"bioguide": "C000127"},
        "name": {"first": "Maria", "last": "Cantwell", "official_full": "Maria Cantwell"},
        "terms": [{"type": "sen", "state": "WA"}],
    }
    row = bm.build_member_row(person, is_current=True, bios={"C000127": "Her bio."})
    assert row == {
        "bioguide_id": "C000127",
        "first_name": "Maria",
        "last_name": "Cantwell",
        "full_name": "Maria Cantwell",
        "nickname": None,
        "delegate": False,
        "is_current": True,
        "bio": "Her bio.",
    }


def test_build_member_row_omits_bio_key_when_bios_not_passed():
    # The nightly roster sync (build_members.py) must never touch the
    # "bio" column — bio_sync.py owns that on its own, more frequent
    # schedule. Passing no bios arg has to omit the key entirely, not
    # send "bio": None, or the upsert would null out an existing bio.
    person = {
        "id": {"bioguide": "C000127"},
        "name": {"first": "Maria", "last": "Cantwell", "official_full": "Maria Cantwell"},
        "terms": [{"type": "sen", "state": "WA"}],
    }
    row = bm.build_member_row(person, is_current=True)
    assert "bio" not in row


def test_build_member_row_missing_bioguide_returns_none():
    person = {"id": {}, "name": {"first": "No", "last": "Id"}, "terms": []}
    assert bm.build_member_row(person, is_current=True, bios={}) is None


def test_build_member_row_delegate_detection():
    # A House term representing a territory makes them a delegate.
    person = {
        "id": {"bioguide": "D000001"},
        "name": {"first": "D", "last": "C.", "official_full": "D.C. Delegate"},
        "terms": [{"type": "rep", "state": "DC"}],
    }
    row = bm.build_member_row(person, is_current=True, bios={})
    assert row["delegate"] is True

    # A House term for an actual state is not a delegate.
    person2 = {
        "id": {"bioguide": "R000001"},
        "name": {"first": "R", "last": "Rep", "official_full": "R. Rep"},
        "terms": [{"type": "rep", "state": "CA"}],
    }
    assert bm.build_member_row(person2, is_current=True, bios={})["delegate"] is False


def test_build_member_row_no_bio_available():
    person = {"id": {"bioguide": "X000001"}, "name": {"first": "X", "last": "Y"}, "terms": []}
    row = bm.build_member_row(person, is_current=False, bios={})
    assert row["bio"] is None
    assert row["is_current"] is False


def test_build_term_rows_maps_chamber_and_district():
    person = {
        "id": {"bioguide": "C000127"},
        "terms": [
            {"type": "rep", "state": "WA", "district": 1, "party": "Democrat", "start": "1993-01-05", "end": "1995-01-03"},
            {"type": "sen", "state": "WA", "class": 1, "party": "Democrat", "start": "2001-01-03", "end": "2007-01-03"},
        ],
    }
    rows = bm.build_term_rows(person)
    assert len(rows) == 2
    assert rows[0] == {
        "member_id": "C000127",
        "chamber": "House",
        "state": "WA",
        "district": "1",
        "party": "Democrat",
        "start_date": "1993-01-05",
        "end_date": "1995-01-03",
    }
    assert rows[1]["chamber"] == "Senate"
    assert rows[1]["district"] is None


def test_build_term_rows_skips_incomplete_terms():
    person = {
        "id": {"bioguide": "C000127"},
        "terms": [
            {"type": "rep", "state": "WA", "start": "1993-01-05"},  # missing end
            {"type": "unknown", "state": "WA", "start": "1993-01-05", "end": "1995-01-03"},
            {"type": "sen", "start": "1993-01-05", "end": "1995-01-03"},  # missing state
        ],
    }
    assert bm.build_term_rows(person) == []


def test_build_term_rows_missing_bioguide_returns_empty():
    assert bm.build_term_rows({"id": {}, "terms": [{"type": "rep"}]}) == []
