from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceKind(StrEnum):
    ARXIV = "arxiv"
    HACKER_NEWS = "hacker_news"
    GITHUB = "github"
    RSS = "rss"


class BriefSection(StrEnum):
    PAPERS = "papers"
    TRENDS = "trends"
    REPOSITORIES = "repositories"


class SourceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    source: SourceKind
    source_name: str
    title: str
    url: str
    published_at: datetime
    excerpt: str = ""
    category: str = ""
    authors: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    score: float = 0.0

    @field_validator("title", "url")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class BriefItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    section: BriefSection
    source: SourceKind
    source_name: str
    category: str = ""
    title: str
    url: str
    published_at: datetime
    summary: str
    post_angle: str
    score: float


class ContentOpportunity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    rationale: str
    post_angle: str
    source_urls: list[str] = Field(default_factory=list)


class DailyBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brief_date: date
    generated_at: datetime
    papers: list[BriefItem]
    trends: list[BriefItem]
    repositories: list[BriefItem]
    opportunity: ContentOpportunity
    model_used: str
    degraded: bool = False

    def all_items(self) -> list[BriefItem]:
        return [*self.papers, *self.trends, *self.repositories]


class RunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    brief_date: date
    started_at: datetime
    completed_at: datetime | None = None
    status: str
    collector_counts: dict[str, int] = Field(default_factory=dict)
    collector_errors: dict[str, str] = Field(default_factory=dict)
    selected_count: int = 0
    model_used: str = ""
    email_status: str = "not_attempted"
    sheets_status: str = "not_attempted"
    error: str = ""

