from __future__ import annotations

import logging
from datetime import date, datetime
from uuid import uuid4

from linkedin_agent_ops.formatter import render_html, render_text
from linkedin_agent_ops.models import RunResult, SourceItem
from linkedin_agent_ops.protocols import (
    BriefGenerator,
    BriefStore,
    Collector,
    EmailSender,
)
from linkedin_agent_ops.ranking import (
    deduplicate,
    score_items,
    select_candidates,
)
from linkedin_agent_ops.utils import canonicalize_url

LOGGER = logging.getLogger(__name__)


class DailyBriefPipeline:
    def __init__(
        self,
        *,
        collectors: list[Collector],
        generator: BriefGenerator,
        config: dict,
        now_fn,
        store: BriefStore | None = None,
        email_sender: EmailSender | None = None,
    ) -> None:
        self.collectors = collectors
        self.generator = generator
        self.config = config
        self.now_fn = now_fn
        self.store = store
        self.email_sender = email_sender

    def run(
        self,
        *,
        brief_date: date,
        as_of: datetime,
        dry_run: bool = False,
        force_send: bool = False,
    ) -> tuple[RunResult, str, str]:
        run_id = f"{brief_date.isoformat()}-{uuid4().hex[:10]}"
        started_at = self.now_fn()
        result = RunResult(
            run_id=run_id,
            brief_date=brief_date,
            started_at=started_at,
            status="running",
        )

        if self.store and self.store.is_completed(brief_date.isoformat()) and not force_send:
            return (
                result.model_copy(
                    update={
                        "status": "skipped",
                        "completed_at": self.now_fn(),
                        "sheets_status": "already_completed",
                    }
                ),
                "",
                "",
            )

        items: list[SourceItem] = []
        for collector in self.collectors:
            try:
                collected = collector.collect(as_of)
                result.collector_counts[collector.name] = len(collected)
                items.extend(collected)
            except Exception as exc:
                LOGGER.exception("Collector %s failed", collector.name)
                result.collector_errors[collector.name] = str(exc)
                result.collector_counts[collector.name] = 0

        successful_collectors = sum(
            count > 0 for count in result.collector_counts.values()
        )
        minimum_collectors = self.config["brief"]["minimum_successful_collectors"]
        if successful_collectors < minimum_collectors:
            return self._failed(
                result,
                f"Only {successful_collectors} collectors returned items; "
                f"{minimum_collectors} required",
            )

        existing_urls = (
            self.store.existing_urls(
                exclude_date=brief_date.isoformat() if force_send else None
            )
            if self.store
            else set()
        )
        available = [
            item
            for item in deduplicate(items)
            if canonicalize_url(item.url) not in existing_urls
        ]
        minimum_candidates = self.config["brief"]["minimum_candidates"]
        if len(available) < minimum_candidates:
            return self._failed(
                result,
                f"Only {len(available)} new candidates available; "
                f"{minimum_candidates} required",
            )

        ranked = score_items(
            available,
            as_of=as_of,
            keywords=self.config["topics"]["keywords"],
            weights=self.config["ranking"],
        )
        counts = (
            self.config["brief"]["paper_count"],
            self.config["brief"]["trend_count"],
            self.config["brief"]["repository_count"],
        )
        selected = select_candidates(
            ranked,
            paper_count=counts[0],
            trend_count=counts[1],
            repository_count=counts[2],
        )
        brief = self.generator.generate(
            items=selected,
            brief_date=brief_date,
            counts=counts,
        )
        text_body = render_text(brief)
        html_body = render_html(brief)
        result.selected_count = len(selected)
        result.model_used = brief.model_used

        if dry_run:
            return (
                result.model_copy(
                    update={
                        "status": "dry_run",
                        "completed_at": self.now_fn(),
                        "email_status": "skipped",
                        "sheets_status": "skipped",
                    }
                ),
                text_body,
                html_body,
            )

        if self.store is None or self.email_sender is None:
            return self._failed(result, "Delivery services are not configured")

        try:
            self.store.record_pending(run_id, brief)
            result.sheets_status = "pending_recorded"
            self.email_sender.send(brief, text_body, html_body)
            result.email_status = "sent"
            self.store.mark_delivery(run_id, "sent")
            result.sheets_status = "sent_recorded"
            result.status = "success"
            result.completed_at = self.now_fn()
            self._record_run(result)
            return result, text_body, html_body
        except Exception as exc:
            LOGGER.exception("Delivery failed")
            result.error = str(exc)
            result.status = "failed"
            result.completed_at = self.now_fn()
            if result.email_status != "sent":
                result.email_status = "failed"
            try:
                self.store.mark_delivery(run_id, result.email_status)
                self._record_run(result)
            except Exception:
                LOGGER.exception("Could not record failed run")
            return result, text_body, html_body

    def _failed(self, result: RunResult, error: str) -> tuple[RunResult, str, str]:
        failed = result.model_copy(
            update={
                "status": "failed",
                "completed_at": self.now_fn(),
                "error": error,
            }
        )
        if self.store:
            try:
                self._record_run(failed)
            except Exception:
                LOGGER.exception("Could not record failed run")
        return failed, "", ""

    def _record_run(self, result: RunResult) -> None:
        if self.store is None:
            return
        self.store.record_run(
            [
                result.run_id,
                result.brief_date.isoformat(),
                result.started_at.isoformat(),
                result.completed_at.isoformat() if result.completed_at else "",
                result.status,
                result.collector_counts,
                result.collector_errors,
                result.selected_count,
                result.model_used,
                result.email_status,
                result.sheets_status,
                result.error,
            ]
        )
