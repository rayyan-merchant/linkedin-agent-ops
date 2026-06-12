from pydantic import BaseModel

from linkedin_agent_ops.agent_models import IssueSeverity, ValidationIssue
from linkedin_agent_ops.agent_runner import StructuredAgentRunner
from linkedin_agent_ops.prompting import PromptEnvelope


class Output(BaseModel):
    value: str


class RepairingProvider:
    name = "fake"

    def __init__(self):
        self.calls = 0

    def generate(self, prompt, schema):
        self.calls += 1
        if "strict evidence and quality auditor" in prompt:
            return {"issues": []}
        if "previous candidate output" in prompt:
            return {"value": "grounded"}
        return {"value": "bad"}


def test_runner_repairs_major_deterministic_issue_once():
    provider = RepairingProvider()
    runner = StructuredAgentRunner([provider])

    def validate(output):
        if output.value == "bad":
            return [
                ValidationIssue(
                    severity=IssueSeverity.MAJOR,
                    code="bad",
                    message="Needs repair.",
                )
            ]
        return []

    response = runner.run(
        agent="test",
        envelope=PromptEnvelope(
            role="role",
            creator_context="context",
            task="task",
            evidence="evidence",
            rubric="rubric",
        ),
        output_model=Output,
        deterministic_validator=validate,
    )
    assert response.result.value == "grounded"
    assert response.metadata.validation.repaired is True
    assert response.metadata.validation.passed is True


def test_runner_flags_copied_example_wording():
    class CopyProvider:
        name = "copy"

        def generate(self, prompt, schema):
            if "strict evidence and quality auditor" in prompt:
                return {"issues": []}
            return {"value": "one two three four five six seven eight"}

    response = StructuredAgentRunner([CopyProvider()]).run(
        agent="test",
        envelope=PromptEnvelope(
            role="role",
            creator_context="context",
            task="task",
            evidence="evidence",
            rubric="rubric",
            examples=["one two three four five six seven eight nine"],
        ),
        output_model=Output,
        deterministic_validator=lambda output: [],
    )
    assert any(
        issue.code == "copied_example_wording"
        for issue in response.metadata.validation.issues
    )
