"""D11 真 Redis 联调：需要先 docker compose up -d redis。

Redis 没起时这几条会自动 skip，所以直接跑 pytest 也不会挂；
    想只跑它们（先 docker compose up -d redis）：
    pytest -m integration
"""
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def real_client():
    redis = pytest.importorskip("redis", reason="需要先 pip install redis")
    from app.config import REDIS_URL

    client = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=1)
    try:
        client.ping()
    except Exception as exc:
        pytest.skip(f"Redis 没起来（{exc}）：先跑 docker compose up -d redis")
    return client


def test_cache_uses_real_redis(real_client):
    from app import cache

    cache.set_backend(None)          # 让 cache 自己去探测
    assert cache.backend_name() == "redis"

    cache.set_json("ashore:test:integration", {"ok": True}, ttl=30)
    assert cache.get_json("ashore:test:integration") == {"ok": True}
    real_client.delete("ashore:test:integration")


def test_session_is_stored_as_redis_list(real_client):
    from app import cache

    cache.set_backend(None)
    cache.session_save("__it__", [{"role": "human", "content": "hi"}], limit=5, ttl=30)

    assert real_client.type("ashore:sess:__it__") == "list"
    assert cache.session_load("__it__") == [{"role": "human", "content": "hi"}]
    assert real_client.ttl("ashore:sess:__it__") > 0

    real_client.delete("ashore:sess:__it__")


def test_kb_version_roundtrip(real_client):
    from app import cache

    cache.set_backend(None)
    before = cache.kb_version()
    assert cache.bump_kb_version() == before + 1
    real_client.set("ashore:kb:version", before)
