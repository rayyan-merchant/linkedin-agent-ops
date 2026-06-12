from __future__ import annotations

from linkedin_agent_ops.agent_runner import StructuredAgentRunner
from linkedin_agent_ops.context import CreatorProfile, select_examples


class BaseAgent:
    name = "base"

    def __init__(
        self,
        *,
        runner: StructuredAgentRunner,
        profile: CreatorProfile,
        examples_path: str,
    ) -> None:
        self.runner = runner
        self.profile = profile
        self.examples_path = examples_path

    def context(self) -> str:
        return self.profile.for_agent(self.name)

    def examples(self, topic: str) -> list[str]:
        return select_examples(self.examples_path, topic=topic)

