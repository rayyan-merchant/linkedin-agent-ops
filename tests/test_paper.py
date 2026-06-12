from linkedin_agent_ops.agent_models import IssueSeverity
from linkedin_agent_ops.agents.paper import (
    EvidenceClaim,
    PaperAgent,
    PaperBriefResult,
    PaperDocument,
    PaperMetadata,
    PaperPage,
    ReportedMetric,
)
from linkedin_agent_ops.context import CreatorProfile


def agent():
    return PaperAgent(
        runner=None,
        profile=CreatorProfile({"positioning": "AI engineer"}),
        examples_path="missing",
    )


def result(metric_value="24 ms", metric_quote="Inference takes 24 ms."):
    return PaperBriefResult(
        metadata=PaperMetadata(title="Paper", source="upload"),
        core_contribution=EvidenceClaim(
            statement="A method is introduced.",
            page=1,
            evidence_quote="We introduce a method.",
        ),
        key_findings=[
            EvidenceClaim(
                statement=f"Finding {word}",
                page=1,
                evidence_quote="The model is evaluated.",
            )
            for word in ("one", "two", "three")
        ],
        ablations=[],
        hardware_and_efficiency=[
            ReportedMetric(name="VRAM", reported=False),
            ReportedMetric(name="training time", reported=False),
            ReportedMetric(
                name="inference latency",
                reported=True,
                value=metric_value,
                page=1,
                evidence_quote=metric_quote,
            ),
            ReportedMetric(name="parameter count", reported=False),
        ],
        limitations=[
            EvidenceClaim(
                statement="Evaluation is limited.",
                page=1,
                evidence_quote="The model is evaluated.",
            )
        ],
        practitioner_implications=["Validate latency.", "Check data.", "Compare baselines."],
        hook_angles=["a", "b", "c", "d", "e"],
        so_what="The method warrants a controlled production evaluation.",
    )


def test_paper_validation_accepts_grounded_quotes_and_numbers():
    document = PaperDocument(
        title="Paper",
        source="upload",
        pages=[
            PaperPage(
                1,
                "We introduce a method. The model is evaluated. Inference takes 24 ms.",
            )
        ],
    )
    assert agent().validate(result(), document) == []


def test_paper_validation_rejects_unsupported_metric_number():
    document = PaperDocument(
        title="Paper",
        source="upload",
        pages=[
            PaperPage(
                1,
                "We introduce a method. The model is evaluated. Inference takes 24 ms.",
            )
        ],
    )
    issues = agent().validate(result(metric_value="12 ms"), document)
    assert any(
        issue.code == "unsupported_metric_value"
        and issue.severity == IssueSeverity.CRITICAL
        for issue in issues
    )
