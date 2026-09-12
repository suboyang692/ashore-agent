"""测试用的假对象：让单元测试不依赖真实大模型 / 网络。"""


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
