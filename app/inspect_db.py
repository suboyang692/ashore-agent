"""研岸：查看 MySQL 里真实存在的数据。

用法: python -m app.inspect_db
"""
from app.db import query_all


def show(title, sql):
    print(f"\n===== {title} =====")
    try:
        rows = query_all(sql)
    except Exception as e:
        print("  查询失败:", e)
        return
    if not rows:
        print("  （暂无数据）")
        return
    for r in rows:
        print("  ", r)


def main():
    show("题库 questions（前 5 条）",
         "SELECT id, knowledge_point, question_type, LEFT(stem, 40) AS stem, answer FROM questions LIMIT 5")
    show("答题记录 answer_records（最近 10 条）",
         "SELECT id, user_id, question_id, user_answer, is_correct, score FROM answer_records ORDER BY id DESC LIMIT 10")
    show("学情画像 user_mastery",
         "SELECT user_id, knowledge_point, total_count, wrong_count, mastery FROM user_mastery ORDER BY mastery ASC")
    show("评测标注 eval_annotations",
         "SELECT * FROM eval_annotations LIMIT 5")
    show("复习计划 review_plans（最近 3 条）",
         "SELECT id, user_id, days, summary, created_at FROM review_plans ORDER BY id DESC LIMIT 3")
    show("各表行数统计",
         """SELECT (SELECT COUNT(*) FROM questions) AS 题目数,
                   (SELECT COUNT(*) FROM answer_records) AS 答题数,
                   (SELECT COUNT(*) FROM user_mastery) AS 学情记录数,
                   (SELECT COUNT(*) FROM eval_annotations) AS 评测标注数,
                   (SELECT COUNT(*) FROM review_plans) AS 复习计划数""")


if __name__ == "__main__":
    main()
