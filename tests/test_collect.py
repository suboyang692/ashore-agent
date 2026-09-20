"""真实作答采集：结构拼装与去重都是纯函数，脱离交互也能测。"""
import copy

from eval.collect import build_item, is_duplicate, merge

QUESTION = {
    "stem": "求极限 lim(x→0) (e^x - 1 - x) / x²",
    "answer": "1/2",
    "analysis": "泰勒展开",
    "knowledge_point": "泰勒展开",
}


def test_build_item_fills_dataset_schema():
    item = build_item(QUESTION, "  用洛必达得 1/2  ", "无错误", True)
    assert item["stem"] == QUESTION["stem"]
    assert item["answer"] == "1/2"
    assert item["user_answer"] == "用洛必达得 1/2"      # 两侧空白被清掉
    assert item["expect_mistake"] == "无错误"
    assert item["expect_pass"] is True
    assert item["source"] == "human"                    # 采集来的默认是真实作答
    assert item["case"] == "泰勒展开"                    # 没给 case 时退回知识点


def test_build_item_coerces_pass_flag_to_bool():
    assert build_item(QUESTION, "x", "计算错误", 0)["expect_pass"] is False


def test_duplicate_is_judged_by_stem_plus_answer():
    data = {"grading": [build_item(QUESTION, "作答 A", "无错误", True)]}
    assert is_duplicate(data, build_item(QUESTION, "作答 A", "无错误", True))
    # 同一道题的不同错法要各收一条，不能算重复
    assert not is_duplicate(data, build_item(QUESTION, "作答 B", "计算错误", False))


def test_merge_appends_once_and_reports_duplicates():
    data = {"grading": []}
    assert merge(data, build_item(QUESTION, "作答 A", "无错误", True)) is True
    assert merge(data, build_item(QUESTION, "作答 A", "无错误", True)) is False
    assert len(data["grading"]) == 1


def test_merge_does_not_touch_other_keys():
    data = {"retrieval": [{"query": "q", "expect_any": ["a"]}], "grading": []}
    before = copy.deepcopy(data["retrieval"])
    merge(data, build_item(QUESTION, "作答 A", "无错误", True))
    assert data["retrieval"] == before
