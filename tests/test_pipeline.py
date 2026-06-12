import json
from datetime import UTC, date, datetime
from pathlib import Path

from linkedin_agent_ops.llm import BriefGenerator
from linkedin_agent_ops.models import SourceItem
from linkedin_agent_ops.pipeline import DailyBriefPipeline


class FakeCollector:
    def __init__(self, name, items):
        self.name = name
        self.items = items

    def collect(self, as_of):
        return self.items


class FakeStore:
    def __init__(self):
        self.completed = False
        self.rows = []
        self.delivery = {}

    def is_completed(self, brief_date):
        return self.completed

    def existing_urls(self, exclude_date=None):
        return {
            item.url for row_date, item in self.rows if row_date != exclude_date
        }

    def record_pending(self, run_id, brief):
        new_items = {
            (brief.brief_date.isoformat(), item.url): (
                brief.brief_date.isoformat(),
                item,
            )
            for item in brief.all_items()
        }
        existing = {
            (row_date, item.url): (row_date, item) for row_date, item in self.rows
        }
        existing.update(new_items)
        self.rows = list(existing.values())

    def mark_delivery(self, run_id, status):
        self.delivery[run_id] = status

    def record_run(self, values):
        if values[4] == "success":
            self.completed = True


class FakeEmail:
    def __init__(self):
        self.calls = 0

    def send(self, brief, text_body, html_body):
        self.calls += 1


def fixture_items():
    path = Path(__file__).parent / "fixtures" / "source_items.json"
    return [SourceItem.model_validate(item) for item in json.loads(path.read_text())]


def config():
    return {
        "brief": {
            "minimum_successful_collectors": 2,
            "minimum_candidates": 5,
            "paper_count": 3,
            "trend_count": 3,
            "repository_count": 3,
        },
        "topics": {"keywords": ["computer vision", "agent", "mlops", "rag"]},
        "ranking": {
            "recency_weight": 30,
            "relevance_weight": 35,
            "source_quality_weight": 20,
            "engagement_weight": 15,
        },
    }


def build_pipeline(store=None, email=None):
    items = fixture_items()
    collectors = [
        FakeCollector(source, [item for item in items if item.source.value == source])
        for source in ("arxiv", "hacker_news", "github", "rss")
    ]
    def clock():
        return datetime(2026, 6, 12, 2, 30, tzinfo=UTC)

    return DailyBriefPipeline(
        collectors=collectors,
        generator=BriefGenerator([], now_fn=clock),
        config=config(),
        now_fn=clock,
        store=store,
        email_sender=email,
    )


def test_dry_run_renders_without_delivery():
    result, text, html = build_pipeline().run(
        brief_date=date(2026, 6, 12),
        as_of=datetime(2026, 6, 12, 2, 30, tzinfo=UTC),
        dry_run=True,
    )
    assert result.status == "dry_run"
    assert "DAILY AI BRIEF" in text
    assert "<html>" in html


def test_delivery_is_idempotent_and_force_send_overrides():
    store = FakeStore()
    email = FakeEmail()
    pipeline = build_pipeline(store, email)
    arguments = {
        "brief_date": date(2026, 6, 12),
        "as_of": datetime(2026, 6, 12, 2, 30, tzinfo=UTC),
    }

    first, _, _ = pipeline.run(**arguments)
    second, _, _ = pipeline.run(**arguments)
    forced, _, _ = pipeline.run(**arguments, force_send=True)

    assert first.status == "success"
    assert second.status == "skipped"
    assert forced.status == "success"
    assert email.calls == 2
