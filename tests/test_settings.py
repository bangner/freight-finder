import pytest

from app.settings import ConfigError, load_settings


def test_missing_sdk_key_fails_clearly(monkeypatch):
    monkeypatch.delenv("LAUNCHDARKLY_SDK_KEY", raising=False)
    with pytest.raises(ConfigError, match="LAUNCHDARKLY_SDK_KEY is not set"):
        load_settings()


def test_client_side_id_is_rejected(monkeypatch):
    monkeypatch.setenv("LAUNCHDARKLY_SDK_KEY", "65f1c0ffee0123456789abcd")
    with pytest.raises(ConfigError, match="server-side SDK key"):
        load_settings()


def test_model_key_is_optional(monkeypatch):
    monkeypatch.setenv("LAUNCHDARKLY_SDK_KEY", "sdk-abc")
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    assert load_settings().model_api_key is None
