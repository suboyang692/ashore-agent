"""FastAPI 接口：TestClient + 打桩，验证参数校验与错误兜底。"""
import pytest

pytest.importorskip("httpx", reason="FastAPI TestClient 需要 httpx")

from fastapi.testclient import TestClient

from app import api


@pytest.fixture
def client():
    return TestClient(api.app)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_root_lists_endpoints(client):
    body = client.get("/").json()
    assert body["docs"] == "/docs"
    assert "/chat" in body["endpoints"]


def test_ui_page_is_served(client):
    r = client.get("/ui/")
    assert r.status_code == 200
    assert "研岸" in r.text


def test_chat_returns_router_result(client, monkeypatch):
    monkeypatch.setattr(api, "route",
                        lambda uid, msg, qid=None: {"intent": "qa", "reply": "答复", "data": {}})
    r = client.post("/chat", json={"user_id": "u", "message": "定积分怎么算"})
    assert r.status_code == 200
    assert r.json()["intent"] == "qa"


def test_chat_turns_agent_failure_into_500(client, monkeypatch):
    def boom(uid, msg, qid=None):
        raise RuntimeError("LLM 超时")

    monkeypatch.setattr(api, "route", boom)
    r = client.post("/chat", json={"user_id": "u", "message": "x"})
    assert r.status_code == 500
    assert "LLM 超时" in r.json()["detail"]


def test_chat_rejects_empty_body(client):
    assert client.post("/chat", json={}).status_code == 422


def test_profile_reports_weak_points(client, monkeypatch):
    rows = [
        {"knowledge_point": "定积分", "subject": "考研数学",
         "total_count": 2, "wrong_count": 2, "mastery": 0.0},
        {"knowledge_point": "极限", "subject": "考研数学",
         "total_count": 5, "wrong_count": 0, "mastery": 1.0},
    ]
    monkeypatch.setattr(api, "query_all", lambda sql, args=None: rows)
    body = client.get("/profile/u").json()
    assert body["weak_points"] == ["定积分"]


def test_latest_plan_404_when_absent(client, monkeypatch):
    monkeypatch.setattr(api, "query_one", lambda sql, args=None: None)
    assert client.get("/plan/nobody").status_code == 404


def test_latest_plan_parses_schedule_json(client, monkeypatch):
    monkeypatch.setattr(api, "query_one", lambda sql, args=None: {
        "id": 3, "days": 7, "summary": "诊断",
        "content": '[{"day": 1, "focus": "极限"}]',
        "created_at": "2026-09-12T00:00:00",
    })
    body = client.get("/plan/u").json()
    assert body["plan_id"] == 3
    assert body["schedule"] == [{"day": 1, "focus": "极限"}]


def test_submit_404_for_missing_question(client, monkeypatch):
    monkeypatch.setattr(api, "query_one", lambda sql, args=None: None)
    r = client.post("/submit", json={"user_id": "u", "question_id": 1, "answer": "A"})
    assert r.status_code == 404


def test_submit_objective_question_uses_objective_judging(client, monkeypatch):
    monkeypatch.setattr(api, "query_one", lambda sql, args=None: {
        "id": 1, "question_type": "选择", "answer": "C",
        "stem": "题干", "analysis": "解析", "knowledge_point": "极限", "subject": "考研数学",
    })
    monkeypatch.setattr(api, "submit_objective",
                        lambda uid, q, ans: {"correct": 1, "mastery": {"mastery": 1.0}})
    body = client.post("/submit", json={"user_id": "u", "question_id": 1, "answer": "C"}).json()
    assert body["type"] == "objective"
    assert body["correct"] is True


def test_submit_subjective_question_uses_grader(client, monkeypatch):
    monkeypatch.setattr(api, "query_one", lambda sql, args=None: {
        "id": 2, "question_type": "解答", "answer": "1/2",
        "stem": "题干", "analysis": "解析", "knowledge_point": "极限", "subject": "考研数学",
    })
    monkeypatch.setattr(api, "grade_subjective",
                        lambda uid, q, ans: {"score": 55, "mistake_type": "结论跳跃",
                                             "comment": "评语", "suggestion": "建议"})
    body = client.post("/submit", json={"user_id": "u", "question_id": 2, "answer": "我的过程"}).json()
    assert body["type"] == "subjective"
    assert body["mistake_type"] == "结论跳跃"
