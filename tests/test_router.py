"""路由 Agent：带 question_id 必须走确定性批改分支，不能过意图分类。"""
import pytest

from app import router_agent


def test_question_id_skips_intent_classification(monkeypatch):
    monkeypatch.setattr(router_agent, "classify",
                        lambda m: pytest.fail("带 question_id 时不应调用意图分类"))
    monkeypatch.setattr(router_agent, "query_one", lambda sql, args=None: {
        "id": 7, "stem": "证明题", "answer": "1/2", "analysis": "解析",
        "knowledge_point": "极限", "question_type": "解答", "subject": "考研数学",
    })
    monkeypatch.setattr(router_agent, "grade_subjective",
                        lambda uid, q, ans: {"score": 80, "mistake_type": "表述不规范",
                                             "comment": "评语", "suggestion": "建议"})
    r = router_agent.route("default", "我的作答", question_id=7)
    assert r["intent"] == "grade"
    assert r["data"]["score"] == 80
    assert r["data"]["standard_answer"] == "1/2"


def test_unknown_question_id_reports_not_found(monkeypatch):
    monkeypatch.setattr(router_agent, "classify",
                        lambda m: pytest.fail("带 question_id 时不应调用意图分类"))
    monkeypatch.setattr(router_agent, "query_one", lambda sql, args=None: None)
    r = router_agent.route("default", "作答", question_id=999)
    assert r["intent"] == "grade"
    assert "不存在" in r["reply"]


def test_quiz_intent_dispatches_to_quiz_agent(monkeypatch):
    monkeypatch.setattr(router_agent, "classify",
                        lambda m: router_agent.RouteDecision(intent="quiz", knowledge_point="极限"))
    monkeypatch.setattr(router_agent, "generate_quiz",
                        lambda uid, kp="": {"knowledge_point": kp or "极限", "saved": 3})
    r = router_agent.route("u", "给我出几道极限的变式题")
    assert r["intent"] == "quiz"
    assert r["data"]["saved"] == 3
    assert "极限" in r["reply"]


def test_plan_intent_falls_back_to_default_days(monkeypatch):
    monkeypatch.setattr(router_agent, "classify",
                        lambda m: router_agent.RouteDecision(intent="plan"))
    captured = {}

    def fake_make_plan(uid, days):
        captured["days"] = days
        return {"plan_id": 1, "plan": {"summary": "诊断", "days": []}}

    monkeypatch.setattr(router_agent, "make_plan", fake_make_plan)
    r = router_agent.route("u", "帮我规划一下复习")
    assert captured["days"] == router_agent.DEFAULT_DAYS
    assert r["intent"] == "plan"


def test_chat_intent_uses_model_reply(monkeypatch):
    monkeypatch.setattr(router_agent, "classify",
                        lambda m: router_agent.RouteDecision(intent="chat", reply="你好呀"))
    r = router_agent.route("u", "在吗")
    assert r["reply"] == "你好呀"


def test_qa_intent_stores_history_for_next_turn(monkeypatch):
    monkeypatch.setattr(router_agent, "classify",
                        lambda m: router_agent.RouteDecision(intent="qa"))
    monkeypatch.setattr(router_agent, "answer_question",
                        lambda q, h=None: {"answer": "答复", "messages": ["m1", "m2"]})
    router_agent._HISTORY.clear()
    r = router_agent.route("u1", "定积分怎么算")
    assert r["intent"] == "qa"
    assert router_agent._HISTORY["u1"] == ["m1", "m2"]


def test_history_is_capped(monkeypatch):
    monkeypatch.setattr(router_agent, "classify",
                        lambda m: router_agent.RouteDecision(intent="qa"))
    long_history = [f"m{i}" for i in range(50)]
    monkeypatch.setattr(router_agent, "answer_question",
                        lambda q, h=None: {"answer": "答复", "messages": long_history})
    router_agent.route("u2", "问题")
    assert len(router_agent._HISTORY["u2"]) == router_agent.MAX_HISTORY
