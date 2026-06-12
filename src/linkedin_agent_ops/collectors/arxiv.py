from __future__ import annotations

from datetime import timedelta
from xml.etree import ElementTree

import httpx

from linkedin_agent_ops.models import SourceItem, SourceKind
from linkedin_agent_ops.utils import canonicalize_url, clean_text, parse_datetime

ATOM = {"atom": "http://www.w3.org/2005/Atom"}


class ArxivCollector:
    name = "arxiv"
    endpoint = "https://export.arxiv.org/api/query"

    def __init__(
        self,
        client: httpx.Client,
        *,
        lookback_hours: int = 48,
        max_results: int = 50,
    ) -> None:
        self.client = client
        self.lookback_hours = lookback_hours
        self.max_results = max_results

    def collect(self, as_of):
        response = self.client.get(
            self.endpoint,
            params={
                "search_query": "cat:cs.CV OR cat:cs.LG OR cat:cs.AI",
                "start": 0,
                "max_results": self.max_results,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            },
        )
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)
        cutoff = as_of - timedelta(hours=self.lookback_hours)
        items: list[SourceItem] = []

        for entry in root.findall("atom:entry", ATOM):
            published = parse_datetime(entry.findtext("atom:published", "", ATOM))
            if published < cutoff:
                continue
            raw_id = entry.findtext("atom:id", "", ATOM)
            url = canonicalize_url(raw_id)
            categories = [
                node.attrib.get("term", "")
                for node in entry.findall("atom:category", ATOM)
            ]
            relevant_category = next(
                (
                    category
                    for category in categories
                    if category in {"cs.CV", "cs.LG", "cs.AI"}
                ),
                categories[0] if categories else "",
            )
            items.append(
                SourceItem(
                    source_id=url.rsplit("/", 1)[-1],
                    source=SourceKind.ARXIV,
                    source_name="arXiv",
                    title=clean_text(entry.findtext("atom:title", "", ATOM)),
                    url=url,
                    published_at=published,
                    excerpt=clean_text(
                        entry.findtext("atom:summary", "", ATOM), limit=1200
                    ),
                    category=relevant_category,
                    authors=[
                        clean_text(author.findtext("atom:name", "", ATOM))
                        for author in entry.findall("atom:author", ATOM)
                    ],
                )
            )
        return items

