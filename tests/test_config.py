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

