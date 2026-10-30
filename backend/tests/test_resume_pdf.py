"""P2.3：真实 multipart/解析进程/隔离数据库；模型使用 HTTP MockTransport。"""
import asyncio
import io
import json
import multiprocessing

import httpx
import pytest
from fastapi import HTTPException
from openai import OpenAI
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from sqlalchemy import select, func
from starlette.requests import Request

from app.api.resume_upload import read_pdf_upload
from app.models.entities import AccessGrant, Resume, User
from app.rag.pdf_extractor import PDFError, extract_pdf_text
from tests.test_ws_recovery import api


def pdf_bytes(text="skills\nJava MySQL\nprojects\nBuilt a cache", *, pages=1, encrypted=False):
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=595, height=842)
        if text:
            font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"):
                DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
            escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream = DecodedStreamObject()
            lines = escaped.splitlines()
            stream.set_data(("BT /F1 12 Tf 50 790 Td 16 TL " +
                             " T* ".join(f"({line}) Tj" for line in lines) + " ET").encode("ascii"))
            page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("test-password")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def upload(client, data, *, filename="resume.pdf", media="application/pdf", name="Test User"):
    return client.post("/api/resume/pdf", files={"file": (filename, data, media)}, data={"name": name})


def test_pdf_upload_and_interview_access(api):
    client, factory = api
    result = upload(client, pdf_bytes())
    assert result.status_code == 200, result.text
    body = result.json()
    assert "Java" in body["skills"] and "MySQL" in body["skills"]
    assert body["projects"] == ["Built a cache"]
    assert body["education"] == ""
    assert len(body["access_token"]) == 64
    with factory() as db:
        saved = db.get(Resume, body["resume_id"])
        assert "Java MySQL" in saved.raw_text
        assert saved.structured["skills"] == body["skills"]
        assert db.get(AccessGrant, ("resume", saved.id)).token_hash != body["access_token"]
    payload = {"resume_id": body["resume_id"], "position": "java_backend"}
    assert client.post("/api/interview", json=payload).status_code == 403
    assert client.post("/api/interview", json=payload,
        headers={"X-Resume-Token": body["access_token"]}).status_code == 200


@pytest.mark.parametrize("data,code", [
    (pdf_bytes(text=""), "empty_pdf"),
    (pdf_bytes(encrypted=True), "encrypted_pdf"),
    (b"%PDF-1.7\ncorrupted", "invalid_pdf"),
    (b"plain text pretending to be pdf", "invalid_pdf"),
])
def test_invalid_pdfs_are_actionable_without_saving(api, data, code):
    client, factory = api
    response = upload(client, data)
    assert response.status_code == 422, response.text
    assert "粘贴" in response.json()["detail"]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Resume)) == 0
        assert db.scalar(select(func.count()).select_from(User)) == 0


@pytest.mark.parametrize("filename,media,data,status", [
    ("resume.txt", "application/pdf", b"hello", 415),
    ("resume.pdf", "text/plain", b"hello", 415),
    ("resume.pdf", "application/pdf", b"", 422),
])
def test_file_type_and_empty_upload(api, filename, media, data, status):
    client, _ = api
    response = upload(client, data, filename=filename, media=media)
    assert response.status_code == status


def test_configured_limits_and_page_text_rejection(api, monkeypatch):
    from app.api import routes
    client, _ = api
    monkeypatch.setattr(routes, "settings", routes.settings.model_copy(update={
        "resume_pdf_max_pages": 1, "resume_pdf_max_text_chars": 100,
    }))
    limits = client.get("/api/resume/limits").json()
    assert limits["pdf_max_pages"] == 1 and limits["ocr_supported"] is False
    assert upload(client, pdf_bytes(pages=2)).status_code == 413
    assert upload(client, pdf_bytes("a" * 101)).status_code == 413
    assert upload(client, pdf_bytes("a" * 100)).status_code == 200


def test_file_size_actual_bytes_not_just_declared_length(api, monkeypatch):
    from app.api import routes
    client, _ = api
    monkeypatch.setattr(routes, "settings", routes.settings.model_copy(update={"resume_pdf_max_bytes": 1024}))
    assert upload(client, b"%PDF-" + b"a" * 1024).status_code == 413
    body = (b'--limit\r\nContent-Disposition: form-data; name="file"; filename="r.pdf"\r\n'
            b'Content-Type: application/pdf\r\n\r\n' + b"a" * 1025 + b"\r\n--limit--\r\n")
    response = client.post("/api/resume/pdf", content=iter([body[:100], body[100:]]),
        headers={"Content-Type": "multipart/form-data; boundary=limit"})
    assert response.status_code == 413
    assert client.post("/api/resume/pdf", content=b"",
        headers={"Content-Type": "multipart/form-data; boundary=x", "Content-Length": "999999999"}).status_code == 413


def test_malformed_duplicate_and_unexpected_parts(api):
    client, _ = api
    assert client.post("/api/resume/pdf", json={"file": "x"}).status_code == 415
    assert client.post("/api/resume/pdf", files={"other": ("x.pdf", pdf_bytes(), "application/pdf")}).status_code == 422
    assert client.post("/api/resume/pdf", files=[("file", ("x.pdf", pdf_bytes(), "application/pdf"))] * 2).status_code == 422
    assert client.post("/api/resume/pdf", files={"file": ("x.pdf", pdf_bytes(), "application/pdf")},
                       data={"other": "unsupported"}).status_code == 422
    body = b'--x\r\nContent-Disposition: form-data; name="file"; filename="x.pdf"\r\nContent-Type: application/pdf\r\n\r\n%PDF-'
    assert client.post("/api/resume/pdf", content=body,
        headers={"Content-Type": "multipart/form-data; boundary=x"}).status_code == 422


