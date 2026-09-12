"""pytest 公共配置：导入路径兜底 + 用例间状态隔离。"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _isolate_router_history():
    """路由 Agent 的进程内多轮记忆不能跨用例串联（未导入则不强行导入）。"""
    module = sys.modules.get("app.router_agent")
    if module is not None:
        module._HISTORY.clear()
    yield
    if module is not None:
        module._HISTORY.clear()
