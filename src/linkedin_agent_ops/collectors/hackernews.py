from __future__ import annotations

from datetime import timedelta

import httpx

from linkedin_agent_ops.models import SourceItem, SourceKind
from linkedin_agent_ops.utils import canonicalize_url, clean_text, parse_datetime


class HackerNewsCollector:
    name = "hacker_news"
    endpoint = "https://hn.algolia.com/api/v1/search_by_date"

    def __init__(
        self,
        client: httpx.Client,
        *,
        lookback_hours: int = 36,
        queries: tuple[str, ...] = ("AI", "machine learning", "LLM"),
    ) -> None:
        self.client = client
        self.lookback_hours = lookback_hours
        self.queries = queries

    def collect(self, as_of):
        cutoff = as_of - timedelta(hours=self.lookback_hours)
        collected: dict[str, SourceItem] = {}
        for query in self.queries:
            response = self.client.get(
                self.endpoint,
                params={
                    "query": query,
                    "tags": "story",
                    "numericFilters": f"created_at_i>{int(cutoff.timestamp())}",
                    "hitsPerPage": 40,
                },
            )
            response.raise_for_status()
            for hit in response.json().get("hits", []):
                title = clean_text(hit.get("title") or "")
                object_id = str(hit.get("objectID") or "")
                if not title or not object_id:
                    continue
                url = hit.get("url") or f"https://news.ycombinator.com/item?id={object_id}"
                url = canonicalize_url(url)
                item = SourceItem(
                    source_id=object_id,
                    source=SourceKind.HACKER_NEWS,
                    source_name="Hacker News",
                    title=title,
                    url=url,
                    published_at=parse_datetime(hit["created_at"]),
                    excerpt=clean_text(hit.get("story_text") or "", limit=800),
                    category="builder trend",
                    metrics={
                        "points": float(hit.get("points") or 0),
                        "comments": float(hit.get("num_comments") or 0),
                    },
                )
                previous = collected.get(url)
                if previous is None or item.metrics["points"] > previous.metrics["points"]:
                    collected[url] = item
        return list(collected.values())

