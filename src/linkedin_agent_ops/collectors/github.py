from __future__ import annotations

from datetime import timedelta

import httpx

from linkedin_agent_ops.models import SourceItem, SourceKind
from linkedin_agent_ops.utils import canonicalize_url, clean_text, parse_datetime


class GitHubCollector:
    name = "github"
    endpoint = "https://api.github.com/search/repositories"

    def __init__(
        self,
        client: httpx.Client,
        *,
        token: str = "",
        queries: list[str] | None = None,
        lookback_days: int = 7,
        minimum_stars: int = 3,
    ) -> None:
        self.client = client
        self.token = token
        self.queries = queries or ["computer vision", "ai agents", "mlops"]
        self.lookback_days = lookback_days
        self.minimum_stars = minimum_stars

    def collect(self, as_of):
        created_after = (as_of - timedelta(days=self.lookback_days)).date().isoformat()
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        collected: dict[str, SourceItem] = {}
        for query in self.queries:
            response = self.client.get(
                self.endpoint,
                params={
                    "q": (
                        f"{query} created:>={created_after} "
                        f"stars:>={self.minimum_stars}"
                    ),
                    "sort": "stars",
                    "order": "desc",
                    "per_page": 20,
                },
                headers=headers,
            )
            response.raise_for_status()
            for repo in response.json().get("items", []):
                url = canonicalize_url(repo["html_url"])
                collected[url] = SourceItem(
                    source_id=str(repo["id"]),
                    source=SourceKind.GITHUB,
                    source_name="GitHub",
                    title=repo["full_name"],
                    url=url,
                    published_at=parse_datetime(repo["created_at"]),
                    excerpt=clean_text(repo.get("description") or "", limit=800),
                    category=(repo.get("language") or "repository"),
                    authors=[repo["owner"]["login"]],
                    metrics={
                        "stars": float(repo.get("stargazers_count") or 0),
                        "forks": float(repo.get("forks_count") or 0),
                    },
                )
        return list(collected.values())

