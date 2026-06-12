from __future__ import annotations

import math
from datetime import datetime

from linkedin_agent_ops.models import BriefSection, SourceItem, SourceKind
from linkedin_agent_ops.utils import canonicalize_url

SOURCE_QUALITY = {
    SourceKind.ARXIV: 1.0,
    SourceKind.RSS: 0.9,
    SourceKind.GITHUB: 0.85,
    SourceKind.HACKER_NEWS: 0.8,
}


def deduplicate(items: list[SourceItem]) -> list[SourceItem]:
    unique: dict[str, SourceItem] = {}
    for item in items:
        key = canonicalize_url(item.url)
        normalized = item.model_copy(update={"url": key})
        previous = unique.get(key)
        if previous is None or normalized.published_at > previous.published_at:
            unique[key] = normalized
    return list(unique.values())


def score_items(
    items: list[SourceItem],
    *,
    as_of: datetime,
    keywords: list[str],
    weights: dict[str, float],
    maximum_age_hours: int = 168,
) -> list[SourceItem]:
    ranked: list[SourceItem] = []
    lowered_keywords = [keyword.lower() for keyword in keywords]

    for item in items:
        age_hours = max(0.0, (as_of - item.published_at).total_seconds() / 3600)
        recency = max(0.0, 1 - age_hours / maximum_age_hours)
        haystack = f"{item.title} {item.excerpt} {item.category}".lower()
        match_count = sum(keyword in haystack for keyword in lowered_keywords)
        relevance = min(1.0, match_count / 3)
        quality = SOURCE_QUALITY[item.source]
        engagement = _engagement_score(item)

        score = (
            recency * weights["recency_weight"]
            + relevance * weights["relevance_weight"]
            + quality * weights["source_quality_weight"]
            + engagement * weights["engagement_weight"]
        )
        ranked.append(item.model_copy(update={"score": round(score, 2)}))

    return sorted(ranked, key=lambda item: (item.score, item.published_at), reverse=True)


def _engagement_score(item: SourceItem) -> float:
    if item.source == SourceKind.HACKER_NEWS:
        raw = item.metrics.get("points", 0) + item.metrics.get("comments", 0) * 2
        return min(1.0, math.log1p(raw) / math.log1p(500))
    if item.source == SourceKind.GITHUB:
        raw = item.metrics.get("stars", 0) + item.metrics.get("forks", 0) * 2
        return min(1.0, math.log1p(raw) / math.log1p(1000))
    return 0.5


def section_for(item: SourceItem) -> BriefSection:
    if item.source == SourceKind.ARXIV:
        return BriefSection.PAPERS
    if item.source == SourceKind.GITHUB:
        return BriefSection.REPOSITORIES
    return BriefSection.TRENDS


def select_candidates(
    ranked: list[SourceItem],
    *,
    paper_count: int,
    trend_count: int,
    repository_count: int,
) -> list[SourceItem]:
    limits = {
        BriefSection.PAPERS: paper_count,
        BriefSection.TRENDS: trend_count,
        BriefSection.REPOSITORIES: repository_count,
    }
    selected: list[SourceItem] = []
    counts = {section: 0 for section in limits}
    for item in ranked:
        section = section_for(item)
        if counts[section] >= limits[section]:
            continue
        selected.append(item)
        counts[section] += 1
    return selected

