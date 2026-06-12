from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from linkedin_agent_ops.models import DailyBrief, SourceItem


class Collector(Protocol):
    name: str

    def collect(self, as_of: datetime) -> list[SourceItem]: ...


class BriefGenerator(Protocol):
    def generate(
        self,
        *,
        items: list[SourceItem],
        brief_date: date,
        counts: tuple[int, int, int],
    ) -> DailyBrief: ...


class EmailSender(Protocol):
    def send(self, brief: DailyBrief, text_body: str, html_body: str) -> None: ...


class BriefStore(Protocol):
    def is_completed(self, brief_date: str) -> bool: ...

    def existing_urls(self, exclude_date: str | None = None) -> set[str]: ...

    def record_pending(self, run_id: str, brief: DailyBrief) -> None: ...

    def mark_delivery(self, run_id: str, status: str) -> None: ...

    def record_run(self, values: list[object]) -> None: ...
