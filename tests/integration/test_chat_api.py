def test_auto_mode_returns_clarification_without_search(client, fake_registry):
    response = client.post(
        "/api/v1/chat",
        json={"question": "这个制度怎么处理？", "partition_hint": None},
    )

    assert response.status_code == 200
    assert response.json()["code"] == "ROUTE_CLARIFICATION_REQUIRED"
    assert response.json()["route"] == "clarify"
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
    assert fake_registry.search_calls == ["tech"]


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
    assert fake_registry.search_calls == []


def test_invalid_chat_partition_uses_error_contract(client):
    response = client.post(
        "/api/v1/chat",
        json={"question": "问题", "partition_hint": "Finance"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_PARTITION"
    assert response.headers["X-Request-ID"] == response.json()["request_id"]
