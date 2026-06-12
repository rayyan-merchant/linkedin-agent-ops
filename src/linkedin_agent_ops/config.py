from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AppSettings:
    config: dict[str, Any]
    gemini_api_key: str = ""
    groq_api_key: str = ""
    github_token: str = ""
    gmail_username: str = ""
    gmail_app_password: str = ""
    email_to: str = ""
    email_from_name: str = "Daily AI Brief"
    google_service_account_json: str = ""
    google_sheet_id: str = ""

    @classmethod
    def from_env(cls, config_path: str | Path | None = None) -> AppSettings:
        path = Path(
            config_path or os.getenv("BRIEF_CONFIG_PATH", "config/settings.toml")
        )
        with path.open("rb") as config_file:
            config = tomllib.load(config_file)
        return cls(
            config=config,
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            groq_api_key=os.getenv("GROQ_API_KEY", ""),
            github_token=os.getenv("GITHUB_TOKEN", ""),
            gmail_username=os.getenv("GMAIL_USERNAME", ""),
            gmail_app_password=os.getenv("GMAIL_APP_PASSWORD", ""),
            email_to=os.getenv("EMAIL_TO", ""),
            email_from_name=os.getenv("EMAIL_FROM_NAME", "Daily AI Brief"),
            google_service_account_json=os.getenv(
                "GOOGLE_SERVICE_ACCOUNT_JSON", ""
            ),
            google_sheet_id=os.getenv("GOOGLE_SHEET_ID", ""),
        )

    def validate_delivery(self) -> None:
        required = {
            "GEMINI_API_KEY": self.gemini_api_key,
            "GROQ_API_KEY": self.groq_api_key,
            "GMAIL_USERNAME": self.gmail_username,
            "GMAIL_APP_PASSWORD": self.gmail_app_password,
            "EMAIL_TO": self.email_to,
            "GOOGLE_SERVICE_ACCOUNT_JSON": self.google_service_account_json,
            "GOOGLE_SHEET_ID": self.google_sheet_id,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"Missing required secrets: {', '.join(missing)}")
        self.service_account_info()

    def service_account_info(self) -> dict[str, Any]:
        if not self.google_service_account_json:
            return {}
        try:
            value = json.loads(self.google_service_account_json)
        except json.JSONDecodeError as exc:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON must contain an object")
        return value
