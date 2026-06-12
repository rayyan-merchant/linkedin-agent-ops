from linkedin_agent_ops.utils import canonicalize_url, clean_text


def test_canonicalize_url_removes_tracking_and_normalizes_arxiv():
    url = "https://www.arxiv.org/pdf/2606.00001.pdf?utm_source=x&b=2&a=1#page=2"
    assert canonicalize_url(url) == "https://arxiv.org/abs/2606.00001?a=1&b=2"


def test_clean_text_removes_markup_and_collapses_whitespace():
    assert clean_text("<p>Hello&nbsp;  world</p>") == "Hello world"

