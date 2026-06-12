from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from linkedin_agent_ops.agent_models import (
    AgentResponse,
    AgentRunMetadata,
    IssueSeverity,
    LlmValidationResult,
    ValidationIssue,
    ValidationReport,
)
from linkedin_agent_ops.llm import StructuredProvider
from linkedin_agent_ops.prompting import (
    PromptEnvelope,
    repair_prompt,
    validation_prompt,
)

LOGGER = logging.getLogger(__name__)
ModelT = TypeVar("ModelT", bound=BaseModel)
Validator = Callable[[BaseModel], list[ValidationIssue]]


class AgentGenerationError(RuntimeError):
    pass


class StructuredAgentRunner:
    def __init__(self, providers: list[StructuredProvider]) -> None:
        self.providers = providers

    def run(
        self,
        *,
        agent: str,
        envelope: PromptEnvelope,
        output_model: type[ModelT],
        deterministic_validator: Callable[[ModelT], list[ValidationIssue]],
    ) -> AgentResponse[ModelT]:
        schema = output_model.model_json_schema()
        errors = []
        for provider in self.providers:
            try:
                candidate = output_model.model_validate(
                    provider.generate(envelope.render(), schema)
                )
                deterministic = [
                    *deterministic_validator(candidate),
                    *_example_copy_issues(envelope.examples, candidate),
                ]
                llm_issues = self._audit(provider, envelope, candidate, schema)
                issues = _deduplicate_issues([*deterministic, *llm_issues])
                repaired = False
                if _requires_repair(issues):
                    candidate = output_model.model_validate(
                        provider.generate(
                            repair_prompt(
                                envelope,
                                candidate.model_dump(mode="json"),
                                [issue.model_dump(mode="json") for issue in issues],
                            ),
                            schema,
                        )
                    )
                    repaired = True
                    deterministic = [
                        *deterministic_validator(candidate),
                        *_example_copy_issues(envelope.examples, candidate),
                    ]
                    llm_issues = self._audit(provider, envelope, candidate, schema)
                    issues = _deduplicate_issues([*deterministic, *llm_issues])
                report = ValidationReport(
                    passed=not _requires_repair(issues),
                    repaired=repaired,
                    issues=issues,
                )
                return AgentResponse(
                    result=candidate,
                    metadata=AgentRunMetadata(
                        agent=agent,
                        model_used=provider.name,
                        validation=report,
                    ),
                )
            except (RuntimeError, ValidationError, ValueError, KeyError) as exc:
                LOGGER.warning("%s failed for %s: %s", provider.name, agent, exc)
                errors.append(f"{provider.name}: {exc}")
        raise AgentGenerationError("; ".join(errors) or "No LLM provider configured")

    @staticmethod
    def _audit(
        provider: StructuredProvider,
        envelope: PromptEnvelope,
        candidate: BaseModel,
        schema: dict[str, Any],
    ) -> list[ValidationIssue]:
        audit = LlmValidationResult.model_validate(
            provider.generate(
                validation_prompt(
                    envelope,
                    candidate.model_dump(mode="json"),
                    schema,
                ),
                LlmValidationResult.model_json_schema(),
            )
        )
        return audit.issues


def _requires_repair(issues: list[ValidationIssue]) -> bool:
    return any(
        issue.severity in {IssueSeverity.MAJOR, IssueSeverity.CRITICAL}
        for issue in issues
    )


def _deduplicate_issues(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    unique = {}
    for issue in issues:
        unique[(issue.code, issue.path, issue.message)] = issue
    return list(unique.values())


def _example_copy_issues(
    examples: list[str],
    candidate: BaseModel,
) -> list[ValidationIssue]:
    output_words = re.findall(r"[a-z0-9]+", candidate.model_dump_json().lower())
    output_sequences = {
        tuple(output_words[index : index + 8])
        for index in range(max(0, len(output_words) - 7))
    }
    for example in examples:
        words = re.findall(r"[a-z0-9]+", example.lower())
        for index in range(max(0, len(words) - 7)):
            if tuple(words[index : index + 8]) in output_sequences:
                return [
                    ValidationIssue(
                        severity=IssueSeverity.MAJOR,
                        code="copied_example_wording",
                        message="Output copies an eight-word sequence from a style example.",
                    )
                ]
    return []
