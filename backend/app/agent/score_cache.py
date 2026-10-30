"""评分缓存（P2 步骤 2.2）。

评审要求："如加缓存，键应包含题目/锚点版本、回答内容摘要、模型与提示词版本、评分配置；
使用有界缓存和保留策略。固定 temperature 不保证外部服务跨时间完全一致，
缓存一致性也不等于评测可重复性。"

因此：
- 键**必须**包含上述六项，任何一项变化都视为不同条目（避免"改了提示词却复用旧结果"）；
- **有界**（LRU 上限）+ **保留策略**（TTL），并提供命中率统计；
- **默认关闭**：这样"重复评测"默认走真实调用，需要时才显式开启。评审要求
  "缓存失效与无缓存重复评测分开"，默认关闭让无缓存口径成为基线。

⚠️ 两条必须如实声明的边界：
1. 命中缓存的两次评测**不构成**可重复性证据——它们连模型都没调用；
2. 缓存只写**模型成功**的结果。把降级结果缓存起来会让一次偶发故障固化成长期劣化。
"""
from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from typing import Callable

from app.agent.score_schema import PROMPT_VERSION, anchors_digest
from app.domain import Question, ScoreResult


@dataclass(frozen=True)
class ScoreCacheKey:
    question_id: str
    anchors_version: str
    answer_digest: str
    model_id: str
    prompt_version: str
    config_version: str

    def as_tuple(self) -> tuple[str, ...]:
        return (
            self.question_id, self.anchors_version, self.answer_digest,
            self.model_id, self.prompt_version, self.config_version,
        )


def answer_digest(answer: str) -> str:
    return hashlib.sha256(answer.encode("utf-8")).hexdigest()[:16]


def build_cache_key(
    question: Question,
    answer: str,
    *,
    model_id: str,
    config_version: str,
    prompt_version: str = PROMPT_VERSION,
) -> ScoreCacheKey:
    return ScoreCacheKey(
        question_id=question.id,
        anchors_version=anchors_digest(question),
        answer_digest=answer_digest(answer),
        model_id=model_id or "unknown",
        prompt_version=prompt_version,
        config_version=config_version or "default",
    )


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    stores: int = 0
    evictions: int = 0
    expired: int = 0

    def as_dict(self, *, size: int) -> dict:
        lookups = self.hits + self.misses
        return {
            "size": size,
            "hits": self.hits,
            "misses": self.misses,
            "stores": self.stores,
            "evictions": self.evictions,
            "expired": self.expired,
            "hit_rate": round(self.hits / lookups, 4) if lookups else 0.0,
        }


@dataclass
class ScoreCache:
    """线程安全的 LRU + TTL 缓存。

    默认关闭；开启后才参与评分链路。``max_entries <= 0`` 视为关闭。
    """

    max_entries: int = 512
    ttl_seconds: float = 3600.0
    enabled: bool = False
    _entries: OrderedDict = field(default_factory=OrderedDict, repr=False)
    _stats: CacheStats = field(default_factory=CacheStats, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def active(self) -> bool:
        return self.enabled and self.max_entries > 0

    def get(self, key: ScoreCacheKey) -> ScoreResult | None:
        if not self.active:
            return None
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key.as_tuple())
            if entry is None:
                self._stats.misses += 1
                return None
            stored_at, value = entry
            if self.ttl_seconds > 0 and now - stored_at > self.ttl_seconds:
                # 过期即删除，避免"过期条目仍占容量"。
                del self._entries[key.as_tuple()]
                self._stats.expired += 1
                self._stats.misses += 1
                return None
            self._entries.move_to_end(key.as_tuple())
            self._stats.hits += 1
            return value

    def set(self, key: ScoreCacheKey, value: ScoreResult) -> None:
        if not self.active:
            return
        with self._lock:
            self._entries[key.as_tuple()] = (time.monotonic(), value)
            self._entries.move_to_end(key.as_tuple())
            self._stats.stores += 1
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
                self._stats.evictions += 1

    def stats(self) -> dict:
        with self._lock:
            return self._stats.as_dict(size=len(self._entries))

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_cache = ScoreCache()
_cache_lock = threading.Lock()


def configure_cache(*, enabled: bool, max_entries: int, ttl_seconds: float) -> ScoreCache:
    """启动时配置进程级缓存。"""
    global _cache
    with _cache_lock:
        _cache = ScoreCache(
            max_entries=max_entries, ttl_seconds=ttl_seconds, enabled=enabled
        )
    return _cache


def get_score_cache() -> ScoreCache:
    return _cache


def reset_cache_for_tests(cache: ScoreCache | None = None) -> ScoreCache:
    """测试用：替换进程级缓存实例。"""
    global _cache
    with _cache_lock:
        _cache = cache or ScoreCache(enabled=False)
    return _cache
