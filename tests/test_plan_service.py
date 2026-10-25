"""复习计划展开：把逐日 JSON 拆成可追踪的计划明细。"""
from app.services import plan_service


def test_expand_one_day_into_one_item_per_knowledge_point():
    days = [{
        "day": 1,
        "focus": "函数极值与复合函数求导",
        "knowledge_points": ["函数极值", "复合函数求导"],
        "tasks": "重做错题 1 道 + 新题 1 道",
    }]
    items = plan_service.expand_items(days)
    assert [i["knowledge_point"] for i in items] == ["函数极值", "复合函数求导"]
    assert all(i["day_no"] == 1 for i in items)
    assert all(i["task_type"] == "重做错题" for i in items)


def test_task_type_is_classified():
    assert plan_service.detect_task_type("重做错题 3 道") == "重做错题"
    assert plan_service.detect_task_type("综合回顾与错题重做") == "重做错题"
    assert plan_service.detect_task_type("综合回顾") == "综合回顾"
    assert plan_service.detect_task_type("新题 8 道") == "新题"


def test_target_count_takes_first_number():
    assert plan_service.parse_target_count("重做错题 3 道 + 新题 8 道") == 3
    assert plan_service.parse_target_count("完成复习") == 1


def test_missing_knowledge_points_falls_back_to_focus():
    items = plan_service.expand_items([{"day": 2, "focus": "泰勒展开", "tasks": "新题 2 道"}])
    assert items[0]["knowledge_point"] == "泰勒展开"


def test_save_plan_writes_main_and_items(monkeypatch):
    calls = {}
    monkeypatch.setattr(plan_service.plan_repository, "create_plan",
                        lambda user_id, days, summary, content: calls.update(
                            main=(user_id, days, summary, content)) or 11)
    monkeypatch.setattr(plan_service.plan_repository, "add_items",
                        lambda plan_id, items: calls.update(items=(plan_id, items)) or len(items))

    plan = {"summary": "诊断", "days": [
        {"day": 1, "focus": "极限", "knowledge_points": ["极限"], "tasks": "新题 2 道"},
    ]}
    result = plan_service.save_plan("u-1", 7, plan)

    assert result == {"plan_id": 11, "item_count": 1}
    assert calls["main"][0] == "u-1"
    assert '"day"' in calls["main"][3]
    assert calls["items"][0] == 11


def test_complete_item_rejects_cross_user(monkeypatch):
    monkeypatch.setattr(plan_service.plan_repository, "get_item_for_user",
                        lambda item_id, user_id: None)
    try:
        plan_service.complete_item("u-1", 3)
    except LookupError as exc:
        assert "无权" in str(exc)
    else:
        raise AssertionError("cross-user plan item must fail")


def test_complete_item_is_idempotent(monkeypatch):
    calls = []
    monkeypatch.setattr(plan_service.plan_repository, "get_item_for_user",
                        lambda item_id, user_id: {"id": item_id, "plan_id": 2, "status": "completed"})
    monkeypatch.setattr(plan_service.plan_repository, "complete_item",
                        lambda *a: calls.append(a))
    item = plan_service.complete_item("u-1", 3)
    assert item["status"] == "completed"
    assert calls == []
