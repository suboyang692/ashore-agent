"""复习计划与计划明细持久化操作。"""
from app.db import execute, query_all, query_one


def create_plan(user_id: str, days: int, summary: str, content_json: str) -> int:
    return execute(
        """INSERT INTO review_plans (user_id, days, summary, content)
           VALUES (%s,%s,%s,%s)""",
        (user_id, days, summary, content_json),
    )


def add_items(plan_id: int, items: list) -> int:
    """批量写入计划明细，返回写入条数。"""
    count = 0
    for item in items:
        execute(
            """INSERT INTO review_plan_items
               (plan_id, day_no, knowledge_point, task_type,
                target_count, due_at)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (
                plan_id, item["day_no"], item["knowledge_point"],
                item["task_type"], item["target_count"], item.get("due_at"),
            ),
        )
        count += 1
    return count


def list_items(plan_id: int):
    return query_all(
        """SELECT * FROM review_plan_items
           WHERE plan_id = %s ORDER BY day_no ASC, id ASC""",
        (plan_id,),
    )


def complete_item(item_id: int, plan_id: int) -> int:
    return execute(
        """UPDATE review_plan_items
           SET status = 'completed', completed_at = NOW(),
               completed_count = target_count
           WHERE id = %s AND plan_id = %s""",
        (item_id, plan_id),
    )


def latest_plan(user_id: str):
    return query_one(
        "SELECT * FROM review_plans WHERE user_id = %s ORDER BY id DESC LIMIT 1",
        (user_id,),
    )


def get_item_for_user(item_id: int, user_id: str):
    """只返回属于该用户的计划项，避免越权勾选别人的计划。"""
    return query_one(
        """SELECT i.* FROM review_plan_items i
           JOIN review_plans p ON p.id = i.plan_id
           WHERE i.id = %s AND p.user_id = %s""",
        (item_id, user_id),
    )
