from datetime import date

import fetch_votes as fv

HOUSE_VOTE_XML = b"""<?xml version="1.0"?>
<rollcall-vote>
  <vote-metadata>
    <congress>119</congress>
    <session>2nd</session>
    <chamber>U.S. House of Representatives</chamber>
    <rollcall-num>123</rollcall-num>
    <legis-num>H R 1234</legis-num>
    <vote-question>On Passage</vote-question>
    <vote-type>YEA-AND-NAY</vote-type>
    <vote-result>Passed</vote-result>
    <action-date>15-Nov-2026</action-date>
    <vote-desc>To amend the thing.</vote-desc>
    <vote-totals>
      <totals-by-vote>
        <yea-total>218</yea-total>
        <nay-total>210</nay-total>
        <present-total>1</present-total>
        <not-voting-total>5</not-voting-total>
      </totals-by-vote>
    </vote-totals>
  </vote-metadata>
  <vote-data>
    <recorded-vote>
      <legislator name-id="A000374" party="R" state="LA">Mr. Abraham</legislator>
      <vote>Yea</vote>
    </recorded-vote>
    <recorded-vote>
      <legislator name-id="B000490" party="D" state="GA">Mr. Bishop</legislator>
      <vote>Nay</vote>
    </recorded-vote>
    <recorded-vote>
      <legislator name-id="" party="D" state="XX">No Id</legislator>
      <vote>Yea</vote>
    </recorded-vote>
  </vote-data>
</rollcall-vote>
"""

SENATE_VOTE_XML = b"""<?xml version="1.0"?>
<roll_call_vote>
  <congress>119</congress>
  <session>2</session>
  <vote_number>55</vote_number>
  <vote_date>November 15, 2026, 02:32 PM</vote_date>
  <vote_question_text>On the Amendment</vote_question_text>
  <vote_document_text>S.Amdt. 10 to S. 456</vote_document_text>
  <vote_result_text>Agreed to</vote_result_text>
  <count>
    <yeas>60</yeas>
    <nays>38</nays>
    <present>0</present>
    <absent>2</absent>
  </count>
  <members>
    <member>
      <member_full>Smith (R-TX)</member_full>
      <lis_member_id>S307</lis_member_id>
      <vote_cast>Yea</vote_cast>
    </member>
    <member>
      <member_full>Unmapped (D-ZZ)</member_full>
      <lis_member_id>S999</lis_member_id>
      <vote_cast>Nay</vote_cast>
    </member>
  </members>
</roll_call_vote>
"""


def test_normalize_position():
    assert fv.normalize_position("Yea") == "Yea"
    assert fv.normalize_position("aye") == "Yea"
    assert fv.normalize_position("Nay") == "Nay"
    assert fv.normalize_position("Not Voting") == "Not Voting"
    assert fv.normalize_position("") is None
    assert fv.normalize_position("Gibberish") is None


def test_normalize_bill_number_known_prefix():
    assert fv.normalize_bill_number("H R 1234") == "H.R. 1234"
    assert fv.normalize_bill_number("S J RES 45") == "S.J.Res. 45"


def test_normalize_bill_number_unknown_prefix_passes_through():
    assert fv.normalize_bill_number("Some Weird Thing") == "Some Weird Thing"
    assert fv.normalize_bill_number(None) is None


def test_current_congress_and_session():
    assert fv.current_congress_and_session(date(2025, 3, 1)) == (119, 1)
    assert fv.current_congress_and_session(date(2026, 11, 15)) == (119, 2)
    assert fv.current_congress_and_session(date(2027, 1, 1)) == (119, 2)
    assert fv.current_congress_and_session(date(2027, 1, 3)) == (120, 1)


def test_parse_house_vote():
    vote_row, member_rows = fv.parse_house_vote(HOUSE_VOTE_XML, congress=119, session=2)

    assert vote_row == {
        "congress": 119, "session": 2, "chamber": "House", "roll_number": 123,
        "date": "2026-11-15", "question": "On Passage", "description": "To amend the thing.",
        "bill_number": "H.R. 1234", "result": "Passed",
        "yea_count": 218, "nay_count": 210, "present_count": 1, "not_voting_count": 5,
    }
    # The third recorded-vote has no name-id and is dropped, not crashed on.
    assert member_rows == [
        {"congress": 119, "session": 2, "chamber": "House", "roll_number": 123,
         "member_id": "A000374", "position": "Yea"},
        {"congress": 119, "session": 2, "chamber": "House", "roll_number": 123,
         "member_id": "B000490", "position": "Nay"},
    ]


def test_parse_senate_vote():
    crosswalk = {"S307": "S000148"}  # S999 deliberately left unmapped
    vote_row, member_rows = fv.parse_senate_vote(SENATE_VOTE_XML, congress=119, session=2, lis_crosswalk=crosswalk)

    assert vote_row == {
        "congress": 119, "session": 2, "chamber": "Senate", "roll_number": 55,
        "date": "2026-11-15", "question": "On the Amendment",
        "description": "S.Amdt. 10 to S. 456", "bill_number": "S.Amdt. 10 to S. 456",
        "result": "Agreed to",
        "yea_count": 60, "nay_count": 38, "present_count": 0, "not_voting_count": 2,
    }
    assert member_rows == [
        {"congress": 119, "session": 2, "chamber": "Senate", "roll_number": 55,
         "member_id": "S000148", "position": "Yea"},
    ]


def test_highest_known_roll_defaults_to_zero(monkeypatch):
    monkeypatch.setattr(fv, "safe_supabase_select", lambda *a, **k: [])
    assert fv.highest_known_roll("House", 119, 2) == 0


def test_highest_known_roll_uses_latest_row(monkeypatch):
    monkeypatch.setattr(fv, "safe_supabase_select", lambda *a, **k: [{"roll_number": 77}])
    assert fv.highest_known_roll("House", 119, 2) == 77


def test_fetch_house_votes_stops_at_404(monkeypatch):
    class FakeResponse:
        def __init__(self, status_code, content=b""):
            self.status_code = status_code
            self.content = content
            self.ok = status_code == 200

    monkeypatch.setattr(fv, "highest_known_roll", lambda *a, **k: 0)

    responses = {1: FakeResponse(200, HOUSE_VOTE_XML), 2: FakeResponse(404)}
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        roll = len(calls)
        return responses.get(roll, FakeResponse(404))

    monkeypatch.setattr(fv.requests, "get", fake_get)
    vote_rows, member_rows = fv.fetch_house_votes(119, 2, 2026)

    assert len(calls) == 2  # fetched roll 1 (success), roll 2 (404), then stopped
    assert len(vote_rows) == 1
    assert len(member_rows) == 2
