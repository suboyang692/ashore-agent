"""流式答疑：token 顺序、来源收口、路由记忆与 SSE 接口。"""
import asyncio

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk

from app import api, graph_agent, qa_agent, router_agent
from app.security import create_token
from tests.stubs import FakeMessage


def _collect(agen):
    async def run():
        return [event async for event in agen]

    return asyncio.run(run())


class FakeStreamingModel:
    def __init__(self, rounds):
        self.rounds = list(rounds)
        self.calls = 0

    async def astream(self, messages):
        self.calls += 1
        for chunk in self.rounds.pop(0):
            yield chunk


class FakeSearch:
    def __init__(self):
        self.queries = []

    def invoke(self, args):
        self.queries.append(args["query"])
        return "[片段1 | 出处: 讲义.md · 第9页 | 命中方式: vector]\n定积分是一个数。"


def test_stream_answer_question_yields_tokens_then_complete(monkeypatch):
    model = FakeStreamingModel([[
        AIMessageChunk(content="答"),
        AIMessageChunk(content="案"),
    ]])
    monkeypatch.setattr(graph_agent, "_model_with_tools", model)

    events = _collect(graph_agent.stream_answer_question("定积分怎么算"))

    assert [event["text"] for event in events if event["type"] == "token"] == ["答", "案"]
    complete = events[-1]
    assert complete["type"] == "complete"
    assert complete["answer"] == "答案"
    assert model.calls == 1


def test_stream_answer_question_runs_tool_loop_and_keeps_sources(monkeypatch):
    tool_round = [AIMessageChunk(
        content="",
        tool_call_chunks=[{
            "name": "search_knowledge",
            "args": '{"query": "定积分"}',
            "id": "call_1",
            "index": 0,
        }],
    )]
    answer_round = [
        AIMessageChunk(content="定积分"),
        AIMessageChunk(content="是一个数。\n来源：讲义.md · 第9页"),
    ]
    monkeypatch.setattr(graph_agent, "_model_with_tools", FakeStreamingModel([tool_round, answer_round]))
    search = FakeSearch()
    monkeypatch.setattr(graph_agent, "search_knowledge", search)

    events = _collect(graph_agent.stream_answer_question("定积分怎么算"))

    assert search.queries == ["定积分"]
    assert "定积分是一个数。" in events[-1]["answer"]
    assert events[-1]["sources"][0]["cited"] is True
    assert any(getattr(message, "type", "") == "tool" for message in events[-1]["messages"])


def test_stream_answer_question_falls_back_after_tool_rounds(monkeypatch):
    tool_round = [AIMessageChunk(
        content="",
        tool_call_chunks=[{
            "name": "search_knowledge",
            "args": '{"query": "定积分"}',
            "id": "call_loop",
            "index": 0,
        }],
    )]
    monkeypatch.setattr(graph_agent, "_model_with_tools", FakeStreamingModel([tool_round] * 4))
    monkeypatch.setattr(graph_agent, "_model", FakeStreamingModel([
        [AIMessageChunk(content="兜底"), AIMessageChunk(content="回答")],
    ]))
    monkeypatch.setattr(graph_agent, "search_knowledge", FakeSearch())

    events = _collect(graph_agent.stream_answer_question("定积分怎么算"))

    assert [event["text"] for event in events if event["type"] == "token"] == ["兜底", "回答"]
    assert events[-1]["answer"] == "兜底回答"


def test_stream_route_emits_meta_tokens_done_and_remembers_history(monkeypatch):
    monkeypatch.setattr(router_agent, "classify", lambda message: router_agent.RouteDecision(
        intent="qa", knowledge_point="定积分",
    ))

    async def fake_stream(question, history=None):
        yield {"type": "token", "text": "答"}
        yield {
            "type": "complete",
            "answer": "答\n来源：讲义.md · 第9页",
            "messages": [
                FakeMessage("human", question),
                FakeMessage("ai", "答\n来源：讲义.md · 第9页"),
            ],
            "sources": [{"cite": "讲义.md · 第9页", "cited": True}],
        }

    monkeypatch.setattr(router_agent, "stream_answer_question", fake_stream)

    events = _collect(router_agent.stream_route("stream-user", "定积分怎么算"))

    assert [event["type"] for event in events] == ["meta", "token", "done"]
    assert events[2]["result"]["data"]["next_action"]["knowledge_point"] == "定积分"
    assert router_agent.cache.session_load("stream-user")[1]["content"].startswith("答")


def test_chat_stream_endpoint_returns_sse(monkeypatch):
    async def fake_stream(user_id, message, question_id=None):
        yield {"type": "token", "text": "答"}
        yield {"type": "done", "result": {"intent": "qa", "reply": "答", "data": {}}}

    monkeypatch.setattr(api, "stream_route", fake_stream)
    monkeypatch.setattr(
        api.user_repository, "get_by_id",
        lambda uid: {"id": uid, "username": uid, "email": None,
                     "role": "student", "status": "active"},
    )
    client = TestClient(
        api.app,
        headers={"Authorization": f"Bearer {create_token('u')}"},
    )

    response = client.post("/chat/stream", json={"user_id": "u", "message": "问题"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"type": "token"' in response.text
    assert response.text.rstrip().endswith("data: [DONE]")


def test_chat_stream_hides_provider_error(monkeypatch):
    async def failing_stream(user_id, message, question_id=None):
        raise RuntimeError("Arrearage: account not in good standing")
        yield  # pragma: no cover

    monkeypatch.setattr(api, "stream_route", failing_stream)
    monkeypatch.setattr(
        api.user_repository, "get_by_id",
        lambda uid: {"id": uid, "username": uid, "email": None,
                     "role": "student", "status": "active"},
    )
    client = TestClient(
        api.app,
        headers={"Authorization": f"Bearer {create_token('u')}"},
    )

    response = client.post("/chat/stream", json={"user_id": "u", "message": "问题"})

    assert "百炼账户" in response.text
    assert "Arrearage" not in response.text


def test_prompts_require_conditions_and_bounded_length():
    for prompt in (graph_agent.SYSTEM_PROMPT, qa_agent.SYSTEM_PROMPT):
        assert "适用条件" in prompt
        assert "800 字" in prompt
        assert "逐一代入" in prompt
