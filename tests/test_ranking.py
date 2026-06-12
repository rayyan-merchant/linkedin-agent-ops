from datetime import UTC, datetime

from linkedin_agent_ops.models import SourceItem, SourceKind
from linkedin_agent_ops.ranking import deduplicate, score_items, select_candidates


def item(source_id: str, source: SourceKind, url: str, title: str) -> SourceItem:
    return SourceItem(
        source_id=source_id,
        source=source,
        source_name=source.value,
        title=title,
        url=url,
        published_at=datetime(2026, 6, 11, tzinfo=UTC),
        excerpt="computer vision ai deployment",
    )


def test_deduplicate_uses_canonical_url_and_keeps_newer_item():
    older = item("1", SourceKind.RSS, "https://example.com/a?utm_source=x", "Old")
    newer = item("2", SourceKind.RSS, "https://example.com/a", "New").model_copy(
        update={"published_at": datetime(2026, 6, 12, tzinfo=UTC)}
    )
    assert deduplicate([older, newer]) == [newer]


def test_score_and_select_balance_sections():
    items = [
        item("paper", SourceKind.ARXIV, "https://arxiv.org/abs/1", "Vision paper"),
        item("trend", SourceKind.HACKER_NEWS, "https://example.com/t", "AI trend"),
        item("repo", SourceKind.GITHUB, "https://github.com/a/b", "Agent repo"),
    ]
    ranked = score_items(
        items,
        as_of=datetime(2026, 6, 12, tzinfo=UTC),
        keywords=["computer vision", "ai deployment"],
        weights={
            "recency_weight": 30,
            "relevance_weight": 35,
            "source_quality_weight": 20,
            "engagement_weight": 15,
        },
    )
    selected = select_candidates(
        ranked, paper_count=1, trend_count=1, repository_count=1
    )
    assert {entry.source_id for entry in selected} == {"paper", "trend", "repo"}

