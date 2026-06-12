import httpx
import pytest

from linkedin_agent_ops.agents.paper import PaperExtractor, PaperInputError


def extractor():
    return PaperExtractor(httpx.Client(transport=httpx.MockTransport(lambda request: None)))


def test_paper_rejects_non_arxiv_url_before_network():
    with pytest.raises(PaperInputError, match="Only HTTPS arXiv"):
        extractor().from_arxiv("https://example.com/paper.pdf")


def test_paper_rejects_non_pdf_bytes():
    with pytest.raises(PaperInputError, match="not a valid PDF"):
        extractor().from_bytes(b"hello", filename="paper.pdf")

