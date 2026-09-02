import httpx
import pytest

from app.services.web_search import (
    TavilySearchProvider,
    WebSearchProviderError,
    WebSearchResult,
    is_web_fallback_eligible,
    normalize_public_https_url,
)


class FakeAsyncClient:
    def __init__(self, response: httpx.Response, **_kwargs) -> None:
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def post(self, *_args, **_kwargs) -> httpx.Response:
        return self.response


def test_web_fallback_policy_rejects_internal_and_high_risk_questions():
    assert is_web_fallback_eligible("Python 装饰器是什么？") is True
    assert is_web_fallback_eligible("本公司差旅怎么报销？") is False
    assert is_web_fallback_eligible("请给我股票推荐") is False


def test_web_url_normalization_rejects_private_and_non_https_targets():
    assert normalize_public_https_url("http://example.com/article") is None
    assert normalize_public_https_url("https://127.0.0.1/admin") is None
    assert normalize_public_https_url("https://user:pass@example.com/") is None
    assert normalize_public_https_url("https://service.local/docs") is None


def test_web_url_normalization_removes_tracking_and_fragments():
    normalized = normalize_public_https_url(
        "https://Example.com/docs?a=1&utm_source=test#section"
    )

    assert normalized == ("https://Example.com/docs?a=1", "example.com")


async def test_tavily_provider_keeps_only_normalized_public_results(monkeypatch):
    response = httpx.Response(
        200,
        request=httpx.Request("POST", "https://api.tavily.com/search"),
        json={
            "results": [
                {
                    "title": "  Public   documentation ",
                    "url": "https://docs.example.com/page?utm_source=test",
                    "content": "  Supported   public fact. ",
                },
                {
                    "title": "Private target",
                    "url": "https://127.0.0.1/admin",
                    "content": "Must not be exposed.",
                },
            ]
        },
    )
    monkeypatch.setattr(
        "app.services.web_search.httpx.AsyncClient",
        lambda **kwargs: FakeAsyncClient(response, **kwargs),
    )
    provider = TavilySearchProvider(
        "https://api.tavily.com/search",
        "test-key-not-sent",
        8,
    )

    results = await provider.search("public question", 5)

    assert results == [
        WebSearchResult(
            title="Public documentation",
            url="https://docs.example.com/page",
            domain="docs.example.com",
            snippet="Supported public fact.",
        )
    ]


async def test_tavily_provider_classifies_authentication_failures(monkeypatch):
    response = httpx.Response(
        401,
        request=httpx.Request("POST", "https://api.tavily.com/search"),
    )
    monkeypatch.setattr(
        "app.services.web_search.httpx.AsyncClient",
        lambda **kwargs: FakeAsyncClient(response, **kwargs),
    )
    provider = TavilySearchProvider(
        "https://api.tavily.com/search",
        "test-key-not-sent",
        60,
    )

    with pytest.raises(WebSearchProviderError) as exc_info:
        await provider.search("public question", 5)

    assert exc_info.value.kind == "http_status"
    assert exc_info.value.status_code == 401
    assert "认证失败" in exc_info.value.safe_message
