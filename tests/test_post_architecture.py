from linkedin_agent_ops.agent_models import IssueSeverity
from linkedin_agent_ops.agents.post_architecture import (
    HookOption,
    PostArchitectureAgent,
    PostArchitectureRequest,
    PostArchitectureResult,
    PostFormat,
)
from linkedin_agent_ops.context import CreatorProfile


def agent():
    return PostArchitectureAgent(
        runner=None,
        profile=CreatorProfile(
            {
                "banned_language": ["game-changer"],
                "positioning": "AI engineer",
            }
        ),
        examples_path="missing",
    )


def valid_result():
    return PostArchitectureResult(
        format_recommendation=PostFormat.TEXT,
        format_reason="The idea benefits from a concise technical argument.",
        target_length="1,200-1,800 characters",
        hooks=[
            HookOption(angle=f"angle-{index}", lines=[f"Specific line {index}.", "Why it matters."])
            for index in range(7)
        ],
        outline=["Problem", "Constraint", "Evidence", "Tradeoff", "Takeaway"],
        discussion_prompts=["Question one?", "Question two?", "Question three?"],
        save_element="A decision checklist.",
        cta_guidance="Ask for concrete implementation experience.",
    )


def test_post_architecture_validator_flags_invented_number_and_language():
    result = valid_result().model_copy(
        update={
            "format_reason": "A game-changer with 99% improvement.",
        }
    )
    issues = agent().validate(
        result,
        PostArchitectureRequest(
            topic="Agent deployment",
            key_insight="Reliability depends on explicit failure handling.",
        ),
    )
    assert {issue.code for issue in issues} == {"banned_language", "invented_number"}
    assert IssueSeverity.CRITICAL in {issue.severity for issue in issues}

