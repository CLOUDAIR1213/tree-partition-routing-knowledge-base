import json

from app.services.web_search import WebSearchResult


class FakeLLMProvider:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = [json.dumps(item, ensure_ascii=False) for item in responses]
        self.calls: list[str] = []

    async def complete(self, *, model, system_prompt, user_prompt) -> str:
        self.calls.append(model)
        return self.responses.pop(0)


class FakeWebSearchProvider:
    def __init__(self, results: list[WebSearchResult]) -> None:
        self.results = results
        self.calls: list[tuple[str, int]] = []

    async def search(self, query: str, max_results: int) -> list[WebSearchResult]:
        self.calls.append((query, max_results))
        return self.results[:max_results]


def configure_fake_llm(client, provider: FakeLLMProvider) -> None:
    settings = client.app.state.settings
    settings.llm_base_url = "https://llm.invalid/v1"
    settings.llm_api_key = "test-key-not-sent"
    settings.router_llm_model = "router-test"
    settings.answer_llm_model = "answer-test"
    client.app.state.llm_provider = provider


def upload_ready_document(client, fake_registry, partition: str, filename: str) -> str:
    upload = client.post(
        "/api/v1/documents",
        files={
            "file": (
                filename,
                f"# {partition}\n\n{partition} test-only evidence.".encode(),
                "text/markdown",
            )
        },
        data={"partition": partition, "title": f"{partition} policy"},
    )
    document_id = upload.json()["document_id"]
    review = client.post(
        f"/api/v1/documents/{document_id}/review",
        json={
            "action": "approve",
            "confirmed_partition": partition,
            "reviewer_name": None,
            "note": None,
        },
    )
    assert review.status_code == 200
    return next(iter(fake_registry.rows[partition]))


def test_auto_mode_returns_clarification_without_search(client, fake_registry):
    response = client.post(
        "/api/v1/chat",
        json={"question": "这个制度怎么处理？", "partition_hint": None},
    )

    assert response.status_code == 200
    assert response.json()["code"] == "ROUTE_CLARIFICATION_REQUIRED"
    assert response.json()["route"] == "clarify"
    assert response.json()["searched_partitions"] == []
    assert response.json()["suggested_partitions"] == ["finance", "hr", "tech"]
    assert fake_registry.search_calls == []


def test_partition_hint_searches_only_selected_index(client, fake_registry):
    response = client.post(
        "/api/v1/chat",
        json={"question": "如何排查 502？", "partition_hint": "tech"},
    )

    assert response.status_code == 200
    assert response.json()["code"] == "NO_INTERNAL_EVIDENCE"
    assert response.json()["route"] == "tech"
    assert response.json()["decision_source"] == "user_hint"
    assert response.json()["searched_partitions"] == ["tech"]
    assert fake_registry.search_calls == ["tech"]
    assert response.json()["answer_source"] == "none"
    assert response.json()["web_citations"] == []


