import pytest

from linkedin_agent_ops.config import AppSettings


def test_missing_runtime_secrets_are_reported():
    settings = AppSettings(config={})
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        settings.validate_delivery()


def test_service_account_json_is_validated():
    settings = AppSettings(config={}, google_service_account_json="not-json")
    with pytest.raises(ValueError, match="not valid JSON"):
        settings.service_account_info()


def test_settings_load_local_dotenv(tmp_path, monkeypatch):
    config = tmp_path / "settings.toml"
    config.write_text("[brief]\ntimezone = \"Asia/Karachi\"\n", encoding="utf-8")
    (tmp_path / ".env").write_text("GEMINI_API_KEY=local-key\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    settings = AppSettings.from_env(config)

    assert settings.gemini_api_key == "local-key"
