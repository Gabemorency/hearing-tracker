"""
Smoke tests for the pure formatting helpers in build_members.py.
"""
import build_members


def test_initials_two_word_name():
    assert build_members.initials("Nancy Pelosi") == "NP"


def test_initials_multi_word_name_uses_first_and_last():
    assert build_members.initials("Alexandria Ocasio Cortez") == "AC"


def test_initials_single_word_name():
    assert build_members.initials("Cher") == "CH"


def test_initials_empty_name():
    assert build_members.initials("") == "?"


def test_party_label_known_parties():
    assert build_members.party_label("Republican") == "R"
    assert build_members.party_label("Democrat") == "D"
    assert build_members.party_label("Independent") == "I"


def test_party_label_unknown_party_falls_back_to_first_letter():
    assert build_members.party_label("Libertarian") == "L"
    assert build_members.party_label("") == "?"


def test_party_class_known_parties():
    assert build_members.party_class("Republican") == "rep"
    assert build_members.party_class("Democrat") == "dem"
    assert build_members.party_class("Independent") == "ind"


def test_party_class_unknown_defaults_to_ind():
    assert build_members.party_class("Libertarian") == "ind"


def test_photo_url_builds_expected_path():
    url = build_members.photo_url("A000055")
    assert url == (
        "https://raw.githubusercontent.com/unitedstates/images/"
        "gh-pages/congress/450x550/A000055.jpg"
    )


def test_photo_url_empty_bioguide_returns_empty():
    assert build_members.photo_url("") == ""


def test_get_leadership_matches_known_title():
    result = build_members.get_leadership("Speaker of the House")
    assert result == {"label": "Speaker", "tier": 1}


def test_get_leadership_matches_case_insensitively():
    result = build_members.get_leadership("MAJORITY WHIP")
    assert result == {"label": "Majority Whip", "tier": 2}


def test_get_leadership_unknown_title_returns_none():
    assert build_members.get_leadership("Backbencher") is None


def test_get_leadership_empty_title_returns_none():
    assert build_members.get_leadership("") is None


def test_build_committee_membership_rows_flattens_per_member():
    cmte_roles_map = {
        "C000127": [
            {"committee": "Commerce", "chamber": "Senate", "role": "Chair", "rank": 1, "is_full_committee": True},
            {"committee": "Commerce — Subcommittee on Communications", "chamber": "Senate", "role": "Member",
             "rank": 4, "is_full_committee": False},
        ],
        "B000002": [
            {"committee": "Judiciary", "chamber": "House", "role": "Member", "rank": 7, "is_full_committee": True},
        ],
    }
    rows = build_members.build_committee_membership_rows(cmte_roles_map)
    assert len(rows) == 3
    assert rows[0] == {
        "member_id": "C000127",
        "committee": "Commerce",
        "chamber": "Senate",
        "role": "Chair",
        "rank": 1,
        "is_full_committee": True,
    }
    assert rows[2]["member_id"] == "B000002"
    assert rows[2]["is_full_committee"] is True


def test_build_committee_membership_rows_empty_map():
    assert build_members.build_committee_membership_rows({}) == []
