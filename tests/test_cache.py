"""D11 Redis 缓存层：后端降级、TTL、检索缓存失效、多轮会话记忆。

单测一律用进程内后端（conftest 里已强制），不依赖真实 Redis；
真连服务器的联调在 tests/test_cache_integration.py（pytest -m integration）。
"""
import time

import pytest

from app import cache, retriever
from tests.stubs import FakeRedis


def _hits(prefix="片段", n=2):
    return [{"text": f"{prefix}{i}", "source": "讲义.md", "via": "vector", "rrf_score": 0.01}
            for i in range(n)]


# ---------------- 后端选择与降级 ----------------
def test_falls_back_to_memory_when_redis_unavailable(monkeypatch):
    monkeypatch.setattr(cache, "_connect", lambda: None)
    cache.set_backend(None)
    assert cache.backend_name() == "memory"
    cache.set_json("ashore:test:kv", {"x": 1})
    assert cache.get_json("ashore:test:kv") == {"x": 1}


def test_uses_redis_backend_when_connect_succeeds(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache, "_connect", lambda: fake)
    cache.set_backend(None)
    assert cache.backend_name() == "redis"
    assert cache.backend() is fake


def test_unexpected_connect_error_still_degrades(monkeypatch):
    """_connect 内部已经兜了异常，这里再兜一层：任何意外都不能把请求打挂。"""

    def boom():
        raise RuntimeError("连接池炸了")

    monkeypatch.setattr(cache, "_connect", boom)
    cache.set_backend(None)
    assert cache.backend_name() == "memory"


def test_connect_is_attempted_only_once(monkeypatch):
    """探测只做一次，不能每个请求都去连一次 Redis。"""
    calls = []

    def connect():
        calls.append(1)
        return None

    monkeypatch.setattr(cache, "_connect", connect)
    cache.set_backend(None)
    for _ in range(5):
        cache.backend()
    assert len(calls) == 1


# ---------------- 通用 KV ----------------
def test_json_roundtrip():
    cache.set_json("ashore:test:kv", {"a": [1, 2], "b": "中文"})
    assert cache.get_json("ashore:test:kv") == {"a": [1, 2], "b": "中文"}


def test_missing_key_returns_none():
    assert cache.get_json("ashore:test:nope") is None


def test_expired_key_returns_none():
    cache.set_json("ashore:test:ttl", {"x": 1}, ttl=0.05)
    time.sleep(0.08)
    assert cache.get_json("ashore:test:ttl") is None


def test_corrupt_value_is_dropped():
    """坏缓存要清掉，否则会一直命中脏数据。"""
    cache.backend().set("ashore:test:bad", "{不是 JSON", ex=60)
    assert cache.get_json("ashore:test:bad") is None
    assert cache.backend().get("ashore:test:bad") is None


def test_stats_count_hit_and_miss():
    cache.reset_stats()
    cache.set_json("ashore:test:stat", {"x": 1})
    cache.get_json("ashore:test:stat")
    cache.get_json("ashore:test:stat")
    cache.get_json("ashore:test:missing")
    info = cache.stats()
    assert info["hit"] == 2
    assert info["miss"] == 1
    assert info["hit_rate"] == pytest.approx(2 / 3, abs=1e-4)


# ---------------- 检索缓存 ----------------
def test_retrieval_cache_hits_on_second_call(monkeypatch):
    calls = []

    def fake(query, top_k=5):
        calls.append(query)
        return _hits()

    monkeypatch.setattr(retriever, "hybrid_search", fake)
    first = retriever.cached_hybrid_search("定积分怎么算", top_k=4)
    second = retriever.cached_hybrid_search("定积分怎么算", top_k=4)
    assert len(calls) == 1          # 第二次没落到真检索
    assert first == second


def test_retrieval_cache_invalidated_by_kb_version_bump(monkeypatch):
    """重新入库后必须重新检索，否则用户会拿到已经作废的切片。"""
    calls = []
    monkeypatch.setattr(retriever, "hybrid_search",
                        lambda q, top_k=5: (calls.append(q), _hits())[1])

    retriever.cached_hybrid_search("定积分怎么算", top_k=4)
    old_key = cache.retrieval_key("定积分怎么算", 4)

    cache.bump_kb_version()

    new_key = cache.retrieval_key("定积分怎么算", 4)
    assert old_key != new_key

    retriever.cached_hybrid_search("定积分怎么算", top_k=4)
    assert len(calls) == 2


def test_retrieval_key_differs_by_top_k():
    assert cache.retrieval_key("定积分", 4) != cache.retrieval_key("定积分", 8)


def test_retrieval_key_normalises_whitespace_and_case():
    assert cache.retrieval_key(" Definite Integral ", 4) == cache.retrieval_key("definite integral", 4)


def test_empty_result_is_not_cached(monkeypatch):
    """空结果不写缓存，否则「知识库还没入库」会被固化一小时。"""
    calls = []
    monkeypatch.setattr(retriever, "hybrid_search", lambda q, top_k=5: (calls.append(q), [])[1])
    retriever.cached_hybrid_search("讲义里没有的词", top_k=4)
    retriever.cached_hybrid_search("讲义里没有的词", top_k=4)
    assert len(calls) == 2


# ---------------- 会话记忆 ----------------
def test_session_roundtrip_keeps_chronological_order():
    messages = [{"role": "human", "content": "第一问"},
                {"role": "ai", "content": "第一答"},
                {"role": "human", "content": "第二问"}]
    cache.session_save("u_sess", messages)
    assert cache.session_load("u_sess") == messages


def test_session_keeps_only_latest_messages():
    messages = [{"role": "human", "content": f"m{i}"} for i in range(30)]
    cache.session_save("u_cap", messages, limit=5)
    loaded = cache.session_load("u_cap", limit=5)
    assert [m["content"] for m in loaded] == ["m25", "m26", "m27", "m28", "m29"]


def test_session_sets_ttl():
    cache.session_save("u_ttl", [{"role": "human", "content": "hi"}], ttl=120)
    assert 0 < cache.backend().ttl(cache.session_key("u_ttl")) <= 120


def test_session_clear():
    cache.session_save("u_clear", [{"role": "human", "content": "hi"}])
    cache.session_clear("u_clear")
    assert cache.session_load("u_clear") == []


def test_session_users_lists_keys():
    cache.session_save("u_a", [{"role": "human", "content": "a"}])
    cache.session_save("u_b", [{"role": "human", "content": "b"}])
    assert {"u_a", "u_b"} <= set(cache.session_users())


def test_session_handles_newlines_and_quotes():
    text = "带换行\n和引号\"的文本"
    cache.session_save("u_json", [{"role": "human", "content": text}])
    assert cache.session_load("u_json")[0]["content"] == text


def test_session_handles_unserialisable_message():
    """写不进 JSON 也不能把请求打挂。"""
    cache.session_save("u_weird", [{"role": "human", "content": object()}])
    assert len(cache.session_load("u_weird")) == 1


def test_flush_only_touches_ashore_prefix():
    cache.set_json("ashore:test:flush", {"x": 1})
    cache.backend().set("someone_else:key", "别动我")
    cache.flush()
    assert cache.get_json("ashore:test:flush") is None
    assert cache.backend().get("someone_else:key") == "别动我"
