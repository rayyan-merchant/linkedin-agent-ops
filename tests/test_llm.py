import json
from datetime import UTC, date, datetime

from linkedin_agent_ops.llm import BriefGenerator
from linkedin_agent_ops.models import SourceItem, SourceKind


class FailedProvider:
    name = "failed"

    def generate(self, prompt, schema):
        raise RuntimeError("unavailable")


class GoodProvider:
    name = "good"

    def generate(self, prompt, schema):
        candidates = json.loads(prompt.split("Candidates:\n", 1)[1])
        return {
            "items": [
                {
                    "source_id": item["source_id"],
                    "summary": f"A factual summary for {item['title']}.",
                    "post_angle": "Explain what a production team should validate first.",
                }
                for item in candidates
            ],
            "opportunity": {
                "title": "Compare research with production evidence",
                "rationale": "The selected items expose a useful implementation gap.",
                "post_angle": "Show which claims need testing before adoption.",
                "source_ids": [candidates[0]["source_id"]],
            },
        }


def source_item():
    return SourceItem(
        source_id="paper-1",
        source=SourceKind.ARXIV,
        source_name="arXiv",
        title="A useful vision paper",
        url="https://arxiv.org/abs/1",
        published_at=datetime(2026, 6, 11, tzinfo=UTC),
        excerpt="The paper reports a practical computer vision method.",
        category="cs.CV",
        score=80,
    )


def test_generator_falls_back_to_second_provider():
    generator = BriefGenerator(
        [FailedProvider(), GoodProvider()],
        now_fn=lambda: datetime(2026, 6, 12, tzinfo=UTC),
    )
    brief = generator.generate(
        items=[source_item()],
        brief_date=date(2026, 6, 12),
        counts=(1, 0, 0),
    )
    assert brief.model_used == "good"
    assert brief.papers[0].summary.startswith("A factual summary")


def test_generator_uses_deterministic_fallback():
    generator = BriefGenerator(
        [FailedProvider()],
        now_fn=lambda: datetime(2026, 6, 12, tzinfo=UTC),
    )
    brief = generator.generate(
        items=[source_item()],
        brief_date=date(2026, 6, 12),
        counts=(1, 0, 0),
    )
    assert brief.model_used == "deterministic"
    assert brief.degraded is True

