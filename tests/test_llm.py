import json
from datetime import UTC, date, datetime

import httpx
import pytest

from linkedin_agent_ops.llm import (
    BriefGenerator,
    GeminiProvider,
    GroqProvider,
    _groq_strict_schema,
    gemini_model_names,
)
from linkedin_agent_ops.models import SourceItem, SourceKind


class FailedProvider:
    name = "failed"

    def generate(self, prompt, schema):
        raise RuntimeError("unavailable")


class GoodProvider:
    name = "good"

    def generate(self, prompt, schema):
        candidates = json.loads(prompt.split("Candidates:\n", 1)[1])
        return {
            "items": [
                {
                    "source_id": item["source_id"],
                    "summary": f"A factual summary for {item['title']}.",
                    "post_angle": "Explain what a production team should validate first.",
                }
                for item in candidates
            ],
            "opportunity": {
                "title": "Compare research with production evidence",
                "rationale": "The selected items expose a useful implementation gap.",
                "post_angle": "Show which claims need testing before adoption.",
                "source_ids": [candidates[0]["source_id"]],
            },
        }


def source_item():
    return SourceItem(
        source_id="paper-1",
        source=SourceKind.ARXIV,
        source_name="arXiv",
        title="A useful vision paper",
        url="https://arxiv.org/abs/1",
        published_at=datetime(2026, 6, 11, tzinfo=UTC),
        excerpt="The paper reports a practical computer vision method.",
        category="cs.CV",
        score=80,
    )


def test_generator_falls_back_to_second_provider():
    generator = BriefGenerator(
        [FailedProvider(), GoodProvider()],
        now_fn=lambda: datetime(2026, 6, 12, tzinfo=UTC),
    )
    brief = generator.generate(
        items=[source_item()],
        brief_date=date(2026, 6, 12),
        counts=(1, 0, 0),
    )
    assert brief.model_used == "good"
    assert brief.papers[0].summary.startswith("A factual summary")


def test_generator_uses_deterministic_fallback():
    generator = BriefGenerator(
        [FailedProvider()],
        now_fn=lambda: datetime(2026, 6, 12, tzinfo=UTC),
    )
    brief = generator.generate(
        items=[source_item()],
        brief_date=date(2026, 6, 12),
        counts=(1, 0, 0),
    )
    assert brief.model_used == "deterministic"
    assert brief.degraded is True


def test_gemini_model_names_include_configured_fallback_once():
    assert gemini_model_names(
        {
            "gemini": "gemini-3.5-flash",
            "gemini_fallback": "gemini-2.5-pro",
        }
    ) == ["gemini-3.5-flash", "gemini-2.5-pro"]

    assert gemini_model_names(
        {
            "gemini": ["gemini-3.5-flash", "gemini-2.5-pro"],
            "gemini_fallback": "gemini-2.5-pro",
        }
    ) == ["gemini-3.5-flash", "gemini-2.5-pro"]


def test_gemini_error_does_not_expose_api_key():
    def fail(request):
        return httpx.Response(503, request=request)

    provider = GeminiProvider(
        httpx.Client(transport=httpx.MockTransport(fail)),
        "super-secret-key",
        "gemini-test",
        attempts=1,
    )

    with pytest.raises(RuntimeError) as exc_info:
        provider.generate("prompt", {"type": "object"})

    message = str(exc_info.value)
    assert "HTTP 503" in message
    assert "super-secret-key" not in message
    assert "?key=" not in message


def test_groq_normalizes_optional_fields_for_strict_schema():
    def respond(request):
        payload = json.loads(request.content)
        response_format = payload["response_format"]["json_schema"]
        assert response_format["strict"] is True
        assert response_format["schema"]["required"] == ["value", "details"]
        assert response_format["schema"]["additionalProperties"] is False
        assert response_format["schema"]["properties"]["details"]["required"] == [
            "note"
        ]
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"value":"ok","details":{"note":null}}'
                        }
                    }
                ]
            },
        )

    provider = GroqProvider(
        httpx.Client(transport=httpx.MockTransport(respond)),
        "groq-secret",
        "openai/gpt-oss-120b",
        attempts=1,
    )

    assert provider.generate(
        "prompt",
        {
            "type": "object",
            "properties": {
                "value": {"type": "string"},
                "details": {
                    "type": "object",
                    "properties": {
                        "note": {
                            "anyOf": [{"type": "string"}, {"type": "null"}],
                            "default": None,
                        }
                    },
                },
            },
            "required": ["value"],
        },
    ) == {"value": "ok", "details": {"note": None}}


def test_groq_schema_normalization_does_not_mutate_input():
    schema = {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": [],
    }

    normalized = _groq_strict_schema(schema)

    assert schema["required"] == []
    assert "additionalProperties" not in schema
    assert normalized["required"] == ["value"]
    assert normalized["additionalProperties"] is False


def test_groq_retries_rate_limit_using_retry_header():
    calls = 0

    def respond(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                429,
                request=request,
                headers={"Retry-After": "0"},
            )
        return httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": '{"value":"ok"}'}}]},
        )

    provider = GroqProvider(
        httpx.Client(transport=httpx.MockTransport(respond)),
        "groq-secret",
        "openai/gpt-oss-120b",
        attempts=2,
    )

    result = provider.generate(
        "prompt",
        {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
    )

    assert result == {"value": "ok"}
    assert calls == 2
