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


def test_is_today_matches_senate_gov_weekday_zero_padded_format():
    # senate.gov's own hearings/meetings listing renders today's date as
    # "Tuesday, Aug 04, 2026" (full weekday, abbreviated month, zero-padded
    # day) — a format none of the original today_variants matched, so the
    # whole page silently read as having no hearings today, even on days
    # with real, live hearings (e.g. a committee's business meeting to
    # vote on a nominee).
    real_page_text = (
        "Time-Room\tCommittee\tTopic\n"
        f"{scrape.now_et.strftime('%A, %b %d, %Y')}\n"
        "9:00 AM – SH-216\tJudiciary\n"
        "\tBusiness meeting to consider a nomination.\n"
    )
    assert scrape.is_today(real_page_text) is True


# Real judiciary.senate.gov page text, captured live on 2026-08-04: three
# same-day entries — a real, active business meeting (the Blanche AG vote),
# a genuinely postponed unrelated hearing, and a second real, active
# hearing — each entry only ~150-200 chars apart.
BLANCHE_TOPIC     = "Business meeting to consider the nomination of Todd Blanche, of Florida, to be Attorney General."
DRUG_COSTS_TOPIC  = "Prescribing Sunshine: How Competition & Transparency Lowers Prescription Drug Costs"
AI_SURVEILLANCE_TOPIC = "Your Data, Their Profit: The Consumer Cost of AI Surveillance Pricing"

def _real_judiciary_page_text(date):
    return (
        "Upcoming Hearings\n"
        "Executive Business Meeting\n"
        "Hart Senate Office Building Room 216\n"
        f"{date} at 09:00am\n"
        "Add to Calendar ▿\n"
        f"POSTPONED: {DRUG_COSTS_TOPIC}\n"
        "Hart Senate Office Building Room 216\n"
        f"{date} at 10:15am\n"
        "Add to Calendar ▿\n"
        f"{AI_SURVEILLANCE_TOPIC}\n"
        "Dirksen Senate Office Building Room 226\n"
        f"{date} at 02:30pm\n"
        "Add to Calendar ▿\n"
    )


def test_find_cancelled_contexts_finds_exactly_the_one_cancelled_entry():
    # Three same-day entries on one page; only the middle one is actually
    # cancelled. A forward-looking window would misattribute it to the
    # first entry (Blanche); a fixed-size backward window large enough to
    # span multiple entries would misattribute it to the third (AI
    # Surveillance) too, since all three dates sit within ~350 chars of
    # each other. Exactly one context should come back.
    date = scrape.now_et.strftime("%m/%d/%y")
    contexts = scrape.find_cancelled_contexts(_real_judiciary_page_text(date))
    assert len(contexts) == 1
    assert "postponed" in contexts[0]


def test_cancellation_only_applies_to_matching_topic_not_whole_committee():
    # The real regression this guards against: a committee page with a
    # cancelled item sandwiched between two active ones on the same day
    # used to get collapsed into a single boolean and applied to *every*
    # hearing under that committee — flagging both the real, active
    # Blanche AG vote AND the real, active AI-surveillance hearing as
    # cancelled, just because an unrelated hearing on the same page was
    # genuinely postponed. Cancellation must be matched against each
    # hearing's own topic text, the same word-overlap approach already
    # used for hearing links.
    date = scrape.now_et.strftime("%m/%d/%y")
    contexts = scrape.find_cancelled_contexts(_real_judiciary_page_text(date))

    assert not any(scrape.word_overlap_score(BLANCHE_TOPIC, c) >= 0.5 for c in contexts)
    assert not any(scrape.word_overlap_score(AI_SURVEILLANCE_TOPIC, c) >= 0.5 for c in contexts)
    assert any(scrape.word_overlap_score(DRUG_COSTS_TOPIC, c) >= 0.5 for c in contexts)


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


def test_word_overlap_score_real_match():
    # Real example: July 28 Homeland Security hearing vs its actual
    # hsgac.senate.gov link text.
    topic = "Hearings to examine the testimony of Anthony Fauci."
    candidate_text = "Testimony of Anthony Fauci"
    assert scrape.word_overlap_score(topic, candidate_text) == 1.0


def test_word_overlap_score_unrelated_text():
    assert scrape.word_overlap_score(
        "Hearing to examine the state of the U.S. Territories",
        "Nomination Hearing"
    ) < 0.34


def test_word_overlap_score_empty_inputs():
    assert scrape.word_overlap_score("", "Some hearing title") == 0.0
    assert scrape.word_overlap_score("Some hearing title", "") == 0.0


def test_best_hearing_link_picks_highest_scoring_candidate():
    candidates = [
        {"text": "Business Meeting to Consider Nominations", "href": "https://example.com/wrong"},
        {"text": "Testimony of Anthony Fauci", "href": "https://example.com/right"},
    ]
    link = scrape.best_hearing_link(
        "Hearings to examine the testimony of Anthony Fauci.", candidates)
    assert link == "https://example.com/right"


def test_best_hearing_link_returns_none_below_threshold():
    candidates = [{"text": "Completely Unrelated Nomination Hearing", "href": "https://example.com/x"}]
    assert scrape.best_hearing_link("The AI Deception Machine", candidates) is None


def test_best_hearing_link_returns_none_for_empty_candidates():
    assert scrape.best_hearing_link("Any topic", []) is None


def test_hearing_link_rules_only_reference_real_committees():
    """Every (chamber, name) key must exist in the corresponding committee
    page table, or watch_link()'s generic fallback would silently never
    fire for that rule (a typo'd committee name)."""
    senate_names = {name for name, _ in scrape.SENATE_COMMITTEE_PAGES}
    house_names  = {name for name, _ in scrape.HOUSE_COMMITTEE_PAGES}
    for (chamber, name) in scrape.HEARING_LINK_RULES:
        if chamber == "Senate":
            assert name in senate_names, f"{name!r} not in SENATE_COMMITTEE_PAGES"
        else:
            assert name in house_names, f"{name!r} not in HOUSE_COMMITTEE_PAGES"
