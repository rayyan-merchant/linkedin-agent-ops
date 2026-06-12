from __future__ import annotations

import io
import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pypdf import PdfReader

from linkedin_agent_ops.agent_models import (
    AgentResponse,
    IssueSeverity,
    ValidationIssue,
)
from linkedin_agent_ops.agents.base import BaseAgent
from linkedin_agent_ops.prompting import PromptEnvelope
from linkedin_agent_ops.utils import clean_text

ARXIV_PATTERN = re.compile(
    r"^/(?:abs|pdf)/(?P<identifier>[a-z\-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?$",
    re.IGNORECASE,
)


class PaperInputError(ValueError):
    pass


@dataclass(frozen=True)
class PaperPage:
    number: int
    text: str


@dataclass(frozen=True)
class PaperDocument:
    title: str
    source: str
    pages: list[PaperPage]

    @property
    def text_length(self) -> int:
        return sum(len(page.text) for page in self.pages)

    def evidence_text(self) -> str:
        return "\n\n".join(
            f"[PAGE {page.number}]\n{page.text}" for page in self.pages
        )


class EvidenceClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str
    page: int = Field(ge=1)
    evidence_quote: str = Field(min_length=3, max_length=600)


class ReportedMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    reported: bool
    value: str | None = None
    page: int | None = Field(default=None, ge=1)
    evidence_quote: str | None = Field(default=None, max_length=600)

    @model_validator(mode="after")
    def reported_requires_evidence(self):
        if self.reported and not all([self.value, self.page, self.evidence_quote]):
            raise ValueError("reported metrics require value, page, and evidence_quote")
        if not self.reported and self.value is not None:
            raise ValueError("unreported metrics cannot have a value")
        return self


class ConnectionKind(StrEnum):
    STATED = "stated"
    INFERRED = "inferred"


class TechniqueConnection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    technique: str
    connection: str
    kind: ConnectionKind
    page: int | None = Field(default=None, ge=1)


class PaperMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    authors: list[str] = Field(default_factory=list)
    publication_or_version: str = "not reported"
    source: str


class PaperBriefResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: PaperMetadata
    core_contribution: EvidenceClaim
    key_findings: list[EvidenceClaim] = Field(min_length=3, max_length=7)
    ablations: list[EvidenceClaim] = Field(default_factory=list)
    hardware_and_efficiency: list[ReportedMetric] = Field(min_length=4)
    limitations: list[EvidenceClaim] = Field(min_length=1)
    practitioner_implications: list[str] = Field(min_length=3, max_length=7)
    technique_connections: list[TechniqueConnection] = Field(default_factory=list)
    hook_angles: list[str] = Field(min_length=5, max_length=5)
    evidence_gaps: list[str] = Field(default_factory=list)
    so_what: str


class ChunkEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata_clues: list[str] = Field(default_factory=list)
    contributions: list[EvidenceClaim] = Field(default_factory=list)
    findings: list[EvidenceClaim] = Field(default_factory=list)
    ablations: list[EvidenceClaim] = Field(default_factory=list)
    metrics: list[EvidenceClaim] = Field(default_factory=list)
    limitations: list[EvidenceClaim] = Field(default_factory=list)


