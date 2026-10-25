"""批改 Agent：用假 LLM 打桩，验证错因兜底与提示词组装（不烧 token）。"""
from app.grader_agent import MISTAKE_TYPES, PASS_SCORE, GradeResult, grade_answer
from tests.stubs import StubModel


def _stub(monkeypatch, **fields):
    fake = StubModel(structured_value=GradeResult(**fields))
    monkeypatch.setattr("app.grader_agent._model", fake)
    return fake


def test_unknown_mistake_type_falls_back_to_known_category(monkeypatch):
    _stub(monkeypatch, score=80, mistake_type="莫名其妙", comment="c", suggestion="s")
    out = grade_answer("题干", "1/2", "", "作答")
    assert out["mistake_type"] in MISTAKE_TYPES
    assert out["mistake_type"] == "知识点不熟"


def test_valid_mistake_type_passes_through(monkeypatch):
    _stub(monkeypatch, score=20, mistake_type="方法误用", comment="c", suggestion="s")
    out = grade_answer("题干", "1/2", "", "作答")
    assert out["mistake_type"] == "方法误用"
    assert out["score"] == 20


def test_prompt_carries_question_answer_and_student_work(monkeypatch):
    fake = _stub(monkeypatch, score=95, mistake_type="无错误", comment="c", suggestion="s")
    grade_answer("求极限 lim(x→0) sinx/x", "1", "解析正文", "我的作答内容")
    user_message = fake.invocations[0][1]["content"]
    assert "求极限 lim(x→0) sinx/x" in user_message
    assert "解析正文" in user_message
    assert "我的作答内容" in user_message


def test_pass_threshold_is_sixty():
    assert PASS_SCORE == 60


def test_mistake_types_cover_rubric():
    assert set(MISTAKE_TYPES) == {
        "计算错误", "方法误用", "审题错误", "结论跳跃", "知识点不熟", "表述不规范", "无错误",
    }

def test_persist_writes_attempt_and_mistake(monkeypatch):
    from app import grader_agent

    calls = []
    monkeypatch.setattr(grader_agent.practice_repository, "create_attempt", lambda *a: 7)
    monkeypatch.setattr(grader_agent.practice_repository, "finish_attempt",
                        lambda *a: calls.append(("finish", a)))
    monkeypatch.setattr(grader_agent.practice_repository, "add_mistake",
                        lambda *a, **k: calls.append(("mistake", a, k)))
    monkeypatch.setattr(grader_agent, "execute", lambda *a, **k: calls.append(("legacy", a, k)))
    monkeypatch.setattr(grader_agent, "_update_mastery", lambda *a: calls.append(("mastery", a)))

    state = {
        "user_id": "u-1",
        "question": {"id": 3, "subject": "考研数学", "knowledge_point": "极限",
                     "answer": "1/2"},
        "user_answer": "我的过程",
        "grade": {"score": 40, "mistake_type": "结论跳跃", "comment": "评语", "suggestion": "建议"},
    }
    out = grader_agent.persist_node(state)

    assert out["grade"]["attempt_id"] == 7
    assert any(c[0] == "finish" for c in calls)
    assert any(c[0] == "mistake" for c in calls)
    assert any(c[0] == "legacy" for c in calls)


def test_persist_skips_mistake_when_no_error(monkeypatch):
    from app import grader_agent

    calls = []
    monkeypatch.setattr(grader_agent.practice_repository, "create_attempt", lambda *a: 8)
    monkeypatch.setattr(grader_agent.practice_repository, "finish_attempt", lambda *a: None)
    monkeypatch.setattr(grader_agent.practice_repository, "add_mistake",
                        lambda *a, **k: calls.append("mistake"))
    monkeypatch.setattr(grader_agent, "execute", lambda *a, **k: None)
    monkeypatch.setattr(grader_agent, "_update_mastery", lambda *a: None)

    state = {
        "user_id": "u-1",
        "question": {"id": 3, "subject": "考研数学", "knowledge_point": "极限", "answer": "1/2"},
        "user_answer": "正确过程",
        "grade": {"score": 95, "mistake_type": "无错误", "comment": "无", "suggestion": "保持"},
    }
    out = grader_agent.persist_node(state)

    assert out["grade"]["attempt_id"] == 8
    assert calls == []
