from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from linkedin_agent_ops.agent_models import (
    AgentHistoryItem,
    AgentResponse,
    AgentRunMetadata,
    ValidationReport,
)
from linkedin_agent_ops.agents.carousel import CarouselResult, CarouselSlide
from linkedin_agent_ops.agents.cricket import (
    CricketBuildLogResult,
    MetricChange,
)
from linkedin_agent_ops.agents.paper import (
    EvidenceClaim,
    PaperBriefResult,
    PaperDocument,
    PaperMetadata,
    PaperPage,
    ReportedMetric,
)
from linkedin_agent_ops.agents.performance import (
    EvidenceFinding,
    PerformanceResult,
    compute_analytics,
)
from linkedin_agent_ops.agents.post_architecture import (
    HookOption,
    PostArchitectureResult,
    PostFormat,
)
from linkedin_agent_ops.api import create_app


def response(agent, result):
    return AgentResponse(
        result=result,
        metadata=AgentRunMetadata(
            agent=agent,
            model_used="fake",
            validation=ValidationReport(passed=True),
        ),
    )


def post_result():
    return PostArchitectureResult(
        format_recommendation=PostFormat.TEXT,
        format_reason="A concise technical argument fits the supplied evidence.",
        target_length="1,200-1,800 characters",
        hooks=[
            HookOption(
                angle=f"angle-{index}",
                lines=[f"Specific line {index}.", "The evidence changes the decision."],
            )
            for index in range(7)
        ],
        outline=["Problem", "Constraint", "Evidence", "Tradeoff", "Decision"],
        discussion_prompts=["Question one?", "Question two?", "Question three?"],
        save_element="A reliability checklist.",
        cta_guidance="Ask for concrete implementation experience.",
    )


