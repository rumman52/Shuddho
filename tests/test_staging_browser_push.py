from __future__ import annotations

from scripts import staging_browser_push as probe


def test_guard_requires_explicit_controlled_staging(monkeypatch):
    monkeypatch.delenv("SHUDDHO_STAGING_ALLOW_BROWSER_PUSH", raising=False)
    monkeypatch.delenv("SHUDDHO_STAGING_SYNTHETIC_ACCOUNT", raising=False)
    try:
        probe.require_guard()
    except probe.BrowserPushProbeFailure as error:
        assert "SHUDDHO_STAGING_ALLOW_BROWSER_PUSH" in str(error)
    else:
        raise AssertionError("guard should fail closed")


def test_https_origin_rejects_credentials_and_paths():
    assert probe.require_https_base("https://staging.example.test") == "https://staging.example.test"
    for value in (
        "http://staging.example.test",
        "https://user:pass@staging.example.test",
        "https://staging.example.test?x=1",
    ):
        try:
            probe.require_https_base(value)
        except probe.BrowserPushProbeFailure:
            pass
        else:
            raise AssertionError(value)
