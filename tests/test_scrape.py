"""
Smoke tests for the pure parsing/matching helpers in scrape.py.
These do not hit the network — they only exercise text-processing
logic that's easy to break silently when source sites change markup.
"""
import scrape


def test_hearing_key_is_stable():
    h = {"chamber": "Senate", "committee": "Judiciary", "time": "10:00 AM"}
    assert scrape.hearing_key(h) == "Senate|Judiciary|10:00 AM"


def test_norm_time_strips_timezone_and_spaces():
    assert scrape.norm_time("10:00 AM ET") == "10:00AM"
    assert scrape.norm_time("2:30 PM EDT") == "2:30PM"
    assert scrape.norm_time("TBD") == "TBD"


def test_norm_cmte_strips_common_prefixes():
    assert scrape.norm_cmte("Senate Committee on the Judiciary") == "judiciary"
    assert scrape.norm_cmte("Committee on Commerce, Science, & Transportation") == \
        "commerce science and transportation"
    assert scrape.norm_cmte("Subcommittee on Aviation") == "aviation"


def test_cmte_similarity_matches_variants():
    assert scrape.cmte_similarity(
        "Senate Committee on Commerce, Science, and Transportation",
        "Commerce, Science & Transportation",
    )
    assert scrape.cmte_similarity(
        "House Committee on the Judiciary",
        "Judiciary",
    )
    assert not scrape.cmte_similarity("Judiciary", "Armed Services")


def test_fuzzy_match_same_chamber_and_committee():
    h1 = {"chamber": "Senate", "committee": "Judiciary", "time": "10:00 AM ET"}
    h2 = {"chamber": "Senate", "committee": "Committee on the Judiciary", "time": "10:00 AM"}
    assert scrape.fuzzy_match(h1, h2)


def test_fuzzy_match_rejects_different_committee():
    h1 = {"chamber": "Senate", "committee": "Judiciary", "time": "10:00 AM"}
    h2 = {"chamber": "Senate", "committee": "Armed Services", "time": "10:00 AM"}
    assert not scrape.fuzzy_match(h1, h2)


def test_fuzzy_match_allows_joint_to_match_senate():
    h1 = {"chamber": "Joint", "committee": "Joint Economic", "time": "10:00 AM"}
    h2 = {"chamber": "Senate", "committee": "Joint Economic", "time": "10:00 AM"}
    assert scrape.fuzzy_match(h1, h2)


def test_extract_witnesses_matches_honorifics():
    text = "\n".join([
        "Mr. John Smith, CEO of Example Corp",
        "The Honorable Jane Doe, Secretary of Something",
        "Some unrelated line that is not a witness",
        "Dr. Alice Lee, Director",
    ])
    witnesses = scrape.extract_witnesses(text)
    assert "Mr. John Smith, CEO of Example Corp" in witnesses
    assert "The Honorable Jane Doe, Secretary of Something" in witnesses
    assert "Dr. Alice Lee, Director" in witnesses
    assert len(witnesses) == 3


def test_extract_witnesses_dedupes():
    text = "Mr. John Smith, CEO\nMr. John Smith, CEO"
    assert scrape.extract_witnesses(text) == ["Mr. John Smith, CEO"]


def test_extract_chair_rejects_ranking_member():
    text = "Ranking Member Jane Doe (D-NY) spoke first."
    assert scrape.extract_chair(text) == ""


def test_extract_chair_finds_valid_chair():
    text = "Chairman John Smith (R-TX) called the hearing to order."
    chair = scrape.extract_chair(text)
    assert "Smith" in chair


def test_building_from_room_maps_known_prefixes():
    assert scrape.building_from_room("SR-325") == "Russell (SR)"
    assert scrape.building_from_room("SD-106") == "Dirksen (SD)"
    assert scrape.building_from_room("unknown-room") == "Dirksen (SD)"


def test_house_building_from_room_maps_known_buildings():
    assert scrape.house_building_from_room("2154 RHOB") == "Rayburn (RHOB)"
    assert scrape.house_building_from_room("1100 LHOB") == "Longworth (LHOB)"
    assert scrape.house_building_from_room("2247 CHOB") == "Cannon (CHOB)"


def test_lookup_chair_matches_known_committee():
    chair = scrape.lookup_chair("Senate Committee on the Judiciary")
    assert "Grassley" in chair


def test_lookup_chair_no_match_returns_empty():
    assert scrape.lookup_chair("Totally Made Up Committee Name") == ""


def test_detect_cancellation_loose_check():
    assert scrape.detect_cancellation("Hearing postponed until further notice")
    assert not scrape.detect_cancellation("Hearing on the state of the economy")


def test_diff_hearing_reports_time_and_room_changes():
    old = {"time": "10:00 AM", "room": "SD-106", "building": "Dirksen (SD)", "witnesses": []}
    new = {"time": "2:00 PM", "room": "SR-325", "building": "Russell (SR)", "witnesses": []}
    changes = scrape.diff_hearing(old, new)
    assert any("Time changed" in c for c in changes)
    assert any("Room changed" in c for c in changes)
    assert any("Location changed" in c for c in changes)


def test_diff_hearing_reports_cancellation():
    old = {"cancelled": False}
    new = {"cancelled": True}
    assert "CANCELLED" in scrape.diff_hearing(old, new)


def test_watch_link_matches_senate_committee():
    assert scrape.watch_link("Senate", "Committee on the Judiciary") == \
        "https://www.judiciary.senate.gov/committee-activity/hearings"


def test_watch_link_matches_house_committee():
    assert scrape.watch_link("House", "Financial Services") == \
        "https://financialservices.house.gov/calendar/"


def test_watch_link_joint_falls_back_to_senate_pages():
    assert scrape.watch_link("Joint", "Joint Economic Committee") == \
        "https://www.jec.senate.gov/public/index.cfm/hearings-calendar"


def test_watch_link_no_match_returns_empty():
    assert scrape.watch_link("House", "Totally Fake Committee") == ""


def test_diff_hearing_no_changes_when_identical():
    h = {"time": "10:00 AM", "room": "SD-106", "building": "Dirksen (SD)",
         "witnesses": [], "cancelled": False}
    assert scrape.diff_hearing(h, dict(h)) == []
