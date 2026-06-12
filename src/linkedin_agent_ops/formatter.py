from __future__ import annotations

from html import escape

from linkedin_agent_ops.models import BriefItem, BriefSection, DailyBrief

EMAIL_BACKGROUND = "#eef3ff"
CARD_BACKGROUND = "#ffffff"
TEXT_COLOR = "#182230"
MUTED_COLOR = "#667085"
BRAND_NAVY = "#172554"
BRAND_BLUE = "#2563eb"

SECTION_STYLES = {
    BriefSection.PAPERS: {
        "eyebrow": "RESEARCH RADAR",
        "heading": "Papers worth your attention",
        "description": "New research selected for practical relevance.",
        "accent": "#7c3aed",
        "soft": "#f3e8ff",
        "badge": "PAPER",
    },
    BriefSection.TRENDS: {
        "eyebrow": "BUILDER SIGNALS",
        "heading": "What builders are discussing",
        "description": "Ideas and ecosystem shifts gaining technical attention.",
        "accent": "#ea580c",
        "soft": "#ffedd5",
        "badge": "TREND",
    },
    BriefSection.REPOSITORIES: {
        "eyebrow": "TOOL WATCH",
        "heading": "Repositories and tools",
        "description": "Projects worth opening, testing, or tracking.",
        "accent": "#059669",
        "soft": "#d1fae5",
        "badge": "TOOL",
    },
}


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
    total_items = len(brief.all_items())
    note = ""
    if brief.degraded:
        note = (
            '<tr><td style="padding:0 24px 18px;">'
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
            'style="background:#fff7ed;border:1px solid #fed7aa;border-radius:12px;">'
            '<tr><td style="padding:14px 16px;color:#9a3412;font-size:13px;'
            'line-height:20px;"><strong>Reduced brief:</strong> one or more sources were '
            "unavailable, so today's edition contains the strongest remaining signals."
            "</td></tr></table></td></tr>"
        )
    sections = "".join(
        _html_section(section, items)
        for section, items in (
            (BriefSection.PAPERS, brief.papers),
            (BriefSection.TRENDS, brief.trends),
            (BriefSection.REPOSITORIES, brief.repositories),
        )
    )
    opportunity_links = " &nbsp; ".join(
        (
            f'<a href="{escape(url, quote=True)}" style="color:#4338ca;'
            f'font-size:12px;text-decoration:underline;">Source {index}</a>'
        )
        for index, url in enumerate(brief.opportunity.source_urls, start=1)
    )
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Rayyan's Daily AI Intelligence Brief</title>
</head>
<body style="margin:0;padding:0;background:{EMAIL_BACKGROUND};
             font-family:Arial,Helvetica,sans-serif;color:{TEXT_COLOR};">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
         style="width:100%;background:{EMAIL_BACKGROUND};">
    <tr>
      <td align="center" style="padding:28px 12px;">
        <table role="presentation" width="680" cellspacing="0" cellpadding="0"
               style="width:100%;max-width:680px;background:{CARD_BACKGROUND};border-radius:20px;
                      overflow:hidden;box-shadow:0 12px 34px rgba(37,54,110,0.12);">
          <tr>
            <td style="padding:32px 28px;background:{BRAND_NAVY};
                       background-image:linear-gradient(135deg,{BRAND_NAVY} 0%,
                                                        #3730a3 55%,{BRAND_BLUE} 100%);">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                <tr>
                  <td>
                    <div style="font-size:11px;line-height:16px;letter-spacing:1.8px;
                                font-weight:bold;color:#bfdbfe;">RAYYAN'S MORNING INTELLIGENCE</div>
                    <h1 style="margin:8px 0 8px;font-size:30px;line-height:36px;color:#ffffff;">
                      Daily AI Brief
                    </h1>
                    <p style="margin:0;color:#dbeafe;font-size:14px;line-height:21px;">
                      Research signals, builder trends, and practical content opportunities.
                    </p>
                  </td>
                </tr>
                <tr>
                  <td style="padding-top:24px;">
                    <span style="display:inline-block;padding:7px 11px;margin-right:7px;
                                 border-radius:999px;background:rgba(255,255,255,0.14);
                                 color:#ffffff;font-size:12px;font-weight:bold;">
                      {escape(brief.brief_date.strftime("%A, %B %d"))}
                    </span>
                    <span style="display:inline-block;padding:7px 11px;border-radius:999px;
                                 background:#fef3c7;color:#92400e;font-size:12px;font-weight:bold;">
                      {total_items} signals selected
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:22px 28px 14px;background:#f8fafc;border-bottom:1px solid #e5e7eb;">
              <p style="margin:0;color:#344054;font-size:14px;line-height:22px;">
                Good morning, Rayyan. Here is the short list worth your attention today.
                Each item includes the practical takeaway and a possible angle
                for your own thinking.
              </p>
            </td>
          </tr>
          {note}
          {sections}
          <tr>
            <td style="padding:12px 24px 24px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
                     style="background:#eef2ff;border:1px solid #c7d2fe;border-radius:16px;">
                <tr>
                  <td style="padding:22px;">
                    <div style="font-size:11px;letter-spacing:1.5px;
                                font-weight:bold;color:#6366f1;">
                      TODAY'S CONTENT OPPORTUNITY
                    </div>
                    <h2 style="margin:8px 0 10px;color:#312e81;font-size:21px;line-height:28px;">
                      {escape(brief.opportunity.title)}
                    </h2>
                    <p style="margin:0 0 12px;color:#3730a3;font-size:14px;line-height:22px;">
                      <strong>Why this matters:</strong> {escape(brief.opportunity.rationale)}
                    </p>
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
                           style="background:#ffffff;border-left:4px solid #6366f1;
                                  border-radius:8px;">
                      <tr>
                        <td style="padding:14px 16px;color:#312e81;
                                   font-size:14px;line-height:22px;">
                          <strong>Your angle:</strong> {escape(brief.opportunity.post_angle)}
                        </td>
                      </tr>
                    </table>
                    <div style="padding-top:13px;">{opportunity_links}</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:20px 28px 26px;background:#f8fafc;
                                      border-top:1px solid #e5e7eb;">
              <p style="margin:0 0 6px;color:#475467;font-size:12px;line-height:18px;">
                Built for Rayyan's research-to-production content workflow.
              </p>
              <p style="margin:0;color:#98a2b3;font-size:11px;line-height:17px;">
                Generated with {escape(brief.model_used)}. Use as research input,
                then apply your own voice and judgment.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _html_section(section: BriefSection, items: list[BriefItem]) -> str:
    style = SECTION_STYLES[section]
    if not items:
        content = (
            '<tr><td style="padding:18px;color:#667085;font-size:14px;">'
            "No qualifying items today.</td></tr>"
        )
    else:
        content = "".join(
            _html_item(item, index, style)
            for index, item in enumerate(items, start=1)
        )
    return f"""
<tr>
  <td style="padding:24px 24px 8px;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
           style="border:1px solid #e4e7ec;border-radius:16px;overflow:hidden;">
      <tr>
        <td style="padding:19px 20px;background:{style["soft"]};border-bottom:1px solid #e4e7ec;">
          <div style="font-size:10px;letter-spacing:1.5px;font-weight:bold;
                      color:{style["accent"]};">
            {style["eyebrow"]}
          </div>
          <h2 style="margin:6px 0 3px;color:{TEXT_COLOR};font-size:21px;line-height:27px;">
            {style["heading"]}
          </h2>
          <p style="margin:0;color:{MUTED_COLOR};font-size:13px;line-height:20px;">
            {style["description"]}
          </p>
        </td>
      </tr>
      {content}
    </table>
  </td>
</tr>"""


def _html_item(item: BriefItem, index: int, style: dict[str, str]) -> str:
    score = max(0, min(100, round(item.score)))
    return f"""
<tr>
  <td style="padding:20px;border-bottom:1px solid #eaecf0;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
      <tr>
        <td valign="top" width="38">
          <div style="width:30px;height:30px;border-radius:9px;background:{style["soft"]};
                      color:{style["accent"]};font-size:13px;line-height:30px;
                      text-align:center;font-weight:bold;">{index}</div>
        </td>
        <td valign="top">
          <div style="margin-bottom:7px;">
            <span style="display:inline-block;padding:4px 7px;border-radius:5px;
                         background:{style["soft"]};color:{style["accent"]};
                         font-size:9px;line-height:12px;letter-spacing:0.8px;font-weight:bold;">
              {style["badge"]}
            </span>
            <span style="color:{MUTED_COLOR};font-size:11px;line-height:16px;">
              &nbsp; {escape(item.source_name)} &middot; {escape(item.category)}
            </span>
          </div>
          <h3 style="margin:0 0 10px;font-size:17px;line-height:24px;">
            <a href="{escape(item.url, quote=True)}"
               style="color:{TEXT_COLOR};text-decoration:none;">
              {escape(item.title)}
            </a>
          </h3>
          <p style="margin:0 0 11px;color:#344054;font-size:14px;line-height:22px;">
            {escape(item.summary)}
          </p>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
                 style="background:#f8fafc;border-left:3px solid {style["accent"]};
                        border-radius:7px;">
            <tr>
              <td style="padding:11px 13px;color:#475467;font-size:13px;line-height:20px;">
                <strong style="color:{style["accent"]};">Content angle:</strong>
                {escape(item.post_angle)}
              </td>
            </tr>
          </table>
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
                 style="margin-top:12px;">
            <tr>
              <td style="color:{MUTED_COLOR};font-size:11px;">
                Relevance
              </td>
              <td align="right" style="color:{style["accent"]};font-size:11px;font-weight:bold;">
                {score}/100
              </td>
            </tr>
            <tr>
              <td colspan="2" style="padding-top:5px;">
                <div style="height:5px;background:#eaecf0;border-radius:999px;overflow:hidden;">
                  <div style="width:{score}%;height:5px;background:{style["accent"]};
                              border-radius:999px;"></div>
                </div>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </td>
</tr>"""
