from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from linkedin_agent_ops.collectors import (
    ArxivCollector,
    GitHubCollector,
    HackerNewsCollector,
    RssCollector,
)
from linkedin_agent_ops.config import AppSettings
from linkedin_agent_ops.email_delivery import GmailSender
from linkedin_agent_ops.llm import (
    BriefGenerator,
    GeminiProvider,
    GroqProvider,
)
from linkedin_agent_ops.models import SourceItem, SourceKind
from linkedin_agent_ops.pipeline import DailyBriefPipeline
from linkedin_agent_ops.sheets import GoogleSheetsStore
from linkedin_agent_ops.utils import utc_now

LOGGER = logging.getLogger(__name__)


class FixtureCollector:
    def __init__(self, name: str, items: list[SourceItem]) -> None:
        self.name = name
        self.items = items

    def collect(self, as_of: datetime) -> list[SourceItem]:
        return self.items


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the daily AI brief.")
    parser.add_argument("--date", type=date.fromisoformat, help="Brief date (YYYY-MM-DD).")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render the brief without writing to Sheets or sending email.",
    )
    parser.add_argument(
        "--force-send",
        action="store_true",
        help="Send even when the date is already marked complete.",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        help="Load SourceItem JSON for an offline fixture-backed run.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to the TOML configuration file.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = parse_args(argv)
    settings = AppSettings.from_env(args.config)
    timezone = ZoneInfo(settings.config["brief"]["timezone"])
    local_now = datetime.now(timezone)
    brief_date = args.date or local_now.date()
    if args.date:
        as_of = datetime.combine(args.date, time(7, 30), tzinfo=timezone).astimezone(UTC)
    else:
        as_of = local_now.astimezone(UTC)

    if not args.dry_run:
        settings.validate_delivery()

    with httpx.Client(
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
        headers={"User-Agent": "linkedin-agent-ops/0.1 (daily research brief)"},
    ) as client:
        collectors = _build_collectors(settings, client, args.fixture)
        providers = []
        if settings.gemini_api_key:
            providers.append(
                GeminiProvider(
                    client,
                    settings.gemini_api_key,
                    settings.config["models"]["gemini"],
                )
            )
        if settings.groq_api_key:
            providers.append(
                GroqProvider(
                    client,
                    settings.groq_api_key,
                    settings.config["models"]["groq"],
                )
            )
        generator = BriefGenerator(providers, now_fn=utc_now)

        store = None
        sender = None
        if not args.dry_run:
            store = GoogleSheetsStore(
                spreadsheet_id=settings.google_sheet_id,
                service_account_info=settings.service_account_info(),
            )
            sender = GmailSender(
                username=settings.gmail_username,
                app_password=settings.gmail_app_password,
                recipient=settings.email_to,
                sender_name=settings.email_from_name,
            )

        pipeline = DailyBriefPipeline(
            collectors=collectors,
            generator=generator,
            config=settings.config,
            now_fn=utc_now,
            store=store,
            email_sender=sender,
        )
        result, text_body, _ = pipeline.run(
            brief_date=brief_date,
            as_of=as_of,
            dry_run=args.dry_run,
            force_send=args.force_send,
        )

    if text_body:
        print(text_body)
    print(result.model_dump_json(indent=2))
    return 0 if result.status in {"success", "dry_run", "skipped"} else 1


def _build_collectors(
    settings: AppSettings,
    client: httpx.Client,
    fixture: Path | None,
):
    if fixture:
        raw_items = json.loads(fixture.read_text(encoding="utf-8"))
        items = [SourceItem.model_validate(item) for item in raw_items]
        return [
            FixtureCollector(
                source.value,
                [item for item in items if item.source == source],
            )
            for source in SourceKind
        ]

    config = settings.config
    return [
        ArxivCollector(
            client,
            lookback_hours=config["lookback_hours"]["arxiv"],
        ),
        HackerNewsCollector(
            client,
            lookback_hours=config["lookback_hours"]["hacker_news"],
        ),
        GitHubCollector(
            client,
            token=settings.github_token,
            queries=config["github"]["queries"],
            lookback_days=config["lookback_hours"]["github_days"],
            minimum_stars=config["github"]["minimum_stars"],
        ),
        RssCollector(
            client,
            feeds=config["rss"]["feeds"],
            lookback_hours=config["lookback_hours"]["rss"],
        ),
    ]


if __name__ == "__main__":
    sys.exit(main())

