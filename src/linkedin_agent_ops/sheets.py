from __future__ import annotations

import json
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from linkedin_agent_ops.agent_models import AgentHistoryItem, AgentResponse
from linkedin_agent_ops.agents.performance import (
    AnalyticsDataset,
    PerformanceResult,
    PostMetric,
)
from linkedin_agent_ops.models import DailyBrief
from linkedin_agent_ops.utils import canonicalize_url

ITEM_SHEET = "Brief Items"
RUN_SHEET = "Run Log"
AGENT_RUN_SHEET = "Agent Runs"
POST_METRICS_SHEET = "Post Metrics"
PERFORMANCE_SHEET = "Performance Analyses"

ITEM_HEADERS = [
    "Run ID",
    "Date PKT",
    "Source",
    "Category",
    "Title",
    "URL",
    "Published At",
    "Summary",
    "Post Angle",
    "Score",
    "Status",
    "Model",
    "Delivery Status",
]

RUN_HEADERS = [
    "Run ID",
    "Brief Date",
    "Started At",
    "Completed At",
    "Status",
    "Collector Counts",
    "Collector Errors",
    "Selected Count",
    "Model",
    "Email Status",
    "Sheets Status",
    "Error",
]

AGENT_RUN_HEADERS = [
    "Run ID",
    "Agent",
    "Created At",
    "Model",
    "Passed",
    "Warnings",
    "Summary",
    "Result JSON",
]

POST_METRICS_HEADERS = list(PostMetric.model_fields)

PERFORMANCE_HEADERS = [
    "Run ID",
    "Created At",
    "Model",
    "Posts",
    "Result JSON",
    "Computed JSON",
]


