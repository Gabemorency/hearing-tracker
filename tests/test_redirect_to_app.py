import redirect_to_app as r


def test_redirect_html_includes_target_url():
    html = r.redirect_html("/calendar")
    assert "https://web-beta-ten-88.vercel.app/calendar" in html
    assert "<title>" in html


def test_build_bio_redirects_basic_shape():
    members_data = {
        "senators": [{"bio_slug": "jane-doe", "bioguide_id": "D000001"}],
        "reps": [{"bio_slug": "john-smith", "bioguide_id": "S000002"}],
    }
    assert r.build_bio_redirects(members_data) == {
        "jane-doe": "D000001",
        "john-smith": "S000002",
    }


def test_build_bio_redirects_skips_missing_fields():
    members_data = {
        "senators": [
            {"bio_slug": "no-bioguide"},
            {"bioguide_id": "D000003"},
            {},
        ],
        "reps": [],
    }
    assert r.build_bio_redirects(members_data) == {}


def test_build_bio_redirects_empty_input():
    assert r.build_bio_redirects({}) == {}
