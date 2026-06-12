from __future__ import annotations

from html import escape

from linkedin_agent_ops.models import BriefItem, DailyBrief


def render_text(brief: DailyBrief) -> str:
    lines = [
        f"DAILY AI BRIEF - {brief.brief_date.strftime('%B %d, %Y')}",
        f"Generated with: {brief.model_used}",
    ]
    if brief.degraded:
        lines.append("Note: This is a reduced brief because one or more inputs failed.")

    sections = (
        ("PAPERS WORTH YOUR ATTENTION", brief.papers),
        ("BUILDER AND ECOSYSTEM TRENDS", brief.trends),
        ("REPOSITORIES AND TOOLS", brief.repositories),
    )
    for heading, items in sections:
        lines.extend(["", heading])
        if not items:
            lines.append("No qualifying items today.")
            continue
        for index, item in enumerate(items, start=1):
            lines.extend(_text_item(index, item))

    lines.extend(
        [
            "",
            "CONTENT OPPORTUNITY",
            brief.opportunity.title,
            f"Why it matters: {brief.opportunity.rationale}",
            f"Angle: {brief.opportunity.post_angle}",
        ]
    )
    for url in brief.opportunity.source_urls:
        lines.append(f"- {url}")
    return "\n".join(lines).strip() + "\n"


def _text_item(index: int, item: BriefItem) -> list[str]:
    return [
        f"{index}. {item.title} [{item.source_name}]",
        f"   {item.url}",
        f"   Summary: {item.summary}",
        f"   Content angle: {item.post_angle}",
        f"   Relevance score: {item.score:.1f}",
    ]


def render_html(brief: DailyBrief) -> str:
    note = ""
    if brief.degraded:
        note = (
            '<p style="padding:12px;background:#fff4ce;border-radius:6px;">'
            "This is a reduced brief because one or more inputs failed.</p>"
        )
    sections = "".join(
        _html_section(heading, items)
        for heading, items in (
            ("Papers worth your attention", brief.papers),
            ("Builder and ecosystem trends", brief.trends),
            ("Repositories and tools", brief.repositories),
        )
    )
    opportunity_links = "".join(
        f'<li><a href="{escape(url, quote=True)}">{escape(url)}</a></li>'
        for url in brief.opportunity.source_urls
    )
    return f"""<!doctype html>
<html>
<body style="margin:0;background:#f5f7fa;font-family:Arial,sans-serif;color:#17202a;">
  <main style="max-width:720px;margin:0 auto;padding:24px;">
    <header style="background:#102a43;color:white;padding:24px;border-radius:10px;">
      <h1 style="margin:0 0 8px;">Daily AI Brief</h1>
      <div>{escape(brief.brief_date.strftime("%B %d, %Y"))}</div>
    </header>
    {note}
    {sections}
    <section style="background:white;margin-top:18px;padding:20px;border-radius:10px;">
      <h2 style="margin-top:0;color:#0b7285;">Content opportunity</h2>
      <h3>{escape(brief.opportunity.title)}</h3>
      <p><strong>Why it matters:</strong> {escape(brief.opportunity.rationale)}</p>
      <p><strong>Angle:</strong> {escape(brief.opportunity.post_angle)}</p>
      <ul>{opportunity_links}</ul>
    </section>
    <footer style="padding:18px 4px;color:#66788a;font-size:12px;">
      Generated with {escape(brief.model_used)}. Use this as research input, not final copy.
    </footer>
  </main>
</body>
</html>"""


def _html_section(heading: str, items: list[BriefItem]) -> str:
    if not items:
        content = "<p>No qualifying items today.</p>"
    else:
        content = "".join(_html_item(item) for item in items)
    return (
        '<section style="background:white;margin-top:18px;padding:20px;'
        'border-radius:10px;">'
        f'<h2 style="margin-top:0;color:#0b7285;">{escape(heading)}</h2>'
        f"{content}</section>"
    )


def _html_item(item: BriefItem) -> str:
    return f"""
<article style="padding:14px 0;border-top:1px solid #e6edf3;">
  <h3 style="margin:0 0 6px;">
    <a style="color:#125d98;" href="{escape(item.url, quote=True)}">
      {escape(item.title)}
    </a>
  </h3>
  <div style="color:#66788a;font-size:13px;">
    {escape(item.source_name)} | {escape(item.category)} | score {item.score:.1f}
  </div>
  <p><strong>Summary:</strong> {escape(item.summary)}</p>
  <p><strong>Content angle:</strong> {escape(item.post_angle)}</p>
</article>"""