class PaperExtractor:
    def __init__(
        self,
        client: httpx.Client,
        *,
        max_bytes: int = 20 * 1024 * 1024,
        max_pages: int = 100,
    ) -> None:
        self.client = client
        self.max_bytes = max_bytes
        self.max_pages = max_pages

    def from_arxiv(self, url: str) -> PaperDocument:
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in {"arxiv.org", "www.arxiv.org"}:
            raise PaperInputError("Only HTTPS arXiv URLs are supported")
        match = ARXIV_PATTERN.match(parts.path)
        if not match:
            raise PaperInputError("Invalid arXiv abstract or PDF URL")
        identifier = match.group("identifier")
        response = self.client.get(f"https://arxiv.org/pdf/{identifier}.pdf")
        response.raise_for_status()
        return self.from_bytes(
            response.content,
            filename=f"{identifier}.pdf",
            source=f"https://arxiv.org/abs/{identifier}",
        )

    def from_bytes(
        self,
        content: bytes,
        *,
        filename: str,
        source: str = "uploaded PDF",
    ) -> PaperDocument:
        if len(content) > self.max_bytes:
            raise PaperInputError("PDF exceeds the 20 MB limit")
        if not content.startswith(b"%PDF"):
            raise PaperInputError("Input is not a valid PDF")
        try:
            reader = PdfReader(io.BytesIO(content))
        except Exception as exc:
            raise PaperInputError("PDF could not be parsed") from exc
        if reader.is_encrypted:
            raise PaperInputError("Encrypted PDFs are not supported")
        if len(reader.pages) > self.max_pages:
            raise PaperInputError(f"PDF exceeds the {self.max_pages}-page limit")
        pages = [
            PaperPage(index, clean_text(page.extract_text() or ""))
            for index, page in enumerate(reader.pages, start=1)
        ]
        total_text = sum(len(page.text) for page in pages)
        if total_text < max(300, len(pages) * 40):
            raise PaperInputError(
                "PDF has too little extractable text; scanned PDFs require OCR"
            )
        return PaperDocument(title=filename.rsplit(".", 1)[0], source=source, pages=pages)


