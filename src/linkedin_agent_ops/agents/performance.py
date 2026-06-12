from __future__ import annotations

import csv
import io
import math
import re
import statistics
from collections import defaultdict
from datetime import date, time
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from linkedin_agent_ops.agent_models import (
    AgentResponse,
    IssueSeverity,
    ValidationIssue,
)
from linkedin_agent_ops.agents.base import BaseAgent
from linkedin_agent_ops.prompting import PromptEnvelope


class ContentFormat(StrEnum):
    TEXT = "text"
    CAROUSEL = "carousel"
    IMAGE = "image"
    VIDEO = "video"
    OTHER = "other"


class PostMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    post_id: str = Field(min_length=1, max_length=100)
    posted_date: date
    posted_time: time | None = None
    format: ContentFormat
    topic: str
    pillar: str
    hook_type: str
    first_line: str
    impressions: int = Field(ge=0)
    reactions: int = Field(ge=0)
    comments: int = Field(ge=0)
    saves: int = Field(ge=0)
    shares: int = Field(ge=0)
    profile_clicks: int = Field(ge=0)
    golden_hour_comments: int | None = Field(default=None, ge=0)
    replied_within_15min: bool | None = None
    max_thread_depth: int | None = Field(default=None, ge=0)
    were_you_online_gh: bool | None = None

    @field_validator("post_id", "topic", "pillar", "hook_type", "first_line")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class PerformanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    posts: list[PostMetric] = Field(min_length=2)
    analysis_goal: str = "Improve useful reach, saves, and technical discussion."


class ComputedPost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    post_id: str
    format: ContentFormat
    topic: str
    pillar: str
    hook_type: str
    engagement_rate: float
    save_rate: float
    comment_rate: float
    share_rate: float
    profile_click_rate: float
    impressions: int
    golden_hour_comments: int | None
    replied_within_15min: bool | None
    were_you_online_gh: bool | None


class GroupSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group: str
    posts: int
    median_impressions: float
    median_save_rate: float
    median_comment_rate: float


class CorrelationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eligible: bool
    coefficient: float | None = None
    reason: str


class AnalyticsDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    posts: list[ComputedPost]
    by_format: list[GroupSummary]
    by_topic: list[GroupSummary]
    by_hook: list[GroupSummary]
    reply_impression_correlation: CorrelationSummary
    offline_rate: float | None
    data_quality_warnings: list[str] = Field(default_factory=list)


class EvidenceFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding: str
    post_ids: list[str] = Field(min_length=1)
    confidence: str


class PerformanceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    executive_summary: str
    findings: list[EvidenceFinding] = Field(min_length=3, max_length=10)
    top_topic_format_combinations: list[str] = Field(min_length=1, max_length=5)
    hook_analysis: list[str] = Field(min_length=1, max_length=5)
    behavioral_audit: list[str] = Field(min_length=1, max_length=5)
    data_quality_warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(min_length=2, max_length=6)
    controlled_experiment: str


class PerformanceAgent(BaseAgent):
    name = "performance"

    def generate(
        self, request: PerformanceRequest
    ) -> tuple[AgentResponse[PerformanceResult], AnalyticsDataset]:
        dataset = compute_analytics(request.posts)
        envelope = PromptEnvelope(
            role=(
                "You are a quantitative content performance analyst. You interpret computed "
                "statistics conservatively and distinguish content signals from behavioral "
                "or distribution factors."
            ),
            creator_context=self.context(),
            task=(
                "Analyze the computed dataset. Cite post_ids for every finding. Rank useful "
                "topic/format and hook patterns using medians and rates, audit first-hour "
                "behavior, identify data limitations, recommend specific changes, and propose "
                "one experiment that changes one variable. Treat ineligible correlations as "
                "directional only."
            ),
            evidence={
                "goal": request.analysis_goal,
                "analytics": dataset.model_dump(mode="json"),
            },
            rubric=(
                "Do not claim LinkedIn algorithm rules or causation. Do not calculate new "
                "statistics. Ground conclusions in supplied computed fields and named post IDs."
            ),
        )
        response = self.runner.run(
            agent=self.name,
            envelope=envelope,
            output_model=PerformanceResult,
            deterministic_validator=lambda result: self.validate(
                result,
                {post.post_id for post in request.posts},
                dataset,
            ),
        )
        return response, dataset

    @staticmethod
    def validate(
        result: PerformanceResult,
        known_post_ids: set[str],
        dataset: AnalyticsDataset,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        cited = {
            post_id for finding in result.findings for post_id in finding.post_ids
        }
        unknown = cited - known_post_ids
        if unknown:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.CRITICAL,
                    code="unknown_post_id",
                    message=f"Findings cite unknown posts: {sorted(unknown)}",
                    path="findings",
                )
            )
        text = result.model_dump_json().lower()
        for phrase in (
            "the algorithm rewards",
            "linkedin requires",
            "guaranteed reach",
            "golden hour is the",
        ):
            if phrase in text:
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.MAJOR,
                        code="unsupported_algorithm_claim",
                        message=f"Unsupported platform claim: {phrase}",
                    )
                )
        supplied_numbers = set(
            re.findall(r"\d+(?:\.\d+)?", dataset.model_dump_json())
        )
        output_numbers = set(
            re.findall(r"\d+(?:\.\d+)?", result.model_dump_json())
        )
        unknown_numbers = output_numbers - supplied_numbers
        if unknown_numbers:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.MAJOR,
                    code="uncomputed_number",
                    message=(
                        "Analysis contains numbers not present in computed data: "
                        f"{sorted(unknown_numbers)}"
                    ),
                )
            )
        return issues


