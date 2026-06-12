from __future__ import annotations

import copy
import json
import logging
import re
import time
from datetime import date, datetime
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from linkedin_agent_ops.models import (
    BriefItem,
    ContentOpportunity,
    DailyBrief,
    SourceItem,
)
from linkedin_agent_ops.ranking import section_for
from linkedin_agent_ops.utils import clean_text

LOGGER = logging.getLogger(__name__)


class GeneratedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    summary: str = Field(min_length=10, max_length=500)
    post_angle: str = Field(min_length=10, max_length=500)


class GeneratedOpportunity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=5, max_length=200)
    rationale: str = Field(min_length=10, max_length=600)
    post_angle: str = Field(min_length=10, max_length=600)
    source_ids: list[str] = Field(min_length=1, max_length=4)


class GeneratedBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[GeneratedItem]
    opportunity: GeneratedOpportunity


class StructuredProvider(Protocol):
    name: str

    def generate(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]: ...


def gemini_model_names(models_config: dict[str, Any]) -> list[str]:
    configured = models_config.get("gemini", [])
    names = [configured] if isinstance(configured, str) else list(configured)
    fallback = models_config.get("gemini_fallback")
    if fallback:
        names.append(fallback)
    unique = []
    for name in names:
        if name and name not in unique:
            unique.append(name)
    return unique


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        client: httpx.Client,
        api_key: str,
        model: str,
        *,
        attempts: int = 2,
    ) -> None:
        self.client = client
        self.api_key = api_key
        self.model = model
        self.name = f"gemini:{model}"
        self.attempts = attempts

    def generate(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
            },
        }
        last_error: Exception | None = None
        for attempt in range(self.attempts):
            try:
                response = self.client.post(
                    endpoint,
                    params={"key": self.api_key},
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
                text = body["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text)
            except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as exc:
                last_error = exc
                _wait_before_retry(exc, attempt, self.attempts)
        raise RuntimeError(
            f"Gemini generation failed: {_safe_provider_error(last_error)}"
        )


class GroqProvider:
    name = "groq"

    def __init__(
        self,
        client: httpx.Client,
        api_key: str,
        model: str,
        *,
        attempts: int = 2,
    ) -> None:
        self.client = client
        self.api_key = api_key
        self.model = model
        self.name = f"groq:{model}"
        self.attempts = attempts

    def generate(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Follow the trusted role and task in the user prompt. Produce factual "
                        "structured JSON grounded only in the supplied evidence."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "daily_ai_brief",
                    "strict": True,
                    "schema": _groq_strict_schema(schema),
                },
            },
        }
        last_error: Exception | None = None
        for attempt in range(self.attempts):
            try:
                response = self.client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                text = response.json()["choices"][0]["message"]["content"]
                return json.loads(text)
            except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as exc:
                last_error = exc
                _wait_before_retry(exc, attempt, self.attempts)
        raise RuntimeError(
            f"Groq generation failed: {_safe_provider_error(last_error)}"
        )


def _safe_provider_error(error: Exception | None) -> str:
    if error is None:
        return "unknown provider error"
    if isinstance(error, httpx.HTTPStatusError):
        return f"HTTP {error.response.status_code}"
    if isinstance(error, httpx.RequestError):
        return error.__class__.__name__
    if isinstance(error, (KeyError, IndexError, json.JSONDecodeError)):
        return f"invalid provider response ({error.__class__.__name__})"
    return error.__class__.__name__


def _groq_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    strict_schema = copy.deepcopy(schema)

    def normalize(node: Any) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["required"] = list(properties)
                node["additionalProperties"] = False
            for value in node.values():
                normalize(value)
        elif isinstance(node, list):
            for value in node:
                normalize(value)

    normalize(strict_schema)
    return strict_schema


def _wait_before_retry(error: Exception, attempt: int, attempts: int) -> None:
    if attempt >= attempts - 1:
        return
    delay = min(2**attempt, 8)
    if isinstance(error, httpx.HTTPStatusError):
        if error.response.status_code not in {429, 500, 502, 503, 504}:
            return
        delay = _provider_retry_delay(error.response.headers) or delay
    elif not isinstance(error, httpx.RequestError):
        return
    time.sleep(min(delay, 60))


def _provider_retry_delay(headers: httpx.Headers) -> float | None:
    retry_after = headers.get("retry-after")
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            pass
    for name in ("x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"):
        value = headers.get(name)
        if not value:
            continue
        parts = re.findall(r"(\d+(?:\.\d+)?)(ms|s|m|h)", value.lower())
        if parts:
            units = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
            return sum(float(amount) * units[unit] for amount, unit in parts)
    return None


class BriefGenerator:
    def __init__(
        self,
        providers: list[StructuredProvider],
        *,
        now_fn,
    ) -> None:
        self.providers = providers
        self.now_fn = now_fn

    def generate(
        self,
        *,
        items: list[SourceItem],
        brief_date: date,
        counts: tuple[int, int, int],
    ) -> DailyBrief:
        prompt = build_prompt(items)
        schema = GeneratedBrief.model_json_schema()
        for provider in self.providers:
            try:
                generated = GeneratedBrief.model_validate(
                    provider.generate(prompt, schema)
                )
                return assemble_brief(
                    items=items,
                    generated=generated,
                    brief_date=brief_date,
                    generated_at=self.now_fn(),
                    model_used=provider.name,
                    degraded=len(items) < sum(counts),
                )
            except (RuntimeError, ValidationError, ValueError) as exc:
                LOGGER.warning("%s failed: %s", provider.name, exc)

        return deterministic_brief(
            items=items,
            brief_date=brief_date,
            generated_at=self.now_fn(),
            degraded=True,
        )