class GoogleSheetsStore:
    def __init__(
        self,
        *,
        spreadsheet_id: str,
        service_account_info: dict[str, Any],
        service=None,
    ) -> None:
        self.spreadsheet_id = spreadsheet_id
        if service is None:
            credentials = Credentials.from_service_account_info(
                service_account_info,
                scopes=["https://www.googleapis.com/auth/spreadsheets"],
            )
            service = build(
                "sheets",
                "v4",
                credentials=credentials,
                cache_discovery=False,
            )
        self.values = service.spreadsheets().values()
        self.spreadsheets = service.spreadsheets()
        self._ensure_structure()

    def _ensure_structure(self) -> None:
        metadata = self.spreadsheets.get(
            spreadsheetId=self.spreadsheet_id,
            fields="sheets.properties.title",
        ).execute()
        titles = {
            sheet["properties"]["title"] for sheet in metadata.get("sheets", [])
        }
        requests = [
            {"addSheet": {"properties": {"title": title}}}
            for title in (
                ITEM_SHEET,
                RUN_SHEET,
                AGENT_RUN_SHEET,
                POST_METRICS_SHEET,
                PERFORMANCE_SHEET,
            )
            if title not in titles
        ]
        if requests:
            self.spreadsheets.batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"requests": requests},
            ).execute()
        self._ensure_headers(ITEM_SHEET, ITEM_HEADERS)
        self._ensure_headers(RUN_SHEET, RUN_HEADERS)
        self._ensure_headers(AGENT_RUN_SHEET, AGENT_RUN_HEADERS)
        self._ensure_headers(POST_METRICS_SHEET, POST_METRICS_HEADERS)
        self._ensure_headers(PERFORMANCE_SHEET, PERFORMANCE_HEADERS)

    def _ensure_headers(self, sheet: str, headers: list[str]) -> None:
        response = self.values.get(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{sheet}'!1:1",
        ).execute()
        if response.get("values"):
            return
        self.values.update(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{sheet}'!A1",
            valueInputOption="RAW",
            body={"values": [headers]},
        ).execute()

    def is_completed(self, brief_date: str) -> bool:
        runs = self._rows(RUN_SHEET)
        for row in runs:
            if row.get("Brief Date") == brief_date and row.get("Status") == "success":
                return True
        items = [
            row for row in self._rows(ITEM_SHEET) if row.get("Date PKT") == brief_date
        ]
        return bool(items) and all(
            row.get("Delivery Status") == "sent" for row in items
        )

    def existing_urls(self, exclude_date: str | None = None) -> set[str]:
        return {
            canonicalize_url(row["URL"])
            for row in self._rows(ITEM_SHEET)
            if row.get("URL") and row.get("Date PKT") != exclude_date
        }

    def record_pending(self, run_id: str, brief: DailyBrief) -> None:
        raw = self.values.get(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{ITEM_SHEET}'!A:M",
        ).execute().get("values", [])
        existing = {}
        for row_number, row in enumerate(raw[1:], start=2):
            if len(row) > 5:
                existing[(row[1], canonicalize_url(row[5]))] = row_number

        append_rows = []
        update_rows = []
        for item in brief.all_items():
            values = [
                run_id,
                brief.brief_date.isoformat(),
                item.source_name,
                item.category,
                item.title,
                item.url,
                item.published_at.isoformat(),
                item.summary,
                item.post_angle,
                item.score,
                "New",
                brief.model_used,
                "pending",
            ]
            row_number = existing.get(
                (brief.brief_date.isoformat(), canonicalize_url(item.url))
            )
            if row_number:
                update_rows.append(
                    {
                        "range": f"'{ITEM_SHEET}'!A{row_number}:M{row_number}",
                        "values": [values],
                    }
                )
            else:
                append_rows.append(values)

        if update_rows:
            self.values.batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"valueInputOption": "RAW", "data": update_rows},
            ).execute()
        if append_rows:
            self.values.append(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{ITEM_SHEET}'!A:M",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": append_rows},
            ).execute()

    def mark_delivery(self, run_id: str, status: str) -> None:
        raw = self.values.get(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{ITEM_SHEET}'!A:M",
        ).execute().get("values", [])
        updates = []
        for row_number, row in enumerate(raw[1:], start=2):
            if row and row[0] == run_id:
                updates.append(
                    {
                        "range": f"'{ITEM_SHEET}'!M{row_number}",
                        "values": [[status]],
                    }
                )
        if updates:
            self.values.batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"valueInputOption": "RAW", "data": updates},
            ).execute()

    def record_run(self, values: list[object]) -> None:
        self.values.append(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{RUN_SHEET}'!A:L",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [[self._serialize(value) for value in values]]},
        ).execute()

    def record_agent_run(self, response: AgentResponse, summary: str) -> None:
        metadata = response.metadata
        warnings = sum(
            issue.severity.value in {"warning", "major", "critical"}
            for issue in metadata.validation.issues
        )
        result_json = response.result.model_dump_json()
        self._append(
            AGENT_RUN_SHEET,
            [
                metadata.run_id,
                metadata.agent,
                metadata.created_at.isoformat(),
                metadata.model_used,
                metadata.validation.passed,
                warnings,
                summary[:1000],
                result_json[:45000],
            ],
        )

    def history(self, limit: int = 50) -> list[AgentHistoryItem]:
        rows = self._rows(AGENT_RUN_SHEET)[-limit:]
        history = []
        for row in reversed(rows):
            result = None
            if row.get("Result JSON"):
                try:
                    result = json.loads(row["Result JSON"])
                except json.JSONDecodeError:
                    result = None
            history.append(
                AgentHistoryItem(
                    run_id=row["Run ID"],
                    agent=row["Agent"],
                    created_at=row["Created At"],
                    model_used=row["Model"],
                    passed=str(row["Passed"]).lower() == "true",
                    warnings=int(row.get("Warnings") or 0),
                    summary=row.get("Summary", ""),
                    result=result,
                )
            )
        return history

    def save_posts(self, posts: list[PostMetric]) -> None:
        existing = {
            row.get("post_id"): index
            for index, row in enumerate(
                self._rows(POST_METRICS_SHEET), start=2
            )
        }
        appends = []
        updates = []
        for post in posts:
            row = [
                self._serialize(post.model_dump(mode="json").get(field))
                for field in POST_METRICS_HEADERS
            ]
            row_number = existing.get(post.post_id)
            if row_number:
                end = _column_name(len(POST_METRICS_HEADERS))
                updates.append(
                    {
                        "range": f"'{POST_METRICS_SHEET}'!A{row_number}:{end}{row_number}",
                        "values": [row],
                    }
                )
            else:
                appends.append(row)
        if updates:
            self.values.batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"valueInputOption": "RAW", "data": updates},
            ).execute()
        if appends:
            self.values.append(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{POST_METRICS_SHEET}'!A:{_column_name(len(POST_METRICS_HEADERS))}",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": appends},
            ).execute()

    def load_posts(self) -> list[PostMetric]:
        posts = []
        optional_fields = {
            "posted_time",
            "golden_hour_comments",
            "replied_within_15min",
            "max_thread_depth",
            "were_you_online_gh",
        }
        for row in self._rows(POST_METRICS_SHEET):
            normalized = {
                key: (None if key in optional_fields and value == "" else value)
                for key, value in row.items()
            }
            posts.append(PostMetric.model_validate(normalized))
        return posts

    def save_performance_analysis(
        self,
        response: AgentResponse[PerformanceResult],
        dataset: AnalyticsDataset,
    ) -> None:
        self._append(
            PERFORMANCE_SHEET,
            [
                response.metadata.run_id,
                response.metadata.created_at.isoformat(),
                response.metadata.model_used,
                len(dataset.posts),
                response.result.model_dump_json()[:45000],
                dataset.model_dump_json()[:45000],
            ],
        )

    def _rows(self, sheet: str) -> list[dict[str, str]]:
        raw = self.values.get(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{sheet}'!A:Z",
        ).execute().get("values", [])
        if not raw:
            return []
        headers = raw[0]
        return [
            {header: row[index] if index < len(row) else "" for index, header in enumerate(headers)}
            for row in raw[1:]
        ]

    def _append(self, sheet: str, row: list[object]) -> None:
        self.values.append(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{sheet}'!A:Z",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [[self._serialize(value) for value in row]]},
        ).execute()

    @staticmethod
    def _serialize(value: object) -> object:
        if isinstance(value, (dict, list)):
            return json.dumps(value, sort_keys=True)
        if value is None:
            return ""
        return value


def _column_name(number: int) -> str:
    name = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        name = chr(65 + remainder) + name
    return name
