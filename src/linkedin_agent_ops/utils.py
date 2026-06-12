from __future__ import annotations

import re
from datetime import UTC, datetime
from html import unescape
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_datetime(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower() or "https"
    hostname = (parts.hostname or "").lower()
    port = parts.port
    netloc = hostname
    if port and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        netloc = f"{hostname}:{port}"

    path = re.sub(r"/+", "/", parts.path).rstrip("/") or "/"
    if hostname in {"arxiv.org", "www.arxiv.org"}:
        netloc = "arxiv.org"
        path = re.sub(r"^/pdf/", "/abs/", path)
        path = re.sub(r"\.pdf$", "", path)

    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in TRACKING_PARAMETERS
    ]
    return urlunsplit((scheme, netloc, path, urlencode(sorted(query)), ""))


def clean_text(value: str, limit: int | None = None) -> str:
    text = unescape(re.sub(r"<[^>]+>", " ", value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        return f"{text[: limit - 3].rstrip()}..."
    return text
