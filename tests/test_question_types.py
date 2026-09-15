"""题型枚举收敛（D12）：多一个「题」字不能再靠运气被正确判分。"""
import pytest

from app import question_types as qt
from app.practice import judge


def test_canonical_types_pass_through():
    for t in qt.TYPES:
        assert qt.normalize_question_type(t) == t


def test_extra_character_is_stripped():
    """这是真实踩过的坑：模型写「选择题」，而判分代码比的是 `== "选择"`。"""
    assert qt.normalize_question_type("选择题") == qt.CHOICE
    assert qt.normalize_question_type("填空题") == qt.BLANK
    assert qt.normalize_question_type("解答题") == qt.SOLUTION


def test_solution_synonyms():
    for raw in ("计算题", "证明题", "简答题", "计算", "证明", "简答"):
        assert qt.normalize_question_type(raw) == qt.SOLUTION


def test_choice_synonyms():
    assert qt.normalize_question_type("单选题") == qt.CHOICE
    assert qt.normalize_question_type("单选") == qt.CHOICE


def test_whitespace_is_tolerated():
    assert qt.normalize_question_type(" 选择题 ") == qt.CHOICE
    assert qt.normalize_question_type("选 择 题") == qt.CHOICE
    assert qt.normalize_question_type("选择　题") == qt.CHOICE      # 全角空格


@pytest.mark.parametrize("bad", ["画图题", "choice", "", "   ", None])
def test_unknown_type_is_rejected(bad):
    """入库口宁可拒绝这道题，也不要让判分时认不出的值悄悄进库。"""
    with pytest.raises(ValueError):
        qt.normalize_question_type(bad)


def test_predicates_accept_dict_or_raw_string():
    assert qt.is_choice({"question_type": "选择"}) and qt.is_choice("选择")
    assert qt.is_blank({"question_type": "填空"})
    assert qt.is_subjective({"question_type": "解答"})
    assert qt.is_objective("选择") and qt.is_objective("填空")
    assert not qt.is_objective("解答")


def test_predicates_are_strict_on_legacy_values():
    """刻意不容错：数据问题应该在入库口解决，读取侧容错只会把它藏起来。"""
    assert not qt.is_choice({"question_type": "选择题"})
    assert not qt.is_subjective({"question_type": "解答题"})


def test_judge_refuses_subjective_question():
    """解答题落到客观题判分说明分流错了，必须炸掉而不是拿整段解题过程做文本比对。"""
    with pytest.raises(ValueError, match="解答题"):
        judge({"id": 10, "question_type": "解答", "answer": "1/2"}, "1/2")


def test_judge_still_handles_objective_types():
    assert judge({"question_type": "选择", "answer": "C"}, "c") == 1
    assert judge({"question_type": "填空", "answer": "1/2"}, " 1 / 2 ") == 1


def test_save_node_normalises_type_before_insert(monkeypatch):
    """出题入库时必须把「选择题」收敛成「选择」，否则判分会走错分支。"""
    from app import quiz_agent

    inserted = []
    monkeypatch.setattr(quiz_agent, "execute", lambda sql, args=None: inserted.append(args))

    state = {
        "subject": "考研数学", "chapter": "极限", "knowledge_point": "极限",
        "generated": [
            {"question_type": "选择题", "stem": "题干", "options": "A. 1 | B. 2",
             "answer": "B", "analysis": "解析", "difficulty": 3},
            {"question_type": "画图题", "stem": "题干", "options": "",
             "answer": "y", "analysis": "解析", "difficulty": 3},
        ],
    }
    out = quiz_agent.save_node(state)

    assert out["saved"] == 1                      # 认不出来的那道被拒绝入库
    assert len(inserted) == 1
    assert inserted[0][3] == "选择"                # 入库的是收敛后的题型
