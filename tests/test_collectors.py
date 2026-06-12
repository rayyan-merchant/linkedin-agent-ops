from datetime import UTC, datetime

import httpx

from linkedin_agent_ops.collectors.arxiv import ArxivCollector
from linkedin_agent_ops.collectors.github import GitHubCollector
from linkedin_agent_ops.collectors.hackernews import HackerNewsCollector
from linkedin_agent_ops.collectors.rss import RssCollector

AS_OF = datetime(2026, 6, 12, 2, 30, tzinfo=UTC)


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_arxiv_parsing():
    body = b"""<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>https://arxiv.org/abs/2606.00001</id>
        <updated>2026-06-11T00:00:00Z</updated>
        <published>2026-06-11T00:00:00Z</published>
        <title> Vision Paper </title>
        <summary>Useful result.</summary>
        <author><name>A. Author</name></author>
        <category term="cs.CV"/>
      </entry>
    </feed>"""
    client = client_for(lambda request: httpx.Response(200, content=body))
    items = ArxivCollector(client).collect(AS_OF)
    assert items[0].category == "cs.CV"
    assert items[0].authors == ["A. Author"]


def test_hacker_news_parsing_and_deduplication():
    payload = {
        "hits": [
            {
                "objectID": "1",
                "title": "AI deployment",
                "url": "https://example.com/story?utm_source=hn",
                "created_at": "2026-06-11T10:00:00Z",
                "points": 20,
                "num_comments": 4,
            }
        ]
    }
    client = client_for(lambda request: httpx.Response(200, json=payload))
    items = HackerNewsCollector(client).collect(AS_OF)
    assert len(items) == 1
    assert items[0].url == "https://example.com/story"
    assert items[0].metrics["points"] == 20


def test_github_parsing():
    payload = {
        "items": [
            {
                "id": 1,
                "full_name": "example/agent",
                "html_url": "https://github.com/example/agent",
                "created_at": "2026-06-10T00:00:00Z",
                "description": "An agent evaluation tool",
                "language": "Python",
                "owner": {"login": "example"},
                "stargazers_count": 12,
                "forks_count": 2,
            }
        ]
    }
    client = client_for(lambda request: httpx.Response(200, json=payload))
    items = GitHubCollector(client, queries=["agent"]).collect(AS_OF)
    assert items[0].title == "example/agent"
    assert items[0].metrics["forks"] == 2


def test_rss_parsing():
    body = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>Feed</title><item>
      <title>Vision deployment guide</title>
      <link>https://example.com/guide</link>
      <pubDate>Thu, 11 Jun 2026 10:00:00 GMT</pubDate>
      <description>Practical deployment advice.</description>
    </item></channel></rss>"""
    client = client_for(lambda request: httpx.Response(200, content=body))
    items = RssCollector(
        client, feeds=[{"name": "Example", "url": "https://example.com/feed"}]
    ).collect(AS_OF)
    assert items[0].source_name == "Example"
    assert items[0].title == "Vision deployment guide"

