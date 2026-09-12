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
