"""真实协议的离线故障注入；全部使用假密钥与MockTransport。"""
import json
import math

import httpx
import pytest

from app.config import Settings
from app.factories import load_assets
from app.rag.embeddings import EmbeddingError, ZhipuEmbedder, build_embedder
from app.rag.retriever import QuestionFilter
from app.rag.vector_index import build_index
from tests.test_retrieval import sample


def payload(count=1):
    return {"model": "embedding-3", "data": [
        {"index": i, "embedding": [float(i + 1), 1.] + [0.] * 254}
        for i in range(count)], "usage": {"total_tokens": count * 7}}


def mock_http(monkeypatch, handler):
    original = httpx.Client
    def factory(**kwargs):
        assert kwargs == {"trust_env": False, "follow_redirects": False}
        return original(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(httpx, "Client", factory)


def test_batches_order_normalization_pii_and_usage(monkeypatch):
    calls = []
    def handler(request):
        data = json.loads(request.content)
        assert request.url == "https://open.bigmodel.cn/api/paas/v4/embeddings"
        assert request.headers["Authorization"] == "Bearer fake-key"
        assert data["model"] == "embedding-3" and data["dimensions"] == 256
        assert "13812345678" not in request.content.decode()
        assert "a@example.com" not in request.content.decode()
        calls.append(len(data["input"]))
        result = payload(calls[-1])
        result["data"].reverse()
        return httpx.Response(200, json=result)
    mock_http(monkeypatch, handler)
    embedder = ZhipuEmbedder("fake-key", dimensions=256)
    vectors = embedder.embed(["数据库 13812345678 a@example.com"] * 9)
    assert calls == [8, 1] and len(vectors) == 9
    assert all(math.isclose(math.hypot(*v), 1) for v in vectors)
    assert vectors[0][0] < vectors[1][0]
    assert embedder.usage() == dict(network_calls=2, provider_reported_tokens=63,
                                   unknown_usage_calls=0, currency_cost=None)


@pytest.mark.parametrize("status", [301, 401, 403, 429, 500, 503])
def test_http_failures_no_retry_no_provider_body_or_secret(monkeypatch, status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="fake-key raw private body", headers={"Location": "https://example.com"})
    mock_http(monkeypatch, handler)
    embedder = ZhipuEmbedder("fake-key", dimensions=256)
    with pytest.raises(EmbeddingError, match=f"^provider_http_{status}$"):
        embedder.embed(["数据库"])
    assert len(calls) == 1 and embedder.usage()["unknown_usage_calls"] == 1


@pytest.mark.parametrize("change", ["model", "count", "duplicate", "bool_index", "dimension", "zero", "nan", "row"])
def test_invalid_provider_vectors_fail_closed(monkeypatch, change):
    result = payload(2)
    if change == "model": result["model"] = "other-model"
    if change == "count": result["data"].pop()
    if change == "duplicate": result["data"][1]["index"] = 0
    if change == "bool_index": result["data"][0]["index"] = False
    if change == "dimension": result["data"][0]["embedding"].pop()
    if change == "zero": result["data"][0]["embedding"] = [0.] * 256
    if change == "nan": result["data"][0]["embedding"][0] = float("nan")
    if change == "row": result["data"][0] = None
    # content允许模拟供应商返回非标准NaN，不经过httpx严格JSON编码。
    mock_http(monkeypatch, lambda request: httpx.Response(200, content=json.dumps(result).encode()))
    embedder = ZhipuEmbedder("fake-key", dimensions=256)
    with pytest.raises(EmbeddingError):
        embedder.embed(["数据库", "事务"])
    assert embedder.usage()["provider_reported_tokens"] == 14


@pytest.mark.parametrize("response", [b"no json", b"[]", b'{"usage": {"total_tokens": true}}'])
def test_malformed_payload_marks_usage_unknown(monkeypatch, response):
    mock_http(monkeypatch, lambda request: httpx.Response(200, content=response))
    embedder = ZhipuEmbedder("fake-key", dimensions=256)
    with pytest.raises(EmbeddingError): embedder.embed(["数据库"])
    assert embedder.usage()["unknown_usage_calls"] == 1


def test_timeout_message_sanitized(monkeypatch):
    def handler(request): raise httpx.ReadTimeout("fake-key private message", request=request)
    mock_http(monkeypatch, handler)
    embedder = ZhipuEmbedder("fake-key", dimensions=256)
    with pytest.raises(EmbeddingError, match="^provider_request_failed$"):
        embedder.embed(["数据库"])
    assert embedder.usage()["network_calls"] == embedder.usage()["unknown_usage_calls"] == 1


def test_response_size_bound(monkeypatch):
    mock_http(monkeypatch, lambda request: httpx.Response(200, content=b"x" * (4 * 1024 * 1024 + 1)))
    with pytest.raises(EmbeddingError, match="provider_response_limit"):
        ZhipuEmbedder("fake-key", dimensions=256).embed(["数据库"])


@pytest.mark.parametrize("url", ["http://open.bigmodel.cn/api/paas/v4", "https://example.com/api/paas/v4",
    "https://open.bigmodel.cn/api/paas/v4?key=x", "https://user@open.bigmodel.cn/api/paas/v4",
    "https://open.bigmodel.cn:444/api/paas/v4", "https://open.bigmodel.cn/wrong"])
def test_credentials_only_sent_to_official_endpoint(url):
    with pytest.raises(EmbeddingError): ZhipuEmbedder("fake-key", base_url=url)


@pytest.mark.parametrize("texts", [[], [""], [" "], [None], ["x" * 3001]])
def test_invalid_input_never_calls_provider(monkeypatch, texts):
    monkeypatch.setattr(httpx, "Client", lambda **kw: pytest.fail("must not call"))
    with pytest.raises(EmbeddingError): ZhipuEmbedder("fake-key").embed(texts)


def test_factory_index_reuse_and_failure_fallback(tmp_path, monkeypatch):
    from app.rag.question_bank import QuestionBank
    questions = sample()
    config = Settings(_env_file=None, embedding_provider="zhipu", embedding_model="embedding-3",
        embedding_dimensions=256, embedding_api_key="fake-key", retrieval_provider="hybrid",
        retrieval_index_path=tmp_path / "zhipu.json")
    mock_http(monkeypatch, lambda request: httpx.Response(200, json=payload(len(json.loads(request.content)["input"]))))
    embedder = build_embedder(config)
    build_index(config.retrieval_index_path, questions, embedder)
    monkeypatch.setattr(QuestionBank, "load", lambda path: QuestionBank(questions))
    # 启动和重复构建不调用远程API；查询失败后才回退。
    mock_http(monkeypatch, lambda request: httpx.Response(429, text="private"))
    _, changed = build_index(config.retrieval_index_path, questions, embedder)
    assert not changed and embedder.usage()["network_calls"] == 1
    _, bank = load_assets(config)
    assert bank.diagnostics()["embedding_usage"]["network_calls"] == 0
    result = bank.search("数据库", QuestionFilter(position="java", theme="DB"), top_k=2)
    assert result.actual == "bm25" and result.fallback_reason == "embedding_failed"
    assert "fake-key" not in repr(config) + json.dumps(bank.diagnostics())
