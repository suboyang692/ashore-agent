"""pytest 公共配置：导入路径兜底 + 用例间状态隔离。"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _isolate_cache():
    """单测一律走进程内后端：不打真实 Redis，也不会被上一个用例的键影响。

    多轮会话记忆（D11 起）也在这里，所以顺带保证了用例之间互不串联。
    """
    from app import cache

    def reset():
        cache.set_backend(cache.memory_backend())
        cache.memory_backend().flushdb()
        cache.reset_stats()

    reset()
    yield
    reset()
