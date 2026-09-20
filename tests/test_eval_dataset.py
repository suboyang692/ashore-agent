"""评测集自检：标注字段完整、期望值合法，避免改数据集时悄悄写坏。"""
import json
from collections import Counter
from pathlib import Path

from app.grader_agent import MISTAKE_TYPES

DATASET = Path(__file__).resolve().parent.parent / "eval" / "dataset.json"

# 样本来源：合成冷启动 / 真题题干 / 真实用户作答（eval/collect.py 采集）
SOURCES = {"synthetic", "exam", "human"}


def _data():
    return json.loads(DATASET.read_text(encoding="utf-8"))


def test_dataset_contains_both_tasks():
    data = _data()
    assert data["retrieval"]
    assert data["grading"]


def test_retrieval_items_are_complete():
    for item in _data()["retrieval"]:
        assert item["query"].strip()
        assert item["expect_any"], item["query"]


def test_grading_expectations_are_valid():
    for item in _data()["grading"]:
        assert item["stem"].strip()
        assert item["answer"].strip()
        assert item["user_answer"].strip()
        assert item["expect_mistake"] in MISTAKE_TYPES, item["expect_mistake"]
        assert isinstance(item["expect_pass"], bool)


def test_every_item_declares_a_known_source():
    """来源必须显式声明且在允许集合内 —— run_eval 靠它分来源统计。"""
    data = _data()
    for task in ("retrieval", "grading"):
        for item in data[task]:
            assert item.get("source") in SOURCES, (task, item.get("source"), item.get("query") or item["stem"][:30])


def test_grading_set_is_big_enough_to_be_meaningful():
    assert len(_data()["grading"]) >= 10


def test_dataset_is_not_purely_synthetic():
    """至少要有非合成来源，否则指标只说明模型和自己对答案。"""
    data = _data()
    sources = Counter(it["source"] for task in ("retrieval", "grading") for it in data[task])
    assert sources["exam"] or sources["human"], sources
