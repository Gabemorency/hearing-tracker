import io
import zipfile
from datetime import date

import shapefile

import fetch_district_shapes as fds


def _build_test_zip(tmp_path):
    base = str(tmp_path / "cb_test_cd119_500k")
    w = shapefile.Writer(base, shapeType=shapefile.POLYGON)
    w.field("STATEFP", "C", 2)
    w.field("CD119FP", "C", 2)
    w.poly([[[-80.0, 40.0], [-80.0, 41.0], [-79.0, 41.0], [-80.0, 40.0]]])
    w.record("36", "01")
    w.close()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for ext in ("shp", "dbf", "shx"):
            zf.write(f"{base}.{ext}", arcname=f"cb_test_cd119_500k.{ext}")
    return buf.getvalue()


def test_shapes_from_zip_reads_real_shapefile_bundle(tmp_path):
    zip_bytes = _build_test_zip(tmp_path)
    shape_records = fds.shapes_from_zip(zip_bytes)
    assert len(shape_records) == 1
    rec = shape_records[0].record.as_dict()
    assert rec == {"STATEFP": "36", "CD119FP": "01"}
    assert shape_records[0].shape.__geo_interface__["type"] == "Polygon"


def test_find_latest_zip_tries_years_descending_until_one_resolves(monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, ok, content):
            self.ok = ok
            self.content = content

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        if "GENZ2024" in url:
            return FakeResponse(True, b"PK\x03\x04fakezipcontent")
        return FakeResponse(False, b"")

    monkeypatch.setattr(fds.requests, "get", fake_get)
    year, content = fds.find_latest_zip("cb_{year}_us_cd119_500k.zip", [2025, 2024, 2023])
    assert year == 2024
    assert content == b"PK\x03\x04fakezipcontent"
    assert len(calls) == 2  # stopped after finding 2024, never tried 2023


def test_find_latest_zip_returns_none_when_nothing_resolves(monkeypatch):
    class FakeResponse:
        ok = False
        content = b""

    monkeypatch.setattr(fds.requests, "get", lambda *a, **k: FakeResponse())
    year, content = fds.find_latest_zip("cb_{year}_us_cd119_500k.zip", [2025, 2024])
    assert year is None
    assert content is None


def test_current_congress_matches_known_dates():
    assert fds.current_congress(date(2025, 1, 2)) == 118
    assert fds.current_congress(date(2025, 1, 3)) == 119
    assert fds.current_congress(date(2026, 11, 15)) == 119
    assert fds.current_congress(date(2027, 1, 2)) == 119
    assert fds.current_congress(date(2027, 1, 3)) == 120


def test_normalize_district_strips_leading_zeros():
    assert fds.normalize_district("00") == "0"
    assert fds.normalize_district("01") == "1"
    assert fds.normalize_district("12") == "12"


def test_state_abbrev_prefers_stusps():
    assert fds.state_abbrev({"STUSPS": "NY", "STATEFP": "36"}) == "NY"


def test_state_abbrev_falls_back_to_fips_crosswalk():
    assert fds.state_abbrev({"STATEFP": "36"}) == "NY"
    assert fds.state_abbrev({"STATEFP": "02"}) == "AK"


def test_state_abbrev_unknown_fips_returns_none():
    assert fds.state_abbrev({"STATEFP": "99"}) is None


def test_build_district_rows_skips_unmatched_state_and_missing_cd_field():
    records = [
        _fake_shape_record({"STATEFP": "36", "CD119FP": "01"}, {"type": "Polygon", "coordinates": []}),
        _fake_shape_record({"STATEFP": "99", "CD119FP": "01"}, {"type": "Polygon", "coordinates": []}),
        _fake_shape_record({"STATEFP": "36"}, {"type": "Polygon", "coordinates": []}),
    ]
    rows = fds.build_district_rows(records, congress=119, cd_field="CD119FP")
    assert rows == [
        {"congress": 119, "state": "NY", "district": "1", "geometry": {"type": "Polygon", "coordinates": []}},
    ]


def test_build_state_rows_uses_empty_district():
    records = [_fake_shape_record({"STUSPS": "VT"}, {"type": "Polygon", "coordinates": []})]
    rows = fds.build_state_rows(records, congress=119)
    assert rows == [
        {"congress": 119, "state": "VT", "district": "", "geometry": {"type": "Polygon", "coordinates": []}},
    ]


class _FakeRecord:
    def __init__(self, fields):
        self._fields = fields

    def as_dict(self):
        return self._fields


class _FakeShape:
    def __init__(self, geo):
        self.__geo_interface__ = geo


class _FakeShapeRecord:
    def __init__(self, fields, geo):
        self.record = _FakeRecord(fields)
        self.shape = _FakeShape(geo)


def _fake_shape_record(fields, geo):
    return _FakeShapeRecord(fields, geo)
