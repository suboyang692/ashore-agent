from app.cache import MemoryBackend


"""测试用的假对象：让单元测试不依赖真实大模型 / 网络 / Redis。"""


class StubRunnable:
    """假的 Runnable：invoke 直接返回预设值，并可选地记录入参。"""

    def __init__(self, value, recorder=None):
        self._value = value
        self._recorder = recorder

    def invoke(self, messages, **kwargs):
        if self._recorder is not None:
            self._recorder(messages)
        return self._value


class StubModel:
    """假 LLM：with_structured_output 返回预设结构，invoke 返回预设文本。

    用法:
        fake = StubModel(structured_value=GradeResult(score=80, ...))
        monkeypatch.setattr("app.grader_agent._model", fake)
    """

    def __init__(self, structured_value=None, text=""):
        self.structured_value = structured_value
        self.text = text
        self.structured_schemas = []
        self.invocations = []          # 记录每次调用传入的 messages，便于断言提示词

    def with_structured_output(self, schema):
        self.structured_schemas.append(schema)
        return StubRunnable(self.structured_value, self.invocations.append)

    def invoke(self, messages, **kwargs):
        self.invocations.append(messages)
        return self.text


class FakeRedis(MemoryBackend):
    """假装自己是 redis-py 客户端。

    直接复用 MemoryBackend 的命令实现（两者语义本来就对齐），只把 name 改成 redis，
    用来验证「真实客户端接上了」这条分支：后端判定、键名布局、TTL 都走正常路径。
    真连服务器的联调在 tests/test_cache_integration.py（pytest -m integration）。
    """

    name = "redis"


class FakeMessage:
    """LangChain 消息的最小替身：路由 Agent 只用到 type / content / tool_calls。"""

    def __init__(self, type, content, tool_calls=None):
        self.type = type
        self.content = content
        self.tool_calls = tool_calls or []