def build_prompt(items: list[SourceItem]) -> str:
    candidates = [
        {
            "source_id": item.source_id,
            "section": section_for(item).value,
            "source": item.source_name,
            "title": item.title,
            "category": item.category,
            "published_at": item.published_at.isoformat(),
            "excerpt": item.excerpt,
            "metrics": item.metrics,
            "url": item.url,
        }
        for item in items
    ]
    return (
        "Create a concise daily intelligence brief for an AI engineer focused on "
        "computer vision, agentic AI, MLOps, RAG, deployment, research-to-production, "
        "and cricket computer vision.\n\n"
        "For every candidate, return exactly one item using the same source_id. "
        "The summary must state what happened in plain language. The post_angle must "
        "be an input for human writing, not a finished LinkedIn post. Never invent "
        "numbers, performance claims, or details absent from the candidate. Create one "
        "content opportunity connecting one to four candidates and cite their source_ids. "
        "Use blunt, engineer-focused language and no marketing filler.\n\n"
        f"Candidates:\n{json.dumps(candidates, ensure_ascii=True)}"
    )


def assemble_brief(
    *,
    items: list[SourceItem],
    generated: GeneratedBrief,
    brief_date: date,
    generated_at: datetime,
    model_used: str,
    degraded: bool,
) -> DailyBrief:
    source_by_id = {item.source_id: item for item in items}
    if len(source_by_id) != len(items):
        raise ValueError("Candidate source IDs must be unique")
    generated_by_id = {item.source_id: item for item in generated.items}
    if set(generated_by_id) != set(source_by_id):
        raise ValueError("Generated item IDs do not match candidate IDs")
    if len(generated_by_id) != len(generated.items):
        raise ValueError("Generated item IDs must be unique")

    brief_items = []
    for source in items:
        output = generated_by_id[source.source_id]
        brief_items.append(
            BriefItem(
                source_id=source.source_id,
                section=section_for(source),
                source=source.source,
                source_name=source.source_name,
                category=source.category,
                title=source.title,
                url=source.url,
                published_at=source.published_at,
                summary=clean_text(output.summary),
                post_angle=clean_text(output.post_angle),
                score=source.score,
            )
        )

    invalid_opportunity_ids = set(generated.opportunity.source_ids) - set(source_by_id)
    if invalid_opportunity_ids:
        raise ValueError("Content opportunity references unknown candidates")
    source_urls = [
        source_by_id[source_id].url
        for source_id in generated.opportunity.source_ids
    ]
    opportunity = ContentOpportunity(
        title=clean_text(generated.opportunity.title),
        rationale=clean_text(generated.opportunity.rationale),
        post_angle=clean_text(generated.opportunity.post_angle),
        source_urls=source_urls,
    )
    return _daily_brief(
        brief_items=brief_items,
        opportunity=opportunity,
        brief_date=brief_date,
        generated_at=generated_at,
        model_used=model_used,
        degraded=degraded,
    )


def deterministic_brief(
    *,
    items: list[SourceItem],
    brief_date: date,
    generated_at: datetime,
    degraded: bool,
) -> DailyBrief:
    brief_items = []
    for source in items:
        summary = _first_sentence(source.excerpt) or (
            f"{source.title} was published by {source.source_name}."
        )
        brief_items.append(
            BriefItem(
                source_id=source.source_id,
                section=section_for(source),
                source=source.source,
                source_name=source.source_name,
                category=source.category,
                title=source.title,
                url=source.url,
                published_at=source.published_at,
                summary=summary,
                post_angle=(
                    "Assess the practical tradeoffs, evidence, and what a production "
                    "AI team would need to validate before adopting this."
                ),
                score=source.score,
            )
        )
    strongest = items[:2]
    opportunity = ContentOpportunity(
        title="Connect today's strongest research and builder signal",
        rationale=(
            "The highest-ranked items can be compared through a practical "
            "research-to-production lens."
        ),
        post_angle=(
            "Contrast the headline promise with the implementation evidence an "
            "engineering team should demand."
        ),
        source_urls=[item.url for item in strongest],
    )
    return _daily_brief(
        brief_items=brief_items,
        opportunity=opportunity,
        brief_date=brief_date,
        generated_at=generated_at,
        model_used="deterministic",
        degraded=degraded,
    )


def _daily_brief(
    *,
    brief_items: list[BriefItem],
    opportunity: ContentOpportunity,
    brief_date: date,
    generated_at: datetime,
    model_used: str,
    degraded: bool,
) -> DailyBrief:
    return DailyBrief(
        brief_date=brief_date,
        generated_at=generated_at,
        papers=[item for item in brief_items if item.section.value == "papers"],
        trends=[item for item in brief_items if item.section.value == "trends"],
        repositories=[
            item for item in brief_items if item.section.value == "repositories"
        ],
        opportunity=opportunity,
        model_used=model_used,
        degraded=degraded,
    )


def _first_sentence(value: str) -> str:
    text = clean_text(value, limit=350)
    for marker in (". ", "? ", "! "):
        if marker in text:
            return f"{text.split(marker, 1)[0]}{marker.strip()}"
    return text