def compute_analytics(posts: list[PostMetric]) -> AnalyticsDataset:
    computed = [
        ComputedPost(
            post_id=post.post_id,
            format=post.format,
            topic=post.topic,
            pillar=post.pillar,
            hook_type=post.hook_type,
            engagement_rate=_rate(
                post.reactions + post.comments + post.saves + post.shares,
                post.impressions,
            ),
            save_rate=_rate(post.saves, post.impressions),
            comment_rate=_rate(post.comments, post.impressions),
            share_rate=_rate(post.shares, post.impressions),
            profile_click_rate=_rate(post.profile_clicks, post.impressions),
            impressions=post.impressions,
            golden_hour_comments=post.golden_hour_comments,
            replied_within_15min=post.replied_within_15min,
            were_you_online_gh=post.were_you_online_gh,
        )
        for post in posts
    ]
    warnings = []
    if any(post.impressions == 0 for post in posts):
        warnings.append("Posts with zero impressions have rates set to 0.")
    if any(post.golden_hour_comments is None for post in posts):
        warnings.append("Some posts are missing first-hour comment data.")

    correlation_posts = [
        post
        for post in computed
        if post.replied_within_15min is not None and post.impressions > 0
    ]
    x = [1.0 if post.replied_within_15min else 0.0 for post in correlation_posts]
    y = [float(post.impressions) for post in correlation_posts]
    eligible = len(correlation_posts) >= 8 and len(set(x)) > 1 and len(set(y)) > 1
    correlation = CorrelationSummary(
        eligible=eligible,
        coefficient=_pearson(x, y) if eligible else None,
        reason=(
            "Eligible: at least 8 posts with variation in both fields."
            if eligible
            else "Directional only: requires at least 8 posts and variation in both fields."
        ),
    )
    online_values = [
        post.were_you_online_gh
        for post in computed
        if post.were_you_online_gh is not None
    ]
    offline_rate = (
        round(sum(not value for value in online_values) / len(online_values), 4)
        if online_values
        else None
    )
    return AnalyticsDataset(
        posts=computed,
        by_format=_group(computed, lambda post: post.format.value),
        by_topic=_group(computed, lambda post: post.topic),
        by_hook=_group(computed, lambda post: post.hook_type),
        reply_impression_correlation=correlation,
        offline_rate=offline_rate,
        data_quality_warnings=warnings,
    )


def parse_posts_csv(content: bytes) -> list[PostMetric]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must be UTF-8 encoded") from exc
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise ValueError("CSV contains no data rows")
    boolean_fields = {"replied_within_15min", "were_you_online_gh"}
    integer_fields = {
        "impressions",
        "reactions",
        "comments",
        "saves",
        "shares",
        "profile_clicks",
        "golden_hour_comments",
        "max_thread_depth",
    }
    parsed = []
    for row in rows:
        cleaned = dict(row)
        for field in boolean_fields:
            value = (cleaned.get(field) or "").strip().lower()
            cleaned[field] = None if not value else value in {"true", "1", "yes"}
        for field in integer_fields:
            value = (cleaned.get(field) or "").strip()
            cleaned[field] = None if not value and field in {
                "golden_hour_comments",
                "max_thread_depth",
            } else int(value or 0)
        if not (cleaned.get("posted_time") or "").strip():
            cleaned["posted_time"] = None
        parsed.append(PostMetric.model_validate(cleaned))
    return parsed


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _group(computed: list[ComputedPost], key_fn) -> list[GroupSummary]:
    groups = defaultdict(list)
    for post in computed:
        groups[key_fn(post)].append(post)
    summaries = [
        GroupSummary(
            group=group,
            posts=len(values),
            median_impressions=statistics.median(
                post.impressions for post in values
            ),
            median_save_rate=statistics.median(post.save_rate for post in values),
            median_comment_rate=statistics.median(
                post.comment_rate for post in values
            ),
        )
        for group, values in groups.items()
    ]
    return sorted(summaries, key=lambda item: item.median_save_rate, reverse=True)


def _pearson(x: list[float], y: list[float]) -> float:
    x_mean = statistics.mean(x)
    y_mean = statistics.mean(y)
    numerator = sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y, strict=True))
    x_sum = sum((a - x_mean) ** 2 for a in x)
    y_sum = sum((b - y_mean) ** 2 for b in y)
    denominator = math.sqrt(x_sum * y_sum)
    return round(numerator / denominator, 4) if denominator else 0.0
