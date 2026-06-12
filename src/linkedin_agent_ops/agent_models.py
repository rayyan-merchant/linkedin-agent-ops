from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class IssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    MAJOR = "major"
    CRITICAL = "critical"


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: IssueSeverity
    code: str
    message: str
    path: str = ""


class ValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    repaired: bool = False
    issues: list[ValidationIssue] = Field(default_factory=list)

    def requires_repair(self) -> bool:
        return any(
            issue.severity in {IssueSeverity.MAJOR, IssueSeverity.CRITICAL}
            for issue in self.issues
        )


class AgentRunMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(default_factory=lambda: uuid4().hex)
    agent: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    model_used: str
    validation: ValidationReport


OutputT = TypeVar("OutputT")


class AgentResponse(BaseModel, Generic[OutputT]):
    model_config = ConfigDict(extra="forbid")

    result: OutputT
    metadata: AgentRunMetadata


class LlmValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issues: list[ValidationIssue] = Field(default_factory=list)


class AgentHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    agent: str
    created_at: datetime
    model_used: str
    passed: bool
    warnings: int
    summary: str
    result: dict[str, Any] | None = None

