from datetime import UTC, date, datetime

from linkedin_agent_ops.formatter import render_html
from linkedin_agent_ops.models import (
    BriefItem,
    BriefSection,
    ContentOpportunity,
    DailyBrief,
    SourceKind,
)


def test_colorful_email_template_contains_personalized_sections_and_escapes_content():
    item = BriefItem(
        source_id="paper-1",
        section=BriefSection.PAPERS,
        source=SourceKind.ARXIV,
        source_name="arXiv",
        category="cs.CV",
        title="Vision <script>alert(1)</script>",
        url="https://example.com/?a=1&b=2",
        published_at=datetime(2026, 6, 12, tzinfo=UTC),
        summary="A practical vision result.",
        post_angle="Compare the reported tradeoff with deployment constraints.",
        score=82.4,
    )
    brief = DailyBrief(
        brief_date=date(2026, 6, 12),
        generated_at=datetime(2026, 6, 12, tzinfo=UTC),
        papers=[item],
        trends=[],
        repositories=[],
        opportunity=ContentOpportunity(
            title="Connect research to deployment",
            rationale="The implementation tradeoff is useful.",
            post_angle="Show what a production team should validate.",
            source_urls=[item.url],
        ),
        model_used="gemini:test",
    )

    html = render_html(brief)

    assert "RAYYAN'S MORNING INTELLIGENCE" in html
    assert "Papers worth your attention" in html
    assert "TODAY'S CONTENT OPPORTUNITY" in html
    assert "82/100" in html
    assert "Source 1" in html
    assert "Source {index}" not in html
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "role=\"presentation\"" in html
