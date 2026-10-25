"""客观题判分边界（纯函数，不依赖数据库与大模型）。"""
from app.practice import judge, normalize


def _q(answer, qtype="选择"):
    return {"answer": answer, "question_type": qtype}


def test_normalize_removes_whitespace_and_case():
    assert normalize(" 1 / 2 ") == "1/2"
    assert normalize("ABC") == "abc"


def test_normalize_unifies_math_apostrophe():
    """学生常打数学撇号 ′（U+2032），必须与普通撇号等价，否则判分误判。"""
    assert normalize("f\u2032(\u03be)=2\u03be") == normalize("f'(\u03be)=2\u03be")


def test_choice_matches_same_letter():
    assert judge(_q("C"), "C") == 1


def test_choice_is_case_insensitive():
    assert judge(_q("C"), "c") == 1


def test_choice_extracts_letter_from_sentence():
    assert judge(_q("B"), "我选 B") == 1


def test_choice_wrong_letter_is_zero():
    assert judge(_q("C"), "B") == 0


def test_fill_answer_ignores_spaces_and_apostrophe_style():
    assert judge(_q("f'(\u03be)=2\u03be", "填空"), "f\u2032(\u03be) = 2\u03be") == 1


def test_fill_answer_fraction_with_spaces():
    assert judge(_q("1/2", "填空"), " 1/2 ") == 1


def test_empty_answer_always_wrong():
    assert judge(_q("1/2", "填空"), "") == 0
    assert judge(_q("A"), "   ") == 0


def test_submit_creates_attempt_and_mistake(monkeypatch):
    from app import practice

    calls = []
    monkeypatch.setattr(practice.practice_repository, "create_attempt", lambda *args: 42)
    monkeypatch.setattr(practice.practice_repository, "finish_attempt", lambda *args: calls.append(("finish", args)))
    monkeypatch.setattr(practice.practice_repository, "add_mistake", lambda *args, **kwargs: calls.append(("mistake", args, kwargs)))
    monkeypatch.setattr(practice, "execute", lambda *args, **kwargs: calls.append(("legacy", args, kwargs)))
    monkeypatch.setattr(practice, "query_one", lambda sql, args=None: {
        "total_count": 0, "wrong_count": 0, "mastery": 0.0,
    })

    question = {
        "id": 7, "subject": "考研数学", "knowledge_point": "极限",
        "question_type": "选择", "answer": "C",
    }
    result = practice.submit("u-1", question, "B")

    assert result["attempt_id"] == 42
    assert any(call[0] == "finish" for call in calls)
    assert any(call[0] == "mistake" for call in calls)
