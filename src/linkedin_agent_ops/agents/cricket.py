from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from linkedin_agent_ops.agent_models import (
    AgentResponse,
    IssueSeverity,
    ValidationIssue,
)
from linkedin_agent_ops.agents.base import BaseAgent
from linkedin_agent_ops.prompting import PromptEnvelope


class MetricDirection(StrEnum):
    HIGHER = "higher"
    LOWER = "lower"
    NEUTRAL = "neutral"


class ProjectMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: float
    unit: str
    better_when: MetricDirection


class CricketBuildLogRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    week_number: int = Field(ge=1, le=500)
    work_completed: str = Field(min_length=10, max_length=5000)
    failures: str = Field(min_length=3, max_length=5000)
    current_metrics: list[ProjectMetric] = Field(min_length=1, max_length=30)
    previous_metrics: list[ProjectMetric] = Field(default_factory=list, max_length=30)
    available_visual_assets: list[str] = Field(default_factory=list, max_length=20)


class MetricChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    previous: str | None
    current: str
    interpretation: str


class CricketBuildLogResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    week_headline: str
    technical_to_cricket_translation: list[str] = Field(min_length=2, max_length=8)
    metric_changes: list[MetricChange] = Field(min_length=1)
    progress_narrative: str
    failure_narrative: str
    hook_options: list[str] = Field(min_length=3, max_length=3)
    audience_bridge: str
    visual_recommendation: str
    missing_evidence_warnings: list[str] = Field(default_factory=list)


class CricketBuildLogAgent(BaseAgent):
    name = "cricket_build_log"

    def generate(
        self, request: CricketBuildLogRequest
    ) -> AgentResponse[CricketBuildLogResult]:
        envelope = PromptEnvelope(
            role=(
                "You are an editor for a cricket computer-vision engineering build log. "
                "You translate technical progress into cricket meaning while preserving every "
                "engineering qualification."
            ),
            creator_context=self.context(),
            task=(
                "Create a week headline, technical-to-cricket translations, metric change "
                "interpretations, progress and failure narratives, exactly three hook options, "
                "an audience bridge for engineers and cricket analysts, a visual recommendation, "
                "and evidence warnings. Compare metrics only when names and units match. Respect "
                "whether higher or lower is better."
            ),
            evidence=request.model_dump(mode="json"),
            rubric=(
                "Use every numerical value exactly as supplied. Never invent accuracy, match "
                "impact, player behavior, or cricket outcomes. Translate the engineering task "
                "without claiming the model can do something not demonstrated."
            ),
            examples=self.examples("cricket computer vision build log"),
        )
        return self.runner.run(
            agent=self.name,
            envelope=envelope,
            output_model=CricketBuildLogResult,
            deterministic_validator=lambda result: self.validate(result, request),
        )

    @staticmethod
    def validate(
        result: CricketBuildLogResult,
        request: CricketBuildLogRequest,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        supplied = {
            _number(metric.value)
            for metric in [*request.current_metrics, *request.previous_metrics]
        }
        supplied.add(str(request.week_number))
        output = result.model_dump_json()
        output_numbers = set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", output))
        invented = output_numbers - supplied
        if invented:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.CRITICAL,
                    code="invented_metric",
                    message=f"Unsupported numeric values found: {sorted(invented)}",
                )
            )
        current_names = {metric.name.lower() for metric in request.current_metrics}
        unknown = {
            change.name.lower() for change in result.metric_changes
        } - current_names
        if unknown:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.MAJOR,
                    code="unknown_metric",
                    message=f"Unknown metrics interpreted: {sorted(unknown)}",
                    path="metric_changes",
                )
            )
        return issues


def _number(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)

