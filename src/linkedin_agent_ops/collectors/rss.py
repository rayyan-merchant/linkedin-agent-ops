from __future__ import annotations

import calendar
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

import feedparser
import httpx

from linkedin_agent_ops.models import SourceItem, SourceKind
from linkedin_agent_ops.utils import canonicalize_url, clean_text, parse_datetime


class RssCollector:
    name = "rss"

    def __init__(
        self,
        client: httpx.Client,
        *,
        feeds: list[dict[str, str]],
        lookback_hours: int = 48,
    ) -> None:
        self.client = client
        self.feeds = feeds
        self.lookback_hours = lookback_hours

    def collect(self, as_of):
        cutoff = as_of - timedelta(hours=self.lookback_hours)
        items: list[SourceItem] = []
        errors: list[str] = []

        for feed in self.feeds:
            try:
                response = self.client.get(feed["url"])
                response.raise_for_status()
                parsed = feedparser.parse(response.content)
                for entry in parsed.entries:
                    published = self._entry_datetime(entry)
                    if published is None or published < cutoff:
                        continue
                    link = entry.get("link", "")
                    title = clean_text(entry.get("title", ""))
                    if not link or not title:
                        continue
                    url = canonicalize_url(link)
                    items.append(
                        SourceItem(
                            source_id=str(entry.get("id") or url),
                            source=SourceKind.RSS,
                            source_name=feed["name"],
                            title=title,
                            url=url,
                            published_at=published,
                            excerpt=clean_text(
                                entry.get("summary")
                                or entry.get("description")
                                or "",
                                limit=1000,
                            ),
                            category="official update",
                            authors=[
                                clean_text(entry.get("author", ""))
                            ]
                            if entry.get("author")
                            else [],
                        )
                    )
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                errors.append(f"{feed['name']}: {exc}")

        if not items and errors:
            raise RuntimeError("; ".join(errors))
        return items

    @staticmethod
    def _entry_datetime(entry) -> datetime | None:
        for key in ("published_parsed", "updated_parsed"):
            parsed = entry.get(key)
            if parsed:
                return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)
        for key in ("published", "updated"):
            raw = entry.get(key)
            if not raw:
                continue
            try:
                parsed = parsedate_to_datetime(raw)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
                return parsed.astimezone(UTC)
            except (TypeError, ValueError):
                try:
                    return parse_datetime(raw)
                except ValueError:
                    continue
        return None