def test_unicode_name_and_long_name(api):
    client, factory = api
    response = upload(client, pdf_bytes(), name="测试用户")
    assert response.status_code == 200
    with factory() as db:
        assert db.get(User, response.json()["user_id"]).name == "测试用户"
    assert upload(client, pdf_bytes(), name="a" * 65).status_code == 422


def test_upload_deadline():
    async def scenario():
        async def receive():
            await asyncio.sleep(10)
        scope = {"type": "http", "method": "POST", "path": "/api/resume/pdf",
                 "headers": [(b"content-type", b"multipart/form-data; boundary=x")]}
        with pytest.raises(HTTPException) as exc:
            await read_pdf_upload(Request(scope, receive), max_bytes=1024, timeout_seconds=0.01)
        assert exc.value.status_code == 408
    asyncio.run(scenario())


def test_parser_timeout_terminates_process_and_releases_slot():
    before = {p.pid for p in multiprocessing.active_children()}
    with pytest.raises(PDFError, match="pdf_timeout"):
        extract_pdf_text(pdf_bytes(), max_pages=10, max_chars=20000, timeout_seconds=0.000001)
    assert {p.pid for p in multiprocessing.active_children()} == before
    assert "Java" in extract_pdf_text(pdf_bytes(), max_pages=10, max_chars=20000, timeout_seconds=10)


def test_parser_busy_is_retryable(api, monkeypatch):
    from app.rag import pdf_extractor
    client, _ = api
    class Busy:
        def acquire(self, **kwargs): return False
    monkeypatch.setattr(pdf_extractor, "_slots", Busy())
    response = upload(client, pdf_bytes())
    assert response.status_code == 429 and response.headers["retry-after"] == "2"


def test_parser_startup_failure_releases_capacity(api, monkeypatch):
    from app.rag import pdf_extractor
    client, _ = api
    def unavailable(*args):
        raise OSError("injected process context failure")
    monkeypatch.setattr(pdf_extractor.multiprocessing, "get_context", unavailable)
    response = upload(client, pdf_bytes())
    assert response.status_code == 503
    assert pdf_extractor._slots.acquire(blocking=False)
    assert pdf_extractor._slots.acquire(blocking=False)
    pdf_extractor._slots.release()
    pdf_extractor._slots.release()


def test_header_limit_and_invalid_utf8_name(api):
    client, _ = api
    assert upload(client, pdf_bytes(), filename="a" * 4200 + ".pdf").status_code == 413
    body = (b'--x\r\nContent-Disposition: form-data; name="name"\r\n\r\n\xff\r\n'
            b'--x\r\nContent-Disposition: form-data; name="file"; filename="r.pdf"\r\n'
            b'Content-Type: application/pdf\r\n\r\n%PDF-1.7\r\n--x--\r\n')
    response = client.post("/api/resume/pdf", content=body,
        headers={"Content-Type": "multipart/form-data; boundary=x"})
    assert response.status_code == 422 and "UTF-8" in response.json()["detail"]


def test_pdf_pii_never_reaches_model_logs_or_storage(api, monkeypatch, caplog):
    from app.api import routes
    from app.llm.client import OpenAICompatibleLLM
    client, factory = api
    pii = ["13812345678", "test@example.com", "110101199001011234"]
    observed = []
    def handle(request):
        observed.append(json.loads(request.content))
        # 即便供应商输出重新包含PII，也必须二次脱敏。
        output = json.dumps({"skills": ["Java"], "projects": [pii[1]], "education": pii[0]})
        return httpx.Response(200, json={"id": "test", "object": "chat.completion", "created": 0,
            "model": "test", "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": output}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}})
    llm = OpenAICompatibleLLM(api_key="synthetic-key", base_url="https://llm.test/v1", model="test")
    llm._client.close()
    llm._client = OpenAI(api_key="synthetic-key", base_url="https://llm.test/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handle), trust_env=False))
    monkeypatch.setattr(routes, "build_llm", lambda _: llm)
    response = upload(client, pdf_bytes("skills\nJava\nprojects\n" + " ".join(pii)),
                      filename=pii[0] + ".pdf", name=pii[0])
    assert response.status_code == 200, response.text
    assert len(observed) == 1
    with factory() as db:
        saved = db.get(Resume, response.json()["resume_id"])
        user = db.get(User, saved.user_id)
        all_data = json.dumps(observed) + response.text + saved.raw_text + json.dumps(saved.structured) + user.name + caplog.text
        for value in pii:
            assert value not in all_data


def test_resume_and_grant_rollback_together(api, monkeypatch):
    from app.api import routes
    client, factory = api
    def fail(*args):
        raise RuntimeError("injected access grant failure")
    monkeypatch.setattr(routes, "issue_access", fail)
    with pytest.raises(RuntimeError, match="injected"):
        upload(client, pdf_bytes())
    with factory() as db:
        for model in (Resume, User, AccessGrant):
            assert db.scalar(select(func.count()).select_from(model)) == 0