class PaperAgent(BaseAgent):
    name = "paper"

    def __init__(
        self,
        *,
        direct_context_chars: int = 120000,
        chunk_chars: int = 30000,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.direct_context_chars = direct_context_chars
        self.chunk_chars = chunk_chars

    def generate(self, document: PaperDocument) -> AgentResponse[PaperBriefResult]:
        evidence: str | list[dict]
        if document.text_length <= self.direct_context_chars:
            evidence = document.evidence_text()
        else:
            evidence = [
                chunk.result.model_dump(mode="json")
                for chunk in self._extract_chunks(document)
            ]
        envelope = PromptEnvelope(
            role=(
                "You are a research analyst for practitioners building production computer "
                "vision, agentic AI, MLOps, and RAG systems. You produce evidence-led briefs, "
                "not finished social posts."
            ),
            creator_context=self.context(),
            task=(
                "Analyze the complete supplied paper evidence. Report metadata, one core "
                "contribution, 3-7 key findings, ablations, limitations, practitioner actions, "
                "technique connections, exactly five hook angles, evidence gaps, and a concise "
                "so-what. Include page references and short evidence quotes for factual claims. "
                "For hardware, VRAM, training time, inference latency, and parameter count, "
                "create explicit entries and set reported=false when absent. Mark technique "
                "connections as stated or inferred."
            ),
            evidence=evidence,
            rubric=(
                "Never infer a number or result. Quotes must occur on the cited page. Distinguish "
                "paper claims from your practitioner inference. Avoid abstract-only summaries, "
                "marketing language, and complete post copy."
            ),
        )
        return self.runner.run(
            agent=self.name,
            envelope=envelope,
            output_model=PaperBriefResult,
            deterministic_validator=lambda result: self.validate(result, document),
        )

    def _extract_chunks(
        self, document: PaperDocument
    ) -> list[AgentResponse[ChunkEvidence]]:
        chunks: list[list[PaperPage]] = []
        current: list[PaperPage] = []
        size = 0
        for page in document.pages:
            if current and size + len(page.text) > self.chunk_chars:
                chunks.append(current)
                current = []
                size = 0
            current.append(page)
            size += len(page.text)
        if current:
            chunks.append(current)

        results = []
        for pages in chunks:
            evidence = "\n\n".join(
                f"[PAGE {page.number}]\n{page.text}" for page in pages
            )
            envelope = PromptEnvelope(
                role="You extract evidence from one paper chunk without interpretation.",
                creator_context=self.context(),
                task=(
                    "Extract metadata clues, contributions, findings, ablations, reported "
                    "metrics, and limitations. Every claim requires its real page and a short "
                    "verbatim evidence quote. Omit anything not present."
                ),
                evidence=evidence,
                rubric="Do not synthesize across missing pages or add outside knowledge.",
            )
            results.append(
                self.runner.run(
                    agent="paper_chunk",
                    envelope=envelope,
                    output_model=ChunkEvidence,
                    deterministic_validator=lambda result: self._validate_chunk(
                        result, document
                    ),
                )
            )
        return results

    def validate(
        self,
        result: PaperBriefResult,
        document: PaperDocument,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        claims = [
            result.core_contribution,
            *result.key_findings,
            *result.ablations,
            *result.limitations,
        ]
        for index, claim in enumerate(claims):
            issues.extend(self._validate_claim(claim, document, f"claims.{index}"))
        required_metrics = {
            "vram",
            "training time",
            "inference latency",
            "parameter count",
        }
        metric_names = {metric.name.lower() for metric in result.hardware_and_efficiency}
        missing = required_metrics - metric_names
        if missing:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.MAJOR,
                    code="missing_metric_status",
                    message=f"Missing explicit reported/not-reported entries: {sorted(missing)}",
                    path="hardware_and_efficiency",
                )
            )
        for index, metric in enumerate(result.hardware_and_efficiency):
            if metric.reported:
                claim = EvidenceClaim(
                    statement=f"{metric.name}: {metric.value}",
                    page=metric.page or 1,
                    evidence_quote=metric.evidence_quote or "",
                )
                issues.extend(
                    self._validate_claim(
                        claim,
                        document,
                        f"hardware_and_efficiency.{index}",
                    )
                )
                value_numbers = set(re.findall(r"\d+(?:\.\d+)?", metric.value or ""))
                quote_numbers = set(
                    re.findall(r"\d+(?:\.\d+)?", metric.evidence_quote or "")
                )
                if value_numbers - quote_numbers:
                    issues.append(
                        ValidationIssue(
                            severity=IssueSeverity.CRITICAL,
                            code="unsupported_metric_value",
                            message=f"Metric value is not supported by its quote: {metric.value}",
                            path=f"hardware_and_efficiency.{index}",
                        )
                    )
        document_numbers = set(
            re.findall(
                r"\d+(?:\.\d+)?",
                " ".join(page.text for page in document.pages),
            )
        )
        narrative_numbers = set(
            re.findall(
                r"\d+(?:\.\d+)?",
                " ".join(
                    [
                        *result.practitioner_implications,
                        *result.hook_angles,
                        result.so_what,
                        *[
                            connection.connection
                            for connection in result.technique_connections
                        ],
                    ]
                ),
            )
        )
        unsupported_narrative = narrative_numbers - document_numbers
        if unsupported_narrative:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.CRITICAL,
                    code="unsupported_narrative_number",
                    message=(
                        "Narrative contains numbers absent from the paper: "
                        f"{sorted(unsupported_narrative)}"
                    ),
                )
            )
        return issues

    def _validate_chunk(
        self,
        result: ChunkEvidence,
        document: PaperDocument,
    ) -> list[ValidationIssue]:
        claims = [
            *result.contributions,
            *result.findings,
            *result.ablations,
            *result.metrics,
            *result.limitations,
        ]
        issues = []
        for index, claim in enumerate(claims):
            issues.extend(self._validate_claim(claim, document, f"claims.{index}"))
        return issues

    @staticmethod
    def _validate_claim(
        claim: EvidenceClaim,
        document: PaperDocument,
        path: str,
    ) -> list[ValidationIssue]:
        if claim.page > len(document.pages):
            return [
                ValidationIssue(
                    severity=IssueSeverity.CRITICAL,
                    code="invalid_page",
                    message=f"Cited page {claim.page} does not exist.",
                    path=path,
                )
            ]
        page_text = document.pages[claim.page - 1].text.lower()
        quote = clean_text(claim.evidence_quote).lower()
        if quote not in page_text:
            return [
                ValidationIssue(
                    severity=IssueSeverity.CRITICAL,
                    code="quote_not_on_page",
                    message="Evidence quote was not found on the cited page.",
                    path=path,
                )
            ]
        statement_numbers = set(re.findall(r"\d+(?:\.\d+)?", claim.statement))
        quote_numbers = set(re.findall(r"\d+(?:\.\d+)?", claim.evidence_quote))
        if statement_numbers - quote_numbers:
            return [
                ValidationIssue(
                    severity=IssueSeverity.CRITICAL,
                    code="unsupported_claim_number",
                    message="Claim contains a number absent from its evidence quote.",
                    path=path,
                )
            ]
        return []
