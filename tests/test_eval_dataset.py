"""评测集自检：标注字段完整、期望值合法，避免改数据集时悄悄写坏。"""
import json
from pathlib import Path

from app.grader_agent import MISTAKE_TYPES

DATASET = Path(__file__).resolve().parent.parent / "eval" / "dataset.json"


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


def test_grading_set_is_big_enough_to_be_meaningful():
    assert len(_data()["grading"]) >= 10
