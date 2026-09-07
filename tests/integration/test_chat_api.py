import json
import logging

from app.models.enums import Partition
from app.services.hierarchical_index import (
    DOCUMENT_LEVEL,
    SECTION_LEVEL,
    HierarchyNode,
    HierarchySearchHit,
    normalize_section,
)
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
    assert fake_registry.node_search_calls == [("tech", DOCUMENT_LEVEL)]
    assert fake_registry.search_calls == []
    assert response.json()["answer_source"] == "none"
    assert response.json()["web_citations"] == []
    timing = response.json()["timing"]
    assert [item["partition"] for item in timing["retrieval"]] == ["tech"]
    assert timing["retrieval"][0]["elapsed_ms"] >= 0
    assert timing["router_llm_ms"] is None
    assert timing["answer_llm_ms"] is None


def test_hierarchical_retrieval_constrains_leaf_hits_and_keeps_chunk_citations(
    hierarchical_client,
    fake_registry,
    fake_hierarchy_registry,
):
    chunk_id = upload_ready_document(
        hierarchical_client, fake_registry, "tech", "hierarchy.md"
    )
    row = fake_registry.rows["tech"][chunk_id]
    document_id = row["document_id"]
    section = normalize_section(row["section"])
    document_node = HierarchyNode(
        id=f"hdoc:{document_id}",
        level=DOCUMENT_LEVEL,
        partition=Partition.TECH,
        document_id=document_id,
        section=None,
        text="技术制度",
    )
    section_node = HierarchyNode(
        id=f"hsec:{document_id}:example",
        level=SECTION_LEVEL,
        partition=Partition.TECH,
        document_id=document_id,
        section=section,
        text="技术制度章节",
    )
    fake_hierarchy_registry.search_results[("tech", DOCUMENT_LEVEL)] = [
        HierarchySearchHit(document_node, 0.92)
    ]
    fake_hierarchy_registry.search_results[("tech", SECTION_LEVEL)] = [
        HierarchySearchHit(section_node, 0.86)
    ]
    fake_registry.search_results["tech"] = [{"id": chunk_id, "score": 0.90}]

    response = hierarchical_client.post(
        "/api/v1/chat",
        json={"question": "技术制度怎么处理？", "partition_hint": "tech"},
    )

    payload = response.json()
    assert payload["code"] == "OK"
    assert [citation["chunk_id"] for citation in payload["citations"]] == [chunk_id]
    assert fake_hierarchy_registry.node_search_calls == [
        ("tech", DOCUMENT_LEVEL),
        ("tech", SECTION_LEVEL),
    ]
    assert fake_hierarchy_registry.search_document_constraints == [
        None,
        frozenset({document_id}),
    ]
    assert fake_registry.search_calls == ["tech"]
    assert fake_registry.search_section_constraints == [
        frozenset({(document_id, section)})
    ]


def test_hierarchical_parent_beams_ignore_chunk_min_score_and_log_diagnostics(
    hierarchical_client,
    fake_registry,
    fake_hierarchy_registry,
    caplog,
):
    chunk_id = upload_ready_document(
        hierarchical_client, fake_registry, "finance", "payment-policy.md"
    )
    row = fake_registry.rows["finance"][chunk_id]
    document_id = row["document_id"]
    section = normalize_section(row["section"])
    document_node = HierarchyNode(
        id=f"hdoc:{document_id}",
        level=DOCUMENT_LEVEL,
        partition=Partition.FINANCE,
        document_id=document_id,
        section=None,
        text="付款制度",
    )
    section_node = HierarchyNode(
        id=f"hsec:{document_id}:payment",
        level=SECTION_LEVEL,
        partition=Partition.FINANCE,
        document_id=document_id,
        section=section,
        text="付款批次",
    )
    fake_hierarchy_registry.search_results[("finance", DOCUMENT_LEVEL)] = [
        HierarchySearchHit(document_node, 0.12)
    ]
    fake_hierarchy_registry.search_results[("finance", SECTION_LEVEL)] = [
        HierarchySearchHit(section_node, 0.34)
    ]
    fake_registry.search_results["finance"] = [{"id": chunk_id, "score": 0.90}]

    caplog.set_level(logging.INFO)
    response = hierarchical_client.post(
        "/api/v1/chat",
        json={"question": "付款批次", "partition_hint": "finance"},
    )

    assert response.json()["code"] == "OK"
    assert [citation["chunk_id"] for citation in response.json()["citations"]] == [
        chunk_id
    ]
    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "level=document candidate_count=1" in message
        and "threshold_filtered_count=0" in message
        for message in messages
    )
    assert any(
        "level=section candidate_count=1" in message
        and "threshold_filtered_count=0" in message
        for message in messages
    )
    assert any(
        "level=chunk candidate_count=1" in message
        and "threshold_filtered_count=0" in message
        and "accepted_count=1" in message
        for message in messages
    )


