"""Opt-in regression against a running service backed by real txtai data.

This test is skipped in the default suite because it reads an operator-selected
business document and can invoke the configured Answer model.
"""

import json
import os
from urllib.request import Request, urlopen

import pytest


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        pytest.fail(f"{name} must be set when RUN_REAL_TXTAI_REGRESSION=1")
    return value


@pytest.mark.skipif(
    os.getenv("RUN_REAL_TXTAI_REGRESSION") != "1",
    reason="set RUN_REAL_TXTAI_REGRESSION=1 for an operator-approved live check",
)
def test_exact_section_title_is_retrieved_from_real_txtai() -> None:
    base_url = _required("REAL_TXTAI_BASE_URL").rstrip("/")
    query = _required("REAL_TXTAI_QUERY")
    partition = _required("REAL_TXTAI_PARTITION")
    expected_section = _required("REAL_TXTAI_EXPECTED_SECTION")
    expected_document_id = os.getenv("REAL_TXTAI_EXPECTED_DOCUMENT_ID", "").strip()
    body = json.dumps(
        {
            "question": query,
            "partition_hint": partition,
            "allow_web_fallback": False,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        f"{base_url}/api/v1/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(request, timeout=120) as response:
        payload = json.load(response)

    assert payload["code"] == "OK"
    citations = payload["citations"]
    assert any(item["section"] == expected_section for item in citations)
    if expected_document_id:
        assert any(item["document_id"] == expected_document_id for item in citations)
