"""
Smoke tests for the bill-URL fix in fetch_domewatch.py. DomeWatch's own
billUrl (e.g. "https://www.congress.gov/bill/hr-8884") loads but lands on a
search/fallback page instead of the bill — these build the real path.
"""
import fetch_domewatch as fd


def test_house_bill():
    assert fd.congress_gov_bill_url("H.R. 8884") == \
        "https://www.congress.gov/bill/119th-congress/house-bill/8884"


def test_senate_bill():
    assert fd.congress_gov_bill_url("S. 1383") == \
        "https://www.congress.gov/bill/119th-congress/senate-bill/1383"


def test_house_concurrent_resolution():
    assert fd.congress_gov_bill_url("H.Con.Res. 89") == \
        "https://www.congress.gov/bill/119th-congress/house-concurrent-resolution/89"


def test_senate_concurrent_resolution():
    assert fd.congress_gov_bill_url("S.Con.Res. 2") == \
        "https://www.congress.gov/bill/119th-congress/senate-concurrent-resolution/2"


def test_house_resolution():
    assert fd.congress_gov_bill_url("H.Res. 12") == \
        "https://www.congress.gov/bill/119th-congress/house-resolution/12"


def test_senate_resolution():
    assert fd.congress_gov_bill_url("S.Res. 5") == \
        "https://www.congress.gov/bill/119th-congress/senate-resolution/5"


def test_house_joint_resolution():
    assert fd.congress_gov_bill_url("H.J.Res. 4") == \
        "https://www.congress.gov/bill/119th-congress/house-joint-resolution/4"


def test_senate_joint_resolution():
    assert fd.congress_gov_bill_url("S.J.Res. 3") == \
        "https://www.congress.gov/bill/119th-congress/senate-joint-resolution/3"


def test_unparseable_falls_back():
    assert fd.congress_gov_bill_url("garbage", fallback="KEEP") == "KEEP"


def test_empty_falls_back():
    assert fd.congress_gov_bill_url("", fallback="KEEP") == "KEEP"
    assert fd.congress_gov_bill_url(None, fallback="KEEP") == "KEEP"


def test_fix_whip_bill_urls_rewrites_in_place():
    data = {
        "data": [
            {"items": [{"billNumber": "H.R. 8884", "billUrl": "https://www.congress.gov/bill/hr-8884"}]}
        ]
    }
    fixed = fd.fix_whip_bill_urls(data)
    assert fixed["data"][0]["items"][0]["billUrl"] == \
        "https://www.congress.gov/bill/119th-congress/house-bill/8884"


def test_fix_whip_bill_urls_handles_none():
    assert fd.fix_whip_bill_urls(None) is None
