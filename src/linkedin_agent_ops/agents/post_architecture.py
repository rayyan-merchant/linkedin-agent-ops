from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from linkedin_agent_ops.agent_models import (
    AgentResponse,
    IssueSeverity,
    ValidationIssue,
)
from linkedin_agent_ops.agents.base import BaseAgent
from linkedin_agent_ops.prompting import PromptEnvelope


class PostFormat(StrEnum):
    ANY = "any"
    TEXT = "text"
    CAROUSEL = "carousel"
    IMAGE = "image"
    VIDEO = "video"


class PostArchitectureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=3, max_length=300)
    key_insight: str = Field(min_length=10, max_length=1200)
    metric_or_evidence: str | None = Field(default=None, max_length=1000)
    preferred_format: PostFormat = PostFormat.ANY
    audience_override: str | None = Field(default=None, max_length=500)


class HookOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    angle: str
    lines: list[str] = Field(min_length=2, max_length=2)
    evidence_used: str | None = None


class PostArchitectureResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format_recommendation: PostFormat
    format_reason: str
    target_length: str
    hooks: list[HookOption] = Field(min_length=7, max_length=7)
    outline: list[str] = Field(min_length=5, max_length=7)
    discussion_prompts: list[str] = Field(min_length=3, max_length=3)
    save_element: str
    cta_guidance: str
    missing_proof_warnings: list[str] = Field(default_factory=list)

    @field_validator("outline")
    @classmethod
    def outline_is_headers_only(cls, value: list[str]) -> list[str]:
        if any(len(item.split()) > 12 for item in value):
            raise ValueError("outline entries must be concise section headers")
        return value


class PostArchitectureAgent(BaseAgent):
    name = "post_architecture"

    def generate(
        self, request: PostArchitectureRequest
    ) -> AgentResponse[PostArchitectureResult]:
        evidence = request.model_dump(mode="json")
        envelope = PromptEnvelope(
            role=(
                "You are a senior LinkedIn content strategist for technical AI builders. "
                "You solve positioning and structure, but never write the complete post."
            ),
            creator_context=self.context(),
            task=(
                "Recommend the best format and create exactly seven two-line hook options "
                "using distinct angles: experiment result, deployment failure, metric "
                "comparison, what changed the creator's mind, human problem, counterintuitive "
                "number, and common technical mistake. Use a metric only when supplied. "
                "Return a header-only outline, three questions that invite specific technical "
                "experience, one concrete save element, CTA guidance, and proof gaps. "
                "Hooks are raw options for the creator to rewrite, not final post copy."
            ),
            evidence=evidence,
            rubric=(
                "Every hook must be exactly two concise lines, specific to the input, grounded "
                "in supplied evidence, and materially different from the others. Do not imply "
                "testing, deployment, personal experience, or numerical results not supplied. "
                "Avoid generic engagement questions and all banned language."
            ),
            examples=self.examples(request.topic),
        )
        return self.runner.run(
            agent=self.name,
            envelope=envelope,
            output_model=PostArchitectureResult,
            deterministic_validator=lambda result: self.validate(result, request),
        )

    def validate(
        self,
        result: PostArchitectureResult,
        request: PostArchitectureRequest,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        serialized = result.model_dump_json().lower()
        for phrase in self.profile.banned_language:
            if phrase in serialized:
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.MAJOR,
                        code="banned_language",
                        message=f"Contains banned phrase: {phrase}",
                    )
                )
        normalized_hooks = {
            re.sub(r"\W+", " ", " ".join(hook.lines).lower()).strip()
            for hook in result.hooks
        }
        if len(normalized_hooks) != 7:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.MAJOR,
                    code="duplicate_hooks",
                    message="Hook options are not distinct.",
                    path="hooks",
                )
            )
        supplied_numbers = set(
            re.findall(
                r"\b\d+(?:\.\d+)?%?\b",
                " ".join(
                    filter(
                        None,
                        [
                            request.topic,
                            request.key_insight,
                            request.metric_or_evidence,
                        ],
                    )
                ),
            )
        )
        output_numbers = set(
            re.findall(
                r"\b\d+(?:\.\d+)?%?\b",
                " ".join(
                    text
                    for hook in result.hooks
                    for text in [*hook.lines, hook.evidence_used or ""]
                ),
            )
        )
        invented = output_numbers - supplied_numbers
        if invented:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.CRITICAL,
                    code="invented_number",
                    message=f"Unsupported numbers found: {sorted(invented)}",
                )
            )
        for index, hook in enumerate(result.hooks):
            if any(len(line.split()) > 25 for line in hook.lines):
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.WARNING,
                        code="long_hook",
                        message="Hook line is longer than 25 words.",
                        path=f"hooks.{index}",
                    )
                )
        return issues
