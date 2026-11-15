import supabase_client as sc


def test_supabase_env_missing_returns_none_none(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    assert sc.supabase_env() == (None, None)


def test_supabase_env_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co/")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")
    base_url, service_key = sc.supabase_env()
    assert base_url == "https://example.supabase.co"
    assert service_key == "secret"


def test_safe_supabase_upsert_noop_without_env(monkeypatch, capsys):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    # Must not raise, and must not attempt a network call.
    sc.safe_supabase_upsert("hearings", [{"a": 1}], "a")
    assert "skipping hearings upsert" in capsys.readouterr().out


def test_safe_supabase_patch_noop_without_env(monkeypatch, capsys):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    sc.safe_supabase_patch("members", "is_current=eq.true", {"is_current": False})
    assert "skipping members patch" in capsys.readouterr().out


def test_safe_supabase_delete_noop_without_env(monkeypatch, capsys):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    sc.safe_supabase_delete("committee_memberships", "id=gt.0")
    assert "skipping committee_memberships delete" in capsys.readouterr().out


def test_safe_supabase_delete_swallows_request_errors(monkeypatch, capsys):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")

    def boom(*args, **kwargs):
        raise RuntimeError("network is down")

    monkeypatch.setattr(sc.requests, "delete", boom)
    sc.safe_supabase_delete("committee_memberships", "id=gt.0")
    assert "WARNING" in capsys.readouterr().out


def test_supabase_upsert_respects_custom_chunk_size(monkeypatch):
    calls = []

    class FakeResponse:
        ok = True

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        return FakeResponse()

    monkeypatch.setattr(sc.requests, "post", fake_post)
    rows = [{"n": i} for i in range(130)]
    sc.supabase_upsert("https://example.supabase.co", "secret", "district_shapes", rows, "id", chunk_size=50)

    assert len(calls) == 3  # 50 + 50 + 30
    assert [len(c) for c in calls] == [50, 50, 30]


def test_safe_supabase_upsert_default_chunk_size_unchanged(monkeypatch):
    calls = []

    class FakeResponse:
        ok = True

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        return FakeResponse()

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")
    monkeypatch.setattr(sc.requests, "post", fake_post)
    rows = [{"n": i} for i in range(600)]
    sc.safe_supabase_upsert("hearings", rows, "id")

    assert len(calls) == 2  # default chunk_size=500: 500 + 100
    assert [len(c) for c in calls] == [500, 100]


def test_safe_supabase_select_noop_without_env(monkeypatch, capsys):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    assert sc.safe_supabase_select("votes", {"select": "roll_number"}) == []
    assert "skipping votes select" in capsys.readouterr().out


def test_safe_supabase_select_returns_parsed_json(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")

    class FakeResponse:
        ok = True

        def json(self):
            return [{"roll_number": 42}]

    monkeypatch.setattr(sc.requests, "get", lambda *a, **k: FakeResponse())
    rows = sc.safe_supabase_select("votes", {"select": "roll_number"})
    assert rows == [{"roll_number": 42}]


def test_safe_supabase_select_swallows_request_errors(monkeypatch, capsys):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")

    def boom(*args, **kwargs):
        raise RuntimeError("network is down")

    monkeypatch.setattr(sc.requests, "get", boom)
    assert sc.safe_supabase_select("votes", {"select": "roll_number"}) == []
    assert "WARNING" in capsys.readouterr().out


def test_safe_supabase_upsert_swallows_request_errors(monkeypatch, capsys):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")

    def boom(*args, **kwargs):
        raise RuntimeError("network is down")

    monkeypatch.setattr(sc.requests, "post", boom)
    # Must not raise even though the underlying request blows up.
    sc.safe_supabase_upsert("hearings", [{"a": 1}], "a")
    assert "WARNING" in capsys.readouterr().out
