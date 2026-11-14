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


def test_safe_supabase_upsert_swallows_request_errors(monkeypatch, capsys):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "secret")

    def boom(*args, **kwargs):
        raise RuntimeError("network is down")

    monkeypatch.setattr(sc.requests, "post", boom)
    # Must not raise even though the underlying request blows up.
    sc.safe_supabase_upsert("hearings", [{"a": 1}], "a")
    assert "WARNING" in capsys.readouterr().out
