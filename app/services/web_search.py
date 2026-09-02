import logging
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


class WebSearchProviderError(Exception):
    """Raised when a search provider cannot return usable structured results."""

    def __init__(self, kind: str, status_code: int | None = None) -> None:
        self.kind = kind
        self.status_code = status_code
        super().__init__(kind)

    @property
    def safe_message(self) -> str:
        if self.status_code in (401, 403):
            return "联网搜索认证失败，请检查本地 Tavily Key。"
        if self.status_code == 429:
            return "联网搜索额度或速率受限，请稍后再试。"
        if self.status_code is not None:
            return f"联网搜索服务返回 HTTP {self.status_code}，本次未生成网络答案。"
        if self.kind == "timeout":
            return "联网搜索请求超时，本次未生成网络答案。"
        if self.kind == "network":
            return "联网搜索网络连接失败，本次未生成网络答案。"
        return "联网搜索返回无效响应，本次未生成网络答案。"


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    domain: str
    snippet: str


class WebSearchProvider(Protocol):
    async def search(self, query: str, max_results: int) -> list[WebSearchResult]: ...


_TRACKING_PARAMETERS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
_BLOCKED_QUESTION_MARKERS = (
    "本公司",
    "我司",
    "公司内部",
    "内部制度",
    "员工",
    "报销",
    "薪资",
    "绩效",
    "入职",
    "离职",
    "请假",
    "内部账号",
    "权限申请",
    "私网",
    "内网",
    "密码",
    "密钥",
    "token",
    "诊断",
    "处方",
    "法律意见",
    "诉讼",
    "投资建议",
    "股票推荐",
)


def is_web_fallback_eligible(question: str) -> bool:
    normalized = question.casefold()
    return not any(marker.casefold() in normalized for marker in _BLOCKED_QUESTION_MARKERS)


def normalize_public_https_url(value: str) -> tuple[str, str] | None:
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return None
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None

    hostname = parsed.hostname.rstrip(".").casefold()
    if hostname == "localhost" or hostname.endswith((".localhost", ".local")):
        return None
    try:
        address = ip_address(hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            return None

    filtered_query = urlencode(
        [
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.casefold().startswith("utm_")
            and key.casefold() not in _TRACKING_PARAMETERS
        ],
        doseq=True,
    )
    normalized_url = urlunsplit(
        ("https", parsed.netloc, parsed.path or "/", filtered_query, "")
    )
    return normalized_url, hostname


class TavilySearchProvider:
    def __init__(self, endpoint: str, api_key: str, timeout_seconds: float) -> None:
        normalized = normalize_public_https_url(endpoint)
        if normalized is None:
            raise ValueError("web search endpoint must be a public HTTPS URL")
        self.endpoint = normalized[0]
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def search(self, query: str, max_results: int) -> list[WebSearchResult]:
        body = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self.endpoint, json=body)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            failure = WebSearchProviderError("http_status", exc.response.status_code)
        except httpx.TimeoutException:
            failure = WebSearchProviderError("timeout")
        except httpx.RequestError:
            failure = WebSearchProviderError("network")
        except ValueError:
            failure = WebSearchProviderError("invalid_response")
        else:
            failure = None

        if failure is not None:
            logger.warning(
                "web_search_request_failed kind=%s status_code=%s",
                failure.kind,
                failure.status_code,
            )
            raise failure

        raw_results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(raw_results, list):
            logger.warning("web_search_request_failed kind=invalid_response")
            raise WebSearchProviderError("invalid_response")

        results: list[WebSearchResult] = []
        seen_urls: set[str] = set()
        domain_counts: dict[str, int] = {}
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            title = item.get("title")
            snippet = item.get("content")
            url = item.get("url")
            if not all(isinstance(value, str) and value.strip() for value in (title, snippet, url)):
                continue
            normalized_url = normalize_public_https_url(url)
            if normalized_url is None:
                continue
            safe_url, domain = normalized_url
            if safe_url in seen_urls or domain_counts.get(domain, 0) >= 2:
                continue
            seen_urls.add(safe_url)
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
            results.append(
                WebSearchResult(
                    title=" ".join(title.split())[:300],
                    url=safe_url,
                    domain=domain,
                    snippet=" ".join(snippet.split())[:2000],
                )
            )
            if len(results) >= max_results:
                break
        return results


def build_web_search_provider(settings: Settings) -> WebSearchProvider | None:
    if not settings.web_search_configured:
        return None
    return TavilySearchProvider(
        settings.web_search_base_url,
        settings.web_search_api_key,
        settings.web_search_timeout_seconds,
    )
