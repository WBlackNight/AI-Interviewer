"""离线词法向量基线与可替换的Embedding接口。

字符1–3 gram经过SHA256映射到固定维度；这是词法哈希，不是训练出的语义模型。
hash不调用网络；zhipu通过显式配置调用官方Embedding-3，输入先做基本PII脱敏。
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
import time
import unicodedata
from dataclasses import asdict, dataclass
from typing import Protocol, Sequence
from urllib.parse import urlsplit

import httpx

from app.security import sanitize_pii


class EmbeddingError(ValueError):
    pass


@dataclass(frozen=True)
class EmbeddingSpec:
    provider: str = "hash"
    model: str = "char-ngram-hash-v1"
    revision: str = "1"
    dimensions: int = 256
    normalization: str = "l2"
    metric: str = "cosine"

    def as_dict(self) -> dict:
        return asdict(self)


class Embedder(Protocol):
    @property
    def spec(self) -> EmbeddingSpec: ...
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def normalize_vector(values: Sequence[float], dimensions: int) -> list[float]:
    if len(values) != dimensions or any(type(v) not in (float, int) or not math.isfinite(v) for v in values):
        raise EmbeddingError("invalid_vector")
    norm = math.hypot(*values)
    if not math.isfinite(norm) or norm == 0:
        raise EmbeddingError("zero_or_nonfinite_norm")
    return [float(v / norm) for v in values]


class HashEmbedder:
    def __init__(self, dimensions: int = 256):
        if not 16 <= dimensions <= 4096:
            raise EmbeddingError("invalid_dimensions")
        self._spec = EmbeddingSpec(dimensions=dimensions)

    @property
    def spec(self) -> EmbeddingSpec:
        return self._spec

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        result = []
        for text in texts:
            compact = "".join(unicodedata.normalize("NFKC", text).lower().split())
            if not compact or len(compact) > 20000:
                raise EmbeddingError("empty_or_oversized_input")
            vector = [0.0] * self.spec.dimensions
            for size in (1, 2, 3):
                for offset in range(len(compact) - size + 1):
                    gram = compact[offset:offset + size]
                    digest = hashlib.sha256(f"{size}:{gram}".encode("utf-8")).digest()
                    vector[int.from_bytes(digest[:8], "big") % len(vector)] += 1.0
            result.append(normalize_vector(vector, self.spec.dimensions))
        return result


class ZhipuEmbedder:
    """官方Embedding-3 HTTP适配；无自动重试，避免未知计费被重复执行。"""

    def __init__(self, api_key: str | None, *, base_url="https://open.bigmodel.cn/api/paas/v4",
                 model="embedding-3", dimensions=1024, revision="1", timeout=15):
        url = urlsplit(base_url)
        if (url.scheme != "https" or url.hostname != "open.bigmodel.cn" or url.port not in (None, 443)
                or url.username or url.password or url.query or url.fragment
                or url.path.rstrip("/") != "/api/paas/v4"):
            raise EmbeddingError("invalid_provider_endpoint")
        if not api_key or model != "embedding-3" or dimensions not in (256, 512, 1024, 2048):
            raise EmbeddingError("invalid_provider_configuration")
        self._key = api_key
        self._url = base_url.rstrip("/") + "/embeddings"
        self._timeout = timeout
        self._spec = EmbeddingSpec(provider="zhipu", model=model, revision=revision, dimensions=dimensions)
        self._calls, self._tokens, self._unknown = 0, 0, 0
        self._lock = threading.Lock()

    @property
    def spec(self) -> EmbeddingSpec:
        return self._spec

    def usage(self) -> dict:
        with self._lock:
            return dict(network_calls=self._calls, provider_reported_tokens=self._tokens,
                        unknown_usage_calls=self._unknown, currency_cost=None)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts or any(not isinstance(t, str) or not t.strip() or len(t) > 3000 for t in texts):
            raise EmbeddingError("invalid_input")
        result = []
        try:
            with httpx.Client(trust_env=False, follow_redirects=False) as client:
                for start in range(0, len(texts), 8):
                    batch = [sanitize_pii(t) for t in texts[start:start + 8]]
                    deadline = time.monotonic() + self._timeout
                    with self._lock:
                        self._calls += 1
                    usage_known = False
                    try:
                        with client.stream("POST", self._url,
                            headers={"Authorization": "Bearer " + self._key},
                            json={"model": self.spec.model, "dimensions": self.spec.dimensions, "input": batch},
                            timeout=self._timeout) as response:
                            if response.status_code != 200:
                                raise EmbeddingError("provider_http_" + str(response.status_code))
                            raw = bytearray()
                            for chunk in response.iter_bytes(chunk_size=8192):
                                if len(raw) + len(chunk) > 4 * 1024 * 1024 or time.monotonic() > deadline:
                                    raise EmbeddingError("provider_response_limit")
                                raw.extend(chunk)
                        data = json.loads(raw)
                        if not isinstance(data, dict):
                            raise EmbeddingError("provider_payload_invalid")
                        usage = data.get("usage")
                        tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
                        if type(tokens) is int and tokens >= 0:
                            with self._lock:
                                self._tokens += tokens
                            usage_known = True
                    finally:
                        if not usage_known:
                            with self._lock:
                                self._unknown += 1
                    if data.get("model") != self.spec.model or not isinstance(data.get("data"), list):
                        raise EmbeddingError("provider_payload_invalid")
                    rows = data["data"]
                    if len(rows) != len(batch) or any(
                            not isinstance(r, dict) or type(r.get("index")) is not int for r in rows):
                        raise EmbeddingError("provider_count_invalid")
                    if sorted(r["index"] for r in rows) != list(range(len(batch))):
                        raise EmbeddingError("provider_indices_invalid")
                    result.extend(normalize_vector(r["embedding"], self.spec.dimensions)
                                  for r in sorted(rows, key=lambda r: r["index"]))
            return result
        except EmbeddingError:
            raise
        except Exception:
            raise EmbeddingError("provider_request_failed") from None


def build_embedder(settings) -> Embedder:
    if settings.embedding_provider == "hash":
        if settings.embedding_model != "char-ngram-hash-v1":
            raise EmbeddingError("invalid_hash_model")
        return HashEmbedder(settings.embedding_dimensions)
    return ZhipuEmbedder(settings.embedding_api_key, base_url=settings.embedding_base_url,
        model=settings.embedding_model, dimensions=settings.embedding_dimensions,
        revision=settings.embedding_revision, timeout=settings.embedding_timeout_seconds)
