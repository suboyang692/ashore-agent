"""研岸 D11：Redis 缓存层 —— 检索结果缓存 + 多轮会话外置。

三个键空间：
    ashore:kb:version                知识库版本号（每次 ingest 成功后 +1）
    ashore:ret:{版本}:{查询指纹}      混合检索结果缓存（JSON，TTL 默认 1h）
    ashore:sess:{user_id}            多轮会话记忆（List，只留最近 N 条，滑动过期）

为什么检索缓存的 key 里要编进知识库版本号：
    re-ingest 之后旧切片已经作废，如果只按 query 缓存，用户会拿到已经不存在的
    切片。常见写法是入库后删掉 ashore:ret:* —— KEYS 会阻塞整个 Redis，SCAN 也要
    全量遍历。这里改成入库后 INCR 一次版本号：旧 key 再也命中不到，剩下的交给
    TTL 自然回收，失效动作是 O(1) 且不阻塞。

为什么会话要外置：
    原来 router_agent 用进程内 dict 存多轮记忆，uvicorn 起多 worker
    （--workers 4）时同一用户会被轮询到不同进程，上下文直接丢；进程重启也全清。
    放进 Redis 后多 worker 共享，并带 TTL，不会无限增长。

降级策略：
    Redis 连不上时自动退回进程内实现，业务不中断（tests/test_cache.py 覆盖了这条
    路径）。当前后端用 backend_name() 查看，也会出现在 GET /cache/stats。
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import logging
import threading
import time

from app.config import (
    CACHE_TTL,
    REDIS_ENABLED,
    REDIS_TIMEOUT,
    REDIS_URL,
    SESSION_MAX,
    SESSION_TTL,
)

log = logging.getLogger("ashore.cache")

KB_VERSION_KEY = "ashore:kb:version"
RET_PREFIX = "ashore:ret"
SESS_PREFIX = "ashore:sess"
ALL_PREFIX = "ashore:"


class MemoryBackend:
    """进程内降级实现：只实现本项目用到的那几条 Redis 命令，语义与 Redis 对齐。

    刻意保持「命令级」接口（get/set/incr/lpush/ltrim/lrange/expire/ttl/scan_iter），
    这样上层代码只有一份，切换后端不需要改调用方，测试里也能用同一个类假装
    redis-py 客户端来验证 Redis 分支。
    """

    name = "memory"

    def __init__(self):
        self._lock = threading.RLock()
        self._data = {}     # key -> str 或 list
        self._expire = {}   # key -> monotonic 截止时间

    # ---- 内部 ----
    def _drop_if_expired(self, key):
        deadline = self._expire.get(key)
        if deadline is not None and deadline <= time.monotonic():
            self._data.pop(key, None)
            self._expire.pop(key, None)
            return True
        return False

    def _live(self, key):
        self._drop_if_expired(key)
        return self._data.get(key)

    @staticmethod
    def _clamp(lst, start, stop):
        n = len(lst)
        if start < 0:
            start += n
        if stop < 0:
            stop += n
        return max(start, 0), min(stop, n - 1)

    # ---- Redis 命令子集 ----
    def ping(self):
        return True

    def get(self, key):
        with self._lock:
            value = self._live(key)
            return value if isinstance(value, str) else None

    def set(self, key, value, ex=None):
        with self._lock:
            self._drop_if_expired(key)
            self._data[key] = str(value)
            if ex is None:
                self._expire.pop(key, None)
            else:
                self._expire[key] = time.monotonic() + float(ex)
            return True

    def delete(self, *keys):
        with self._lock:
            removed = 0
            for key in keys:
                if self._data.pop(key, None) is not None:
                    removed += 1
                self._expire.pop(key, None)
            return removed

    def exists(self, key):
        with self._lock:
            return 1 if self._live(key) is not None else 0

    def incr(self, key, amount=1):
        with self._lock:
            value = int(self._live(key) or 0) + int(amount)
            self._data[key] = str(value)
            return value

    def lpush(self, key, *values):
        with self._lock:
            lst = self._live(key)
            if lst is None:
                lst = []
                self._data[key] = lst
            if not isinstance(lst, list):
                raise ValueError(f"{key} 已被非 list 值占用")
            for value in values:
                lst.insert(0, value)
            return len(lst)

    def ltrim(self, key, start, stop):
        with self._lock:
            lst = self._live(key)
            if isinstance(lst, list):
                start, stop = self._clamp(lst, int(start), int(stop))
                self._data[key] = lst[start:stop + 1] if start <= stop else []
            return True

    def lrange(self, key, start, stop):
        with self._lock:
            lst = self._live(key)
            if not isinstance(lst, list):
                return []
            start, stop = self._clamp(lst, int(start), int(stop))
            return lst[start:stop + 1] if start <= stop else []

    def expire(self, key, ttl):
        with self._lock:
            if self._live(key) is None:
                return False
            self._expire[key] = time.monotonic() + float(ttl)
            return True

    def ttl(self, key):
        with self._lock:
            if self._live(key) is None:
                return -2
            deadline = self._expire.get(key)
            return -1 if deadline is None else max(int(deadline - time.monotonic()), 0)

    def scan_iter(self, match="*"):
        with self._lock:
            for key in list(self._data):
                self._drop_if_expired(key)
            keys = [key for key in self._data if fnmatch.fnmatch(key, match)]
        for key in keys:          # 不在锁内 yield，避免遍历期间长时间占锁
            yield key

    def flushdb(self):
        with self._lock:
            self._data.clear()
            self._expire.clear()
            return True


_MEMORY = MemoryBackend()      # 降级后端（单例）
_backend = None                # None 表示尚未探测
_stats = {"hit": 0, "miss": 0, "write": 0}
_stats_lock = threading.Lock()


def _connect():
    """尝试连真实 Redis；任何异常都返回 None，由调用方降级。"""
    if not REDIS_ENABLED:
        log.info("REDIS_ENABLED=false，直接使用进程内缓存")
        return None
    try:
        import redis

        client = redis.Redis.from_url(
            REDIS_URL, decode_responses=True,
            socket_connect_timeout=REDIS_TIMEOUT, socket_timeout=REDIS_TIMEOUT,
        )
        client.ping()
        log.info("已连接 Redis：%s", REDIS_URL)
        return client
    except Exception as exc:                      # 连不上 / 没装 redis 库 / 认证失败
        log.warning("Redis 不可用（%s），降级为进程内缓存：%s", REDIS_URL, exc)
        return None


def backend():
    """当前后端实例；首次调用时探测 Redis，失败则用进程内实现。"""
    global _backend
    if _backend is None:
        try:
            client = _connect()
        except Exception as exc:                  # _connect 之外的意外也不能拖垮请求
            log.warning("连接 Redis 时出现异常，降级为进程内缓存：%s", exc)
            client = None
        _backend = client if client is not None else _MEMORY
    return _backend


def backend_name():
    """返回 'redis' 或 'memory'。"""
    return "memory" if backend() is _MEMORY else "redis"


def memory_backend():
    return _MEMORY


def set_backend(client):
    """显式指定后端（测试/脚本用）；传 None 恢复为下次调用时自动探测。"""
    global _backend
    _backend = client


# ---------- 统计 ----------
def _count(field, amount=1):
    with _stats_lock:
        _stats[field] += amount


def reset_stats():
    with _stats_lock:
        for key in _stats:
            _stats[key] = 0


def stats():
    """缓存概况：后端、命中率、键数量、知识库版本号。"""
    with _stats_lock:
        snapshot = dict(_stats)
    total = snapshot["hit"] + snapshot["miss"]
    snapshot["hit_rate"] = round(snapshot["hit"] / total, 4) if total else 0.0
    snapshot["backend"] = backend_name()
    snapshot["kb_version"] = kb_version()
    snapshot["keys"] = key_count()
    snapshot["sessions"] = len(session_users())
    return snapshot


def key_count(prefix=ALL_PREFIX):
    return sum(1 for _ in backend().scan_iter(match=f"{prefix}*"))


# ---------- 通用 KV（JSON）----------
def get_json(key):
    raw = backend().get(key)
    if raw is None:
        _count("miss")
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        backend().delete(key)        # 脏数据直接清掉，否则会一直命中坏缓存
        _count("miss")
        return None
    _count("hit")
    return value


def set_json(key, value, ttl=CACHE_TTL):
    backend().set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
    _count("write")


# ---------- 检索缓存 ----------
def query_fingerprint(query, top_k):
    """查询指纹：统一大小写与首尾空白，避免「定积分 」和「定积分」各存一份。"""
    raw = f"{top_k}|{query.strip().lower()}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def retrieval_key(query, top_k, version=None):
    version = kb_version() if version is None else version
    return f"{RET_PREFIX}:{version}:{query_fingerprint(query, top_k)}"


# ---------- 知识库版本号 ----------
def kb_version():
    raw = backend().get(KB_VERSION_KEY)
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def bump_kb_version():
    """知识库变更后调用：版本 +1，旧版本的检索缓存立即失效。"""
    return int(backend().incr(KB_VERSION_KEY))


# ---------- 会话记忆 ----------
def session_key(user_id):
    return f"{SESS_PREFIX}:{user_id}"


def session_load(user_id, limit=SESSION_MAX):
    """按时间正序返回最近 limit 条消息。"""
    raw = backend().lrange(session_key(user_id), 0, limit - 1)
    messages = []
    for item in raw:
        try:
            messages.append(json.loads(item))
        except (TypeError, ValueError):
            continue
    return messages


def _safe_dump(value):
    """序列化兜底：会话写失败不能让整个请求挂掉，退回字符串存储并记日志。"""
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        log.warning("会话消息无法 JSON 序列化，降级为字符串存储：%s", type(value).__name__)
        return json.dumps({"_raw": str(value)}, ensure_ascii=False)


def session_save(user_id, messages, limit=SESSION_MAX, ttl=SESSION_TTL):
    """整段覆盖写入，只保留最近 limit 条，并刷新 TTL。"""
    kept = list(messages or [])[-limit:]
    key = session_key(user_id)
    client = backend()
    client.delete(key)
    if not kept:
        return 0
    # LPUSH 是头插：倒序压入后 list[0] 才是最新一条，lrange 回来就是时间正序
    client.lpush(key, *[_safe_dump(m) for m in reversed(kept)])
    client.ltrim(key, 0, limit - 1)
    client.expire(key, ttl)
    return len(kept)


def session_clear(user_id):
    return backend().delete(session_key(user_id))


def session_users():
    """当前有会话记忆的 user_id（用 scan_iter，不用会阻塞的 KEYS）。"""
    prefix = f"{SESS_PREFIX}:"
    return sorted(key[len(prefix):] for key in backend().scan_iter(match=f"{prefix}*"))


def flush(prefix=ALL_PREFIX):
    """按前缀清理缓存（比 FLUSHDB 安全，不会误删同一个库里的其它数据）。"""
    keys = list(backend().scan_iter(match=f"{prefix}*"))
    return backend().delete(*keys) if keys else 0
