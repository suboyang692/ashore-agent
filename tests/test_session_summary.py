"""会话记忆压缩：挤出窗口的对话要变成滚动摘要，不能直接丢。

原行为是「只留最近 N 条」，窗口外的一律丢弃；这里验证新行为：
窗口外的对话被压成一段摘要，下一轮以 system 消息回到上下文里。
"""
from app import cache
from app.router_agent import (
    MAX_HISTORY,
    MAX_SUMMARY_CHARS,
    _history,
    _remember,
    _summary_message,
    summarize,
)
from tests.stubs import FakeMessage, StubModel


class BoomModel:
    """压缩时模型炸掉的替身。"""

    def invoke(self, messages, **kwargs):
        raise RuntimeError("模型挂了")


def turns(n):
    """造 n 条 human/ai 交替的对话消息。"""
    out = []
    for i in range(n):
        out.append(FakeMessage("human", f"第{i}个问题"))
        out.append(FakeMessage("ai", f"第{i}个回答"))
    return out


def test_no_summary_when_nothing_compressed():
    assert cache.session_summary_load("u") == ""
    assert _summary_message("u") is None
    assert _history("u") == []


def test_summarize_feeds_previous_summary_and_dropped_turns_to_model(monkeypatch):
    fake = StubModel(text="学生在复习定积分，薄弱点在分部积分")
    monkeypatch.setattr("app.router_agent._model", fake)
    out = summarize("此前问过极限", [{"role": "human", "content": "定积分怎么算"}])
    assert out == "学生在复习定积分，薄弱点在分部积分"
    prompt = fake.invocations[0][-1]["content"]
    assert "此前问过极限" in prompt          # 旧摘要带进去了
    assert "定积分怎么算" in prompt           # 新丢出来的对话也带进去了


def test_summarize_keeps_old_summary_when_model_fails():
    """摘要失败只能退化，不能把已有记忆清空。"""
    out = summarize("旧摘要不能丢", [{"role": "human", "content": "x"}], model=BoomModel())
    assert out == "旧摘要不能丢"


def test_summarize_returns_previous_when_model_returns_blank():
    assert summarize("旧摘要", [{"role": "ai", "content": "x"}], model=StubModel(text="   ")) == "旧摘要"


def test_summarize_truncates_overlong_output():
    out = summarize("", [{"role": "human", "content": "x"}], model=StubModel(text="噫" * 5000))
    assert len(out) == MAX_SUMMARY_CHARS


def test_summarize_accepts_plain_string_reply(monkeypatch):
    """真模型返回 AIMessage（有 .content），桩返回 str —— 两种都要吃得下。"""
    monkeypatch.setattr("app.router_agent._model", StubModel(text="字符串回复"))
    assert summarize("", [{"role": "human", "content": "x"}]) == "字符串回复"


def test_remember_compresses_overflow_and_keeps_recent(monkeypatch):
    monkeypatch.setattr("app.router_agent._model", StubModel(text="学生问过极限与定积分"))
    _remember("u", turns(MAX_HISTORY))          # 一共 20 条，超出 10 条
    kept = cache.session_load("u", limit=MAX_HISTORY)
    assert len(kept) == MAX_HISTORY
    assert kept[-1]["content"] == f"第{MAX_HISTORY - 1}个回答"     # 最近的在
    assert cache.session_summary_load("u") == "学生问过极限与定积分"
    assert kept[0]["content"] != "第0个问题"                      # 最早的那批已被挤出


def test_remember_without_overflow_does_not_touch_summary(monkeypatch):
    monkeypatch.setattr("app.router_agent._model", StubModel(text="不该被调用"))
    _remember("u", turns(3))
    assert cache.session_summary_load("u") == ""
    assert len(cache.session_load("u", limit=MAX_HISTORY)) == 6


def test_remember_survives_summarize_failure(monkeypatch):
    """压缩炸了，这轮对话照样要存下来。"""
    monkeypatch.setattr("app.router_agent._model", BoomModel())
    _remember("u", turns(MAX_HISTORY))
    assert len(cache.session_load("u", limit=MAX_HISTORY)) == MAX_HISTORY


def test_history_prepends_summary_as_system_message():
    cache.session_summary_save("u", "学生目标是数二，薄弱点在级数")
    _remember("u", turns(1))
    history = _history("u")
    assert history[0].type == "system"
    assert "学生目标是数二" in history[0].content
    assert [m.type for m in history[1:]] == ["human", "ai"]


def test_summary_message_is_not_written_back_into_session(monkeypatch):
    """摘要以 system 消息进入上下文，但不能被当成对话轮次再存回去，否则会越滚越大。"""
    monkeypatch.setattr("app.router_agent._model", StubModel(text="摘要"))
    cache.session_summary_save("u", "旧摘要")
    history = _history("u")
    history.append(FakeMessage("human", "新问题"))
    history.append(FakeMessage("ai", "新回答"))
    _remember("u", history)
    stored = cache.session_load("u", limit=MAX_HISTORY)
    assert all(m["role"] in ("human", "ai") for m in stored)
    assert "旧摘要" not in "".join(m["content"] for m in stored)


def test_session_clear_also_drops_summary():
    cache.session_summary_save("u", "摘要")
    cache.session_clear("u")
    assert cache.session_summary_load("u") == ""