def test_hierarchical_metadata_scopes_prevent_global_candidate_crowding(
    hierarchical_client,
    fake_registry,
    fake_hierarchy_registry,
):
    chunk_id = upload_ready_document(
        hierarchical_client, fake_registry, "tech", "scoped-hierarchy.md"
    )
    row = fake_registry.rows["tech"][chunk_id]
    document_id = row["document_id"]
    section = normalize_section(row["section"])
    document_node = HierarchyNode(
        id=f"hdoc:{document_id}",
        level=DOCUMENT_LEVEL,
        partition=Partition.TECH,
        document_id=document_id,
        section=None,
        text="目标文档",
    )
    section_node = HierarchyNode(
        id=f"hsec:{document_id}:target",
        level=SECTION_LEVEL,
        partition=Partition.TECH,
        document_id=document_id,
        section=section,
        text="目标章节",
    )
    section_distractors = [
        HierarchySearchHit(
            HierarchyNode(
                id=f"hsec:other-{position}",
                level=SECTION_LEVEL,
                partition=Partition.TECH,
                document_id=f"other-document-{position}",
                section="无关章节",
                text="无关章节",
            ),
            0.99,
        )
        for position in range(100)
    ]
    fake_hierarchy_registry.search_results[("tech", DOCUMENT_LEVEL)] = [
        HierarchySearchHit(document_node, 0.92)
    ]
    fake_hierarchy_registry.search_results[("tech", SECTION_LEVEL)] = [
        *section_distractors,
        HierarchySearchHit(section_node, 0.86),
    ]

    chunk_distractors = []
    for position in range(100):
        distractor_id = f"other-document-{position}:v1:00000"
        fake_registry.rows["tech"][distractor_id] = {
            "id": distractor_id,
            "document_id": f"other-document-{position}",
            "section": "无关章节",
        }
        chunk_distractors.append({"id": distractor_id, "score": 0.99})
    fake_registry.search_results["tech"] = [
        *chunk_distractors,
        {"id": chunk_id, "score": 0.90},
    ]

    response = hierarchical_client.post(
        "/api/v1/chat",
        json={"question": "目标章节的制度是什么？", "partition_hint": "tech"},
    )

    assert response.json()["code"] == "OK"
    assert [citation["chunk_id"] for citation in response.json()["citations"]] == [
        chunk_id
    ]
    assert fake_hierarchy_registry.search_document_constraints == [
        None,
        frozenset({document_id}),
    ]
    assert fake_registry.search_section_constraints == [
        frozenset({(document_id, section)})
    ]


def test_tree_only_returns_no_evidence_when_no_parent_nodes_exist(
    hierarchical_client,
    fake_registry,
    fake_hierarchy_registry,
):
    chunk_id = upload_ready_document(
        hierarchical_client, fake_registry, "tech", "fallback.md"
    )
    fake_registry.search_results["tech"] = [{"id": chunk_id, "score": 0.90}]
    fake_hierarchy_registry.search_results[("tech", DOCUMENT_LEVEL)] = []

    response = hierarchical_client.post(
        "/api/v1/chat",
        json={"question": "如何排查 502？", "partition_hint": "tech"},
    )

    assert response.json()["code"] == "NO_INTERNAL_EVIDENCE"
    assert fake_hierarchy_registry.node_search_calls == [("tech", DOCUMENT_LEVEL)]
    assert fake_registry.search_calls == []


def test_tree_only_reports_unavailable_parent_level(
    client,
    fake_registry,
):
    fake_registry.fail_next_node_search = True

    response = client.post(
        "/api/v1/chat",
        json={"question": "如何排查 502？", "partition_hint": "tech"},
    )

    assert response.status_code == 503
    assert response.json()["code"] == "INDEX_NOT_READY"
    assert response.json()["details"] == {
        "partition": "tech",
        "level": DOCUMENT_LEVEL,
    }


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
    assert fake_registry.node_search_calls == [("tech", DOCUMENT_LEVEL)]
    assert fake_registry.search_calls == []
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
    timing = payload["timing"]
    assert [item["partition"] for item in timing["retrieval"]] == [
        "tech",
        "finance",
    ]
    assert all(item["elapsed_ms"] >= 0 for item in timing["retrieval"])
    assert timing["router_llm_ms"] is not None
    assert timing["answer_llm_ms"] is not None


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
