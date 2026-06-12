from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CreatorProfile:
    raw: dict

    @classmethod
    def load(cls, path: str | Path) -> CreatorProfile:
        with Path(path).open("rb") as profile_file:
            return cls(tomllib.load(profile_file))

    def for_agent(self, agent: str) -> str:
        fields = [
            "positioning",
            "audience",
            "content_pillars",
            "technical_expertise",
            "tone",
            "banned_language",
            "non_goals",
        ]
        if agent == "cricket_build_log":
            fields.append("cricket_context")
        lines = [f"profile_version: {self.raw.get('version', 'unknown')}"]
        for field in fields:
            value = self.raw.get(field)
            if isinstance(value, list):
                lines.append(f"{field}:\n" + "\n".join(f"- {item}" for item in value))
            elif value:
                lines.append(f"{field}: {value}")
        return "\n\n".join(lines)

    @property
    def banned_language(self) -> list[str]:
        return [str(value).lower() for value in self.raw.get("banned_language", [])]


def select_examples(
    examples_path: str | Path,
    *,
    topic: str,
    limit: int = 2,
) -> list[str]:
    path = Path(examples_path)
    if not path.exists():
        return []
    terms = set(re.findall(r"[a-z0-9]+", topic.lower()))
    scored: list[tuple[int, str]] = []
    for example_path in path.glob("*.md"):
        text = example_path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        overlap = len(terms & set(re.findall(r"[a-z0-9]+", text.lower())))
        scored.append((overlap, text[:4000]))
    return [text for _, text in sorted(scored, reverse=True)[:limit]]