def paper_result():
    return PaperBriefResult(
        metadata=PaperMetadata(title="Paper", source="upload"),
        core_contribution=EvidenceClaim(
            statement="A method is introduced.",
            page=1,
            evidence_quote="We introduce a method.",
        ),
        key_findings=[
            EvidenceClaim(
                statement=f"Finding {index}",
                page=1,
                evidence_quote="The model is evaluated.",
            )
            for index in range(3)
        ],
        ablations=[],
        hardware_and_efficiency=[
            ReportedMetric(name=name, reported=False)
            for name in ("VRAM", "training time", "inference latency", "parameter count")
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


def carousel_result():
    return CarouselResult(
        narrative_strategy="Move from production problem to practical decision.",
        slides=[
            CarouselSlide(
                slide_number=index,
                title=f"Slide {index}",
                on_slide_copy="One focused production idea.",
                core_message="The reader understands one decision.",
                visual_recommendation="Simple architecture diagram.",
                transition_hook="The next constraint changes the choice.",
            )
            for index in range(1, 9)
        ],
        design_guidance=["One visual.", "High contrast.", "Consistent hierarchy."],
    )


def performance_result(post_ids):
    return PerformanceResult(
        executive_summary="The sample supports directional decisions.",
        findings=[
            EvidenceFinding(
                finding=f"Finding {index}",
                post_ids=[post_ids[index % len(post_ids)]],
                confidence="directional",
            )
            for index in range(3)
        ],
        top_topic_format_combinations=["agents + text"],
        hook_analysis=["Specific hooks led the sample."],
        behavioral_audit=["Reply behavior needs a larger sample."],
        recommendations=["Repeat the strongest topic.", "Change one hook variable."],
        controlled_experiment="Hold topic constant and compare two hook types.",
    )


def cricket_result():
    return CricketBuildLogResult(
        week_headline="Week 7 improves ball tracking evidence.",
        technical_to_cricket_translation=["Track release.", "Follow trajectory."],
        metric_changes=[
            MetricChange(
                name="ball detection mAP",
                previous=None,
                current="0.73 mAP",
                interpretation="Baseline established.",
            )
        ],
        progress_narrative="Tracking now covers the delivery sequence.",
        failure_narrative="Motion blur remains unresolved.",
        hook_options=["Hook one", "Hook two", "Hook three"],
        audience_bridge="The metric connects detection quality to usable analysis.",
        visual_recommendation="Show a trajectory overlay.",
    )


class FakeStore:
    def __init__(self):
        self.agent_runs = []
        self.posts = []
        self.analyses = []

    def record_agent_run(self, agent_response, summary):
        self.agent_runs.append((agent_response, summary))

    def save_posts(self, posts):
        self.posts.extend(posts)

    def save_performance_analysis(self, agent_response, dataset):
        self.analyses.append((agent_response, dataset))

    def history(self, limit):
        return [
            AgentHistoryItem(
                run_id="run-1",
                agent="post_architecture",
                created_at=datetime(2026, 6, 12, tzinfo=UTC),
                model_used="fake",
                passed=True,
                warnings=0,
                summary="Stored result",
            )
        ][:limit]


def services(store=None):
    def performance_generate(request):
        dataset = compute_analytics(request.posts)
        return response(
            "performance",
            performance_result([post.post_id for post in request.posts]),
        ), dataset

    return SimpleNamespace(
        store=store,
        post_architecture=SimpleNamespace(
            generate=lambda request: response("post_architecture", post_result())
        ),
        paper=SimpleNamespace(
            generate=lambda document: response("paper", paper_result())
        ),
        paper_extractor=SimpleNamespace(
            from_bytes=lambda content, filename: PaperDocument(
                title=filename,
                source="upload",
                pages=[
                    PaperPage(
                        number=1,
                        text="We introduce a method. The model is evaluated.",
                    )
                ],
            ),
            from_arxiv=lambda url: PaperDocument(
                title="arXiv paper",
                source=url,
                pages=[
                    PaperPage(
                        number=1,
                        text="We introduce a method. The model is evaluated.",
                    )
                ],
            ),
        ),
        carousel=SimpleNamespace(
            generate=lambda request: response("carousel", carousel_result())
        ),
        performance=SimpleNamespace(generate=performance_generate),
        cricket=SimpleNamespace(
            generate=lambda request: response("cricket_build_log", cricket_result())
        ),
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


def post_payload(post_id):
    return {
        "post_id": post_id,
        "posted_date": "2026-06-01",
        "format": "text",
        "topic": "agents",
        "pillar": "technical",
        "hook_type": "failure",
        "first_line": "Retries need explicit limits.",
        "impressions": 1000,
        "reactions": 50,
        "comments": 10,
        "saves": 20,
        "shares": 5,
        "profile_clicks": 3,
    }


def test_all_agent_endpoints_return_structured_results():
    store = FakeStore()
    client = TestClient(create_app(services(store)))

    post = client.post(
        "/agents/post-architecture",
        json={
            "topic": "Agent reliability",
            "key_insight": "Retries need explicit failure classes and limits.",
        },
    )
    assert post.status_code == 200
    assert len(post.json()["result"]["hooks"]) == 7

    paper = client.post(
        "/agents/paper",
        files={"file": ("paper.pdf", b"%PDF-test", "application/pdf")},
    )
    assert paper.status_code == 200
    assert paper.json()["result"]["metadata"]["title"] == "Paper"

    carousel = client.post(
        "/agents/carousel",
        json={
            "topic": "Agent reliability",
            "key_points": ["Tools fail.", "Retries need limits."],
            "slide_count": 8,
        },
    )
    assert carousel.status_code == 200
    assert carousel.json()["marp_markdown"].count("\n---\n") == 8

    performance = client.post(
        "/agents/performance",
        json={"posts": [post_payload("p1"), post_payload("p2")]},
    )
    assert performance.status_code == 200
    assert len(performance.json()["computed_analytics"]["posts"]) == 2

    cricket = client.post(
        "/agents/cricket-build-log",
        json={
            "week_number": 7,
            "work_completed": "Tracked the ball through the delivery sequence.",
            "failures": "Motion blur still causes missed detections.",
            "current_metrics": [
                {
                    "name": "ball detection mAP",
                    "value": 0.73,
                    "unit": "mAP",
                    "better_when": "higher",
                }
            ],
        },
    )
    assert cricket.status_code == 200
    assert len(cricket.json()["result"]["hook_options"]) == 3
    assert len(store.agent_runs) == 5
    assert len(store.analyses) == 1


def test_analytics_json_csv_and_history_routes():
    store = FakeStore()
    client = TestClient(create_app(services(store)))

    saved = client.post("/analytics/posts", json=[post_payload("json-post")])
    assert saved.status_code == 200
    assert saved.json() == {"saved": 1}

    headers = ",".join(post_payload("csv-post"))
    values = ",".join(str(value) for value in post_payload("csv-post").values())
    imported = client.post(
        "/analytics/import",
        files={"file": ("posts.csv", f"{headers}\n{values}\n", "text/csv")},
    )
    assert imported.status_code == 200
    assert imported.json() == {"saved": 1}

    history = client.get("/history?limit=1")
    assert history.status_code == 200
    assert history.json()[0]["run_id"] == "run-1"
    assert [post.post_id for post in store.posts] == ["json-post", "csv-post"]


def test_strict_request_and_query_validation():
    client = TestClient(create_app(services()))

    invalid_request = client.post(
        "/agents/post-architecture",
        json={"topic": "x", "key_insight": "short", "unexpected": True},
    )
    assert invalid_request.status_code == 422
    assert client.get("/history?limit=0").status_code == 422
