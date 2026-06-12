from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import httpx

from linkedin_agent_ops.agent_runner import StructuredAgentRunner
from linkedin_agent_ops.agents import (
    CarouselAgent,
    CricketBuildLogAgent,
    PaperAgent,
    PerformanceAgent,
    PostArchitectureAgent,
)
from linkedin_agent_ops.agents.paper import PaperExtractor
from linkedin_agent_ops.config import AppSettings
from linkedin_agent_ops.context import CreatorProfile
from linkedin_agent_ops.llm import GeminiProvider, GroqProvider
from linkedin_agent_ops.sheets import GoogleSheetsStore


@dataclass
class AgentServices:
    settings: AppSettings
    client: httpx.Client
    post_architecture: PostArchitectureAgent
    paper: PaperAgent
    paper_extractor: PaperExtractor
    carousel: CarouselAgent
    performance: PerformanceAgent
    cricket: CricketBuildLogAgent
    store: GoogleSheetsStore | None = None

    def close(self) -> None:
        self.client.close()


@lru_cache(maxsize=1)
def build_services() -> AgentServices:
    settings = AppSettings.from_env()
    settings.validate_agents()
    client = httpx.Client(
        timeout=httpx.Timeout(60.0),
        follow_redirects=True,
        headers={"User-Agent": "linkedin-agent-ops/0.2"},
    )
    providers = []
    if settings.gemini_api_key:
        providers.append(
            GeminiProvider(
                client,
                settings.gemini_api_key,
                settings.config["models"]["gemini"],
            )
        )
    if settings.groq_api_key:
        providers.append(
            GroqProvider(
                client,
                settings.groq_api_key,
                settings.config["models"]["groq"],
            )
        )
    runner = StructuredAgentRunner(providers)
    agent_config = settings.config["agents"]
    common = {
        "runner": runner,
        "profile": CreatorProfile.load(agent_config["profile_path"]),
        "examples_path": agent_config["examples_path"],
    }
    store = None
    if settings.sheets_configured() and agent_config.get("history_enabled", True):
        store = GoogleSheetsStore(
            spreadsheet_id=settings.google_sheet_id,
            service_account_info=settings.service_account_info(),
        )
    return AgentServices(
        settings=settings,
        client=client,
        post_architecture=PostArchitectureAgent(**common),
        paper=PaperAgent(
            **common,
            direct_context_chars=agent_config["paper_direct_context_chars"],
            chunk_chars=agent_config["paper_chunk_chars"],
        ),
        paper_extractor=PaperExtractor(
            client,
            max_bytes=agent_config["paper_max_bytes"],
            max_pages=agent_config["paper_max_pages"],
        ),
        carousel=CarouselAgent(**common),
        performance=PerformanceAgent(**common),
        cricket=CricketBuildLogAgent(**common),
        store=store,
    )

