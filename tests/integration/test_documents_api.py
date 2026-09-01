from io import BytesIO

from docx import Document
from reportlab.pdfgen import canvas


def upload_markdown(client, content: bytes | None = None, filename: str = "policy.md"):
    return client.post(
        "/api/v1/documents",
        files={"file": (filename, content or b"# Policy\n\nDemo amount is 600 yuan.", "text/markdown")},
        data={"partition": "finance", "title": "Demo policy"},
    )


def test_upload_preview_and_approve_into_confirmed_partition(client, fake_registry):
    upload = upload_markdown(client)
    assert upload.status_code == 201, upload.text
    payload = upload.json()
    assert payload["status"] == "pending_review"
    assert payload["confirmed_partition"] is None
    assert upload.headers["X-Request-ID"] == payload["request_id"]

    document_id = payload["document_id"]
    detail = client.get(f"/api/v1/documents/{document_id}")
    assert detail.status_code == 200
    assert "stored_path" not in detail.json()
    assert "checksum_sha256" not in detail.json()

    preview = client.get(f"/api/v1/documents/{document_id}/preview?limit=1&offset=0")
    assert preview.status_code == 200
    assert preview.json()["total"] == payload["chunk_count"]
    assert "embedding_text" not in preview.json()["items"][0]
    assert fake_registry.upsert_calls == []

    review = client.post(
        f"/api/v1/documents/{document_id}/review",
        json={
            "action": "approve",
            "confirmed_partition": "tech",
            "reviewer_name": "demo-reviewer",
            "note": "Corrected partition",
        },
    )
    assert review.status_code == 200, review.text
    assert review.json()["status"] == "ready"
    assert review.json()["selected_partition"] == "finance"
    assert review.json()["confirmed_partition"] == "tech"
    assert fake_registry.upsert_calls == ["tech"]
    assert fake_registry.rows["finance"] == {}
    assert fake_registry.rows["hr"] == {}


def test_reject_does_not_touch_any_index(client, fake_registry):
    document_id = upload_markdown(client, b"# Leave\n\nDemo leave policy.", "leave.md").json()["document_id"]
    response = client.post(
        f"/api/v1/documents/{document_id}/review",
        json={"action": "reject", "confirmed_partition": None, "reviewer_name": None, "note": "Incomplete"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert fake_registry.upsert_calls == []


def test_review_action_validation_uses_stable_error_codes(client):
    first = upload_markdown(client, b"# First\n\nReview validation one.", "first.md").json()["document_id"]
    missing_partition = client.post(
        f"/api/v1/documents/{first}/review",
        json={"action": "approve", "confirmed_partition": None, "reviewer_name": None, "note": None},
    )
    assert missing_partition.status_code == 422
    assert missing_partition.json()["code"] == "REVIEW_PARTITION_REQUIRED"

    second = upload_markdown(client, b"# Second\n\nReview validation two.", "second.md").json()["document_id"]
    reject_with_partition = client.post(
        f"/api/v1/documents/{second}/review",
        json={"action": "reject", "confirmed_partition": "hr", "reviewer_name": None, "note": None},
    )
    assert reject_with_partition.status_code == 422
    assert reject_with_partition.json()["code"] == "VALIDATION_ERROR"


def test_duplicate_upload_is_rejected_with_existing_document(client):
    content = b"# Stable\n\nSame content."
    first = upload_markdown(client, content)
    second = upload_markdown(client, content)
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["code"] == "DUPLICATE_DOCUMENT"
    assert second.json()["details"]["document_id"] == first.json()["document_id"]


def test_errors_use_contract_and_request_id(client):
    response = client.post(
        "/api/v1/documents",
        files={"file": ("policy.md", b"content", "text/markdown")},
        data={"partition": "Finance"},
        headers={"X-Request-ID": "req_frontend_123"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_PARTITION"
    assert response.json()["request_id"] == "req_frontend_123"
    assert response.headers["X-Request-ID"] == "req_frontend_123"
    assert "detail" not in response.json()


def test_path_traversal_filename_cannot_escape_storage(client, tmp_path):
    response = upload_markdown(client, filename="../../outside.md")
    assert response.status_code == 201
    assert response.json()["original_filename"] == "outside.md"
    assert not (tmp_path / "outside.md").exists()


def test_list_pagination_and_health(client):
    upload_markdown(client, b"# A\n\nFirst demo.", "a.md")
    upload_markdown(client, b"# B\n\nSecond demo.", "b.md")
    listing = client.get("/api/v1/documents?status=pending_review&limit=1&offset=1")
    assert listing.status_code == 200
    assert listing.json()["total"] == 2
    assert listing.json()["limit"] == 1
    assert listing.json()["offset"] == 1
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["indexes"] == {"finance": "ready", "hr": "ready", "tech": "ready"}


def test_framework_404_uses_error_contract(client):
    response = client.get("/api/v1/not-a-route")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    assert response.headers["X-Request-ID"] == response.json()["request_id"]


def test_txt_pdf_docx_and_markdown_uploads(client):
    docx_buffer = BytesIO()
    document = Document()
    document.add_heading("DOCX Demo", level=1)
    document.add_paragraph("Approval material list.")
    document.save(docx_buffer)

    pdf_buffer = BytesIO()
    pdf = canvas.Canvas(pdf_buffer)
    pdf.drawString(72, 720, "PDF demo approval process")
    pdf.save()

    samples = [
        ("demo.txt", b"Plain text demo policy.", "text/plain"),
        ("demo.md", b"# Markdown\n\nMarkdown demo policy.", "text/markdown"),
        (
            "demo.docx",
            docx_buffer.getvalue(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("demo.pdf", pdf_buffer.getvalue(), "application/pdf"),
    ]
    for filename, content, mime_type in samples:
        response = client.post(
            "/api/v1/documents",
            files={"file": (filename, content, mime_type)},
            data={"partition": "hr"},
        )
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "pending_review"
        assert response.json()["chunk_count"] >= 1


def test_content_and_extension_mismatch_is_rejected(client):
    response = client.post(
        "/api/v1/documents",
        files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
        data={"partition": "finance"},
    )
    assert response.status_code == 415
    assert response.json()["code"] == "UNSUPPORTED_FILE_TYPE"


def test_index_failure_compensates_and_marks_document_failed(client, fake_registry):
    document_id = upload_markdown(
        client, b"# Failure\n\nCompensation path unique content.", "failure.md"
    ).json()["document_id"]
    fake_registry.fail_after_upsert = True
    response = client.post(
        f"/api/v1/documents/{document_id}/review",
        json={
            "action": "approve",
            "confirmed_partition": "finance",
            "reviewer_name": None,
            "note": None,
        },
    )
    assert response.status_code == 500
    assert response.json()["code"] == "INDEX_WRITE_FAILED"
    assert fake_registry.delete_calls == ["finance"]
    assert fake_registry.rows["finance"] == {}
    detail = client.get(f"/api/v1/documents/{document_id}")
    assert detail.json()["status"] == "failed"
    assert detail.json()["error_code"] == "INDEX_WRITE_FAILED"