def test_zero_internal_evidence_uses_opted_in_web_fallback(client, fake_registry):
    source = WebSearchResult(
        title="Python decorators",
        url="https://docs.python.org/3/glossary.html#term-decorator",
        domain="docs.python.org",
        snippet="A decorator is a function returning another function.",
    )
    search_provider = FakeWebSearchProvider([source])
    client.app.state.web_search_provider = search_provider
    provider = FakeLLMProvider(
        [
            {
                "answer": "装饰器用于包装函数或类并扩展其行为。",
                "citation_urls": [source.url],
            }
        ]
    )
    configure_fake_llm(client, provider)

    response = client.post(
        "/api/v1/chat",
        json={
            "question": "Python 装饰器是什么？",
            "partition_hint": "tech",
            "allow_web_fallback": True,
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["code"] == "OK"
    assert payload["answer_source"] == "web"
    assert payload["searched_partitions"] == ["tech"]
    assert payload["citations"] == []
    assert payload["web_citations"] == [
        {
            "title": source.title,
            "url": source.url,
            "domain": source.domain,
        }
    ]
    assert search_provider.calls == [("Python 装饰器是什么？", 5)]
    assert provider.calls == ["answer-test"]


def test_low_score_internal_hits_do_not_block_opted_in_web_fallback(
    client, fake_registry
):
    tech_chunk = upload_ready_document(client, fake_registry, "tech", "unrelated.md")
    fake_registry.search_results["tech"] = [{"id": tech_chunk, "score": 0.41}]
    source = WebSearchResult(
        title="Python decorators",
        url="https://docs.python.org/3/glossary.html#term-decorator",
        domain="docs.python.org",
        snippet="A decorator is a function returning another function.",
    )
    search_provider = FakeWebSearchProvider([source])
    client.app.state.web_search_provider = search_provider
    provider = FakeLLMProvider(
        [
            {
                "answer": "装饰器用于包装函数或类并扩展其行为。",
                "citation_urls": [source.url],
            }
        ]
    )
    configure_fake_llm(client, provider)

    response = client.post(
        "/api/v1/chat",
        json={
            "question": "Python 装饰器是什么？",
            "partition_hint": "tech",
            "allow_web_fallback": True,
        },
    )

    payload = response.json()
    assert payload["code"] == "OK"
    assert payload["answer_source"] == "web"
    assert payload["citations"] == []
    assert [item["url"] for item in payload["web_citations"]] == [source.url]
    assert search_provider.calls == [("Python 装饰器是什么？", 5)]


def test_web_fallback_requires_explicit_request_opt_in(client, fake_registry):
    search_provider = FakeWebSearchProvider([])
    client.app.state.web_search_provider = search_provider

    response = client.post(
        "/api/v1/chat",
        json={"question": "Python 装饰器是什么？", "partition_hint": "tech"},
    )

    assert response.json()["code"] == "NO_INTERNAL_EVIDENCE"
    assert search_provider.calls == []


def test_internal_evidence_prevents_web_fallback(client, fake_registry):
    tech_chunk = upload_ready_document(client, fake_registry, "tech", "internal.md")
    fake_registry.search_results["tech"] = [{"id": tech_chunk, "score": 0.9}]
    search_provider = FakeWebSearchProvider([])
    client.app.state.web_search_provider = search_provider

    response = client.post(
        "/api/v1/chat",
        json={
            "question": "如何排查 502？",
            "partition_hint": "tech",
            "allow_web_fallback": True,
        },
    )

    assert response.json()["answer_source"] == "internal"
    assert response.json()["web_citations"] == []
    assert search_provider.calls == []


def test_internal_policy_question_is_not_sent_to_web(client, fake_registry):
    search_provider = FakeWebSearchProvider([])
    client.app.state.web_search_provider = search_provider

    response = client.post(
        "/api/v1/chat",
        json={
            "question": "本公司差旅制度是什么？",
            "partition_hint": "finance",
            "allow_web_fallback": True,
        },
    )

    payload = response.json()
    assert payload["code"] == "NO_INTERNAL_EVIDENCE"
    assert payload["answer_source"] == "none"
    assert "不符合公开、低风险" in payload["warning"]
    assert search_provider.calls == []


def test_secret_input_is_blocked_before_search(client, fake_registry):
    response = client.post(
        "/api/v1/chat",
        json={
            "question": "Bearer abcdefghijklmnopqrstuvwxyz123456",
            "partition_hint": "finance",
        },
    )

    assert response.status_code == 200
    assert response.json()["code"] == "SENSITIVE_INPUT_BLOCKED"
    assert response.json()["answerable"] is False
    assert response.json()["searched_partitions"] == []
    assert fake_registry.search_calls == []


def test_invalid_chat_partition_uses_error_contract(client):
    response = client.post(
        "/api/v1/chat",
        json={"question": "问题", "partition_hint": "Finance"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_PARTITION"
    assert response.headers["X-Request-ID"] == response.json()["request_id"]


def test_partition_hint_bypasses_configured_router(client, fake_registry):
    provider = FakeLLMProvider([])
    configure_fake_llm(client, provider)

    response = client.post(
        "/api/v1/chat",
        json={"question": "如何排查 502？", "partition_hint": "tech"},
    )

    assert response.status_code == 200
    assert response.json()["route"] == "tech"
    assert fake_registry.search_calls == ["tech"]
    assert provider.calls == []


def test_composite_route_searches_two_partitions_and_groups_citations(
    client, fake_registry
):
    tech_chunk = upload_ready_document(client, fake_registry, "tech", "tech.md")
    finance_chunk = upload_ready_document(
        client, fake_registry, "finance", "finance.md"
    )
    fake_registry.search_results["tech"] = [{"id": tech_chunk, "score": 0.91}]
    fake_registry.search_results["finance"] = [
        {"id": finance_chunk, "score": 0.87}
    ]
    provider = FakeLLMProvider(
        [
            {
                "route_kind": "composite",
                "subqueries": [
                    {"partition": "tech", "query": "GitLab 权限申请"},
                    {"partition": "finance", "query": "认证考试费用报销"},
                ],
                "needs_clarification": False,
                "reason_code": "multi_intent",
            },
            {
                "answer": "先申请 GitLab 权限，再按制度报销认证考试费用。",
                "citation_chunk_ids": [tech_chunk, finance_chunk],
            },
        ]
    )
    configure_fake_llm(client, provider)

    response = client.post(
        "/api/v1/chat",
        json={
            "question": "新员工如何申请 GitLab 权限并报销认证考试费用？",
            "partition_hint": None,
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["route"] == "composite"
    assert payload["searched_partitions"] == ["tech", "finance"]
    assert [item["partition"] for item in payload["citations"]] == [
        "tech",
        "finance",
    ]
    assert fake_registry.search_calls == ["tech", "finance"]
    assert provider.calls == ["router-test", "answer-test"]


def test_router_clarify_does_not_search_any_partition(client, fake_registry):
    provider = FakeLLMProvider(
        [
            {
                "route_kind": "clarify",
                "subqueries": [],
                "needs_clarification": True,
                "reason_code": "ambiguous_domain",
            }
        ]
    )
    configure_fake_llm(client, provider)

    response = client.post(
        "/api/v1/chat",
        json={"question": "这个制度怎么办？", "partition_hint": None},
    )

    assert response.status_code == 200
    assert response.json()["route"] == "clarify"
    assert response.json()["decision_source"] == "llm"
    assert response.json()["searched_partitions"] == []
    assert fake_registry.search_calls == []
    assert provider.calls == ["router-test"]


def test_unknown_answer_citation_is_rejected(client, fake_registry):
    tech_chunk = upload_ready_document(client, fake_registry, "tech", "single.md")
    fake_registry.search_results["tech"] = [{"id": tech_chunk, "score": 0.9}]
    provider = FakeLLMProvider(
        [
            {
                "route_kind": "single",
                "subqueries": [{"partition": "tech", "query": "502 排查"}],
                "needs_clarification": False,
                "reason_code": "technical_operation",
            },
            {
                "answer": "引用了未召回的内容。",
                "citation_chunk_ids": ["unknown-chunk"],
            },
        ]
    )
    configure_fake_llm(client, provider)

    response = client.post(
        "/api/v1/chat",
        json={"question": "如何排查 502？", "partition_hint": None},
    )

    assert response.status_code == 200
    assert response.json()["code"] == "NO_INTERNAL_EVIDENCE"
    assert response.json()["answerable"] is False
    assert response.json()["citations"] == []
