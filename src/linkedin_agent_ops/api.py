from typing import Annotated

import uvicorn
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)

from linkedin_agent_ops.agent_models import AgentHistoryItem
from linkedin_agent_ops.agent_runner import AgentGenerationError
from linkedin_agent_ops.agents.carousel import CarouselRequest, render_marp
from linkedin_agent_ops.agents.cricket import CricketBuildLogRequest
from linkedin_agent_ops.agents.paper import PaperInputError
from linkedin_agent_ops.agents.performance import (
    PerformanceRequest,
    PostMetric,
    parse_posts_csv,
)
from linkedin_agent_ops.agents.post_architecture import PostArchitectureRequest
from linkedin_agent_ops.services import AgentServices, build_services


def create_app(services: AgentServices | None = None) -> FastAPI:
    app = FastAPI(
        title="LinkedIn Agent Ops",
        version="0.2.0",
        description="Private research and content-planning agents for an AI engineer.",
    )

    def get_services() -> AgentServices:
        try:
            return services or build_services()
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    Services = Annotated[AgentServices, Depends(get_services)]

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/agents/post-architecture")
    def post_architecture(
        request: PostArchitectureRequest,
        service: Services,
    ):
        return _run_and_store(
            service,
            lambda: service.post_architecture.generate(request),
            request.topic,
        )

    @app.post("/agents/paper")
    async def paper(
        service: Services,
        arxiv_url: Annotated[str | None, Form()] = None,
        file: Annotated[UploadFile | None, File()] = None,
    ):
        if bool(arxiv_url) == bool(file):
            raise HTTPException(
                status_code=422,
                detail="Provide exactly one arXiv URL or PDF upload.",
            )
        try:
            if arxiv_url:
                document = service.paper_extractor.from_arxiv(arxiv_url)
            else:
                assert file is not None
                document = service.paper_extractor.from_bytes(
                    await file.read(),
                    filename=file.filename or "paper.pdf",
                )
            return _run_and_store(
                service,
                lambda: service.paper.generate(document),
                document.title,
            )
        except PaperInputError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/agents/carousel")
    def carousel(
        request: CarouselRequest,
        service: Services,
    ):
        response = _run_and_store(
            service,
            lambda: service.carousel.generate(request),
            request.topic,
        )
        return {
            **response.model_dump(mode="json"),
            "marp_markdown": render_marp(response.result),
        }

    @app.post("/agents/performance")
    def performance(
        request: PerformanceRequest,
        service: Services,
    ):
        try:
            response, dataset = service.performance.generate(request)
        except AgentGenerationError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if service.store:
            service.store.record_agent_run(response, "Performance analysis")
            service.store.save_performance_analysis(response, dataset)
        return {
            **response.model_dump(mode="json"),
            "computed_analytics": dataset.model_dump(mode="json"),
        }

    @app.post("/agents/cricket-build-log")
    def cricket(
        request: CricketBuildLogRequest,
        service: Services,
    ):
        return _run_and_store(
            service,
            lambda: service.cricket.generate(request),
            f"Cricket CV week {request.week_number}",
        )

    @app.post("/analytics/posts")
    def save_posts(
        posts: list[PostMetric],
        service: Services,
    ):
        if service.store is None:
            raise HTTPException(status_code=503, detail="Google Sheets is not configured")
        service.store.save_posts(posts)
        return {"saved": len(posts)}

    @app.post("/analytics/import")
    async def import_posts(
        file: Annotated[UploadFile, File()],
        service: Services,
    ):
        if service.store is None:
            raise HTTPException(status_code=503, detail="Google Sheets is not configured")
        try:
            posts = parse_posts_csv(await file.read())
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        service.store.save_posts(posts)
        return {"saved": len(posts)}

    @app.get("/history", response_model=list[AgentHistoryItem])
    def history(
        service: Services,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ):
        return service.store.history(limit) if service.store else []

    return app


def _run_and_store(service: AgentServices, generate, summary: str):
    try:
        response = generate()
    except AgentGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if service.store:
        service.store.record_agent_run(response, summary)
    return response


app = create_app()


def run() -> None:
    uvicorn.run(
        "linkedin_agent_ops.api:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
