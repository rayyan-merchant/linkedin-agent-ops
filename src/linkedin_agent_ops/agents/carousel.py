from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

from linkedin_agent_ops.agent_models import (
    AgentResponse,
    IssueSeverity,
    ValidationIssue,
)
from linkedin_agent_ops.agents.base import BaseAgent
from linkedin_agent_ops.prompting import PromptEnvelope


class CarouselRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=3, max_length=300)
    key_points: list[str] = Field(min_length=2, max_length=12)
    audience: str | None = Field(default=None, max_length=500)
    source_brief: str | None = Field(default=None, max_length=20000)
    slide_count: int = Field(default=10, ge=8, le=10)


class CarouselSlide(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slide_number: int = Field(ge=1, le=10)
    title: str
    on_slide_copy: str
    core_message: str
    visual_recommendation: str
    evidence: str | None = None
    transition_hook: str

    @model_validator(mode="after")
    def enforce_copy_limits(self):
        if len(self.title.split()) > 5:
            raise ValueError("slide title must contain at most five words")
        if len(self.on_slide_copy.split()) > 40:
            raise ValueError("on-slide copy must contain at most 40 words")
        return self


class CarouselResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    narrative_strategy: str
    slides: list[CarouselSlide] = Field(min_length=8, max_length=10)
    design_guidance: list[str] = Field(min_length=3, max_length=7)
    evidence_warnings: list[str] = Field(default_factory=list)


class CarouselAgent(BaseAgent):
    name = "carousel"

    def generate(self, request: CarouselRequest) -> AgentResponse[CarouselResult]:
        envelope = PromptEnvelope(
            role=(
                "You are a technical information architect designing LinkedIn carousel "
                "outlines for AI engineers. You organize evidence and narrative; the creator "
                "writes and designs the final artifact."
            ),
            creator_context=self.context(),
            task=(
                f"Create exactly {request.slide_count} slides. Slide 1 must frame the concrete "
                "problem or claim. Middle slides must each contain one idea and progress "
                "logically. The final slide must give a concrete practitioner takeaway and "
                "restrained CTA guidance. For each slide return title, on-slide copy, core "
                "message, visual recommendation, supplied evidence if any, and a meaningful "
                "transition hook. Do not claim algorithmic reach or dwell-time thresholds."
            ),
            evidence=request.model_dump(mode="json"),
            rubric=(
                "Titles use at most five words. On-slide copy uses at most 40 words. Every "
                "slide contains one idea. Numerical or performance claims must come from key "
                "points or source brief. Avoid filler transitions such as keep reading."
            ),
            examples=self.examples(request.topic),
        )
        return self.runner.run(
            agent=self.name,
            envelope=envelope,
            output_model=CarouselResult,
            deterministic_validator=lambda result: self.validate(result, request),
        )

    def validate(
        self,
        result: CarouselResult,
        request: CarouselRequest,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if len(result.slides) != request.slide_count:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.MAJOR,
                    code="wrong_slide_count",
                    message=f"Expected {request.slide_count} slides.",
                    path="slides",
                )
            )
        numbers = [slide.slide_number for slide in result.slides]
        if numbers != list(range(1, len(result.slides) + 1)):
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.MAJOR,
                    code="slide_sequence",
                    message="Slide numbers must be consecutive and ordered.",
                    path="slides",
                )
            )
        supplied = " ".join(
            [request.topic, *request.key_points, request.source_brief or ""]
        )
        supplied_numbers = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", supplied))
        output_numbers = set(
            re.findall(
                r"\b\d+(?:\.\d+)?%?\b",
                " ".join(
                    f"{slide.title} {slide.on_slide_copy} {slide.evidence or ''}"
                    for slide in result.slides
                ),
            )
        )
        structural_numbers = {str(index) for index in range(1, request.slide_count + 1)}
        invented = output_numbers - supplied_numbers - structural_numbers
        if invented:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.CRITICAL,
                    code="invented_number",
                    message=f"Unsupported numbers found: {sorted(invented)}",
                    path="slides",
                )
            )
        forbidden_claims = ("61 seconds", "algorithm threshold", "guaranteed reach")
        serialized = result.model_dump_json().lower()
        for phrase in forbidden_claims:
            if phrase in serialized:
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.MAJOR,
                        code="unsupported_platform_claim",
                        message=f"Unsupported platform claim: {phrase}",
                    )
                )
        if any(
            slide.transition_hook.strip().lower() in {"keep reading", "swipe"}
            for slide in result.slides
        ):
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.WARNING,
                    code="weak_transition",
                    message="Replace generic transition hooks with information gaps.",
                    path="slides",
                )
            )
        return issues


def render_marp(result: CarouselResult) -> str:
    slides = []
    for slide in result.slides:
        evidence = f"\n\n> Evidence: {slide.evidence}" if slide.evidence else ""
        slides.append(
            f"# {slide.title}\n\n{slide.on_slide_copy}{evidence}\n\n"
            f"*{slide.transition_hook}*"
        )
    return (
        "---\nmarp: true\ntheme: default\npaginate: true\n---\n\n"
        + "\n\n---\n\n".join(slides)
        + "\n"
    )
