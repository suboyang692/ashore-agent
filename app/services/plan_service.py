"""复习计划服务：计划正文与可追踪明细一起落库。

review_plans.content 继续保留整份 JSON，兼容旧接口和已有数据；
review_plan_items 让前端可以按天渲染、逐项标记完成。
"""
import json
import re

from app.repositories import plan_repository

_COUNT_RE = re.compile(r"(\d+)\s*道")


def parse_target_count(tasks: str) -> int:
    """从「重做错题 3 道 + 新题 8 道」里取第一个题量，取不到按 1 道算。"""
    m = _COUNT_RE.search(tasks or "")
    return int(m.group(1)) if m else 1


def detect_task_type(tasks: str) -> str:
    """把任务描述归成三类，便于前端分组和统计。"""
    text = tasks or ""
    if "错题" in text:
        return "重做错题"
    if "综合" in text or "回顾" in text:
        return "综合回顾"
    return "新题"


def expand_items(days: list) -> list:
    """把逐日计划展开成计划明细行。

    一天可能覆盖多个知识点，每个知识点单独一行，才能分别追踪完成状态。
    """
    items = []
    for day in days or []:
        task_text = day.get("tasks", "")
        task_type = detect_task_type(task_text)
        target = parse_target_count(task_text)
        points = day.get("knowledge_points") or [day.get("focus", "")]
        for kp in points:
            kp = (kp or "").strip()
            if not kp:
                continue
            items.append({
                "day_no": int(day.get("day", 0)),
                "knowledge_point": kp,
                "task_type": task_type,
                "target_count": target,
            })
    return items


def save_plan(user_id: str, days: int, plan: dict) -> dict:
    """写入计划主表并展开明细，返回 plan_id 与明细条数。"""
    content = json.dumps(plan["days"], ensure_ascii=False)
    plan_id = plan_repository.create_plan(user_id, days, plan["summary"], content)
    items = expand_items(plan["days"])
    written = plan_repository.add_items(plan_id, items)
    return {"plan_id": plan_id, "item_count": written}


def complete_item(user_id: str, item_id: int) -> dict:
    """勾选完成一个计划项；重复勾选保持幂等。"""
    item = plan_repository.get_item_for_user(item_id, user_id)
    if not item:
        raise LookupError("计划项不存在或无权访问")
    if item["status"] != "completed":
        plan_repository.complete_item(item_id, item["plan_id"])
        item = dict(item, status="completed")
    return item
