from datetime import date

from linkedin_agent_ops.agents.performance import (
    ContentFormat,
    PostMetric,
    compute_analytics,
    parse_posts_csv,
)


def post(index: int, replied: bool) -> PostMetric:
    return PostMetric(
        post_id=f"post-{index}",
        posted_date=date(2026, 6, index + 1),
        format=ContentFormat.TEXT,
        topic="agents",
        pillar="technical",
        hook_type="metric",
        first_line="A specific technical hook.",
        impressions=1000 + index * 100,
        reactions=50,
        comments=10,
        saves=20,
        shares=5,
        profile_clicks=3,
        replied_within_15min=replied,
        were_you_online_gh=replied,
    )


def test_analytics_enables_correlation_only_with_enough_variation():
    dataset = compute_analytics([post(index, index % 2 == 0) for index in range(8)])
    assert dataset.reply_impression_correlation.eligible is True
    assert dataset.offline_rate == 0.5
    assert dataset.posts[0].save_rate == 0.02


def test_csv_parser_handles_optional_and_boolean_fields():
    content = (
        b"post_id,posted_date,posted_time,format,topic,pillar,hook_type,first_line,"
        b"impressions,reactions,comments,saves,shares,profile_clicks,"
        b"golden_hour_comments,replied_within_15min,max_thread_depth,were_you_online_gh\n"
        b"p1,2026-06-01,,text,agents,technical,metric,Hook,100,5,2,3,1,1,,yes,,false\n"
    )
    parsed = parse_posts_csv(content)
    assert parsed[0].replied_within_15min is True
    assert parsed[0].were_you_online_gh is False
    assert parsed[0].golden_hour_comments is None
