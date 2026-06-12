from types import SimpleNamespace

from fastapi.testclient import TestClient

from linkedin_agent_ops.api import create_app


def services():
    return SimpleNamespace(
        store=None,
        post_architecture=None,
        paper=None,
        paper_extractor=None,
        carousel=None,
        performance=None,
        cricket=None,
    )


def test_health_does_not_require_secrets():
    client = TestClient(create_app(services()))
    assert client.get("/health").json() == {"status": "ok"}


def test_paper_requires_exactly_one_input():
    client = TestClient(create_app(services()))
    response = client.post("/agents/paper", data={})
    assert response.status_code == 422
    assert "exactly one" in response.json()["detail"]


def test_history_is_empty_without_sheets():
    client = TestClient(create_app(services()))
    assert client.get("/history").json() == []

