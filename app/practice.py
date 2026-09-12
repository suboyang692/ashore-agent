"""研岸 D2：练习闭环 —— 抽题 -> 作答 -> 判分 -> 落库 -> 学情统计。

用法: python -m app.practice
说明: D2 只做客观题判分（选择/填空），主观题批改交给后续的批改 Agent。
"""
import re

from app.db import execute, query_all, query_one


def normalize(text: str) -> str:
    """判分归一化：去空白、转小写，并统一撇号（学生常打数学撇号 ′）。"""
    t = re.sub(r"\s+", "", (text or "").strip().lower())
    return t.replace("’", "'").replace("′", "'").replace("`", "'")


def judge(question: dict, user_answer: str) -> int:
    """返回 1 正确 / 0 错误。选择题取 A-D 首字母比较，填空题去空白比较。"""
    correct = normalize(question["answer"])
    user = normalize(user_answer)
    if question["question_type"] == "选择":
        mc = re.search(r"[a-d]", user)
        user = mc.group(0) if mc else user
        mc2 = re.search(r"[a-d]", correct)
        correct = mc2.group(0) if mc2 else correct
    return 1 if user and user == correct else 0


def pick_question(user_id: str, knowledge_point=None):
    """优先抽该用户没做过的题；都做完了则随机抽一道（允许二刷）。"""
    sql = """SELECT q.* FROM questions q
             LEFT JOIN answer_records a ON a.question_id = q.id AND a.user_id = %s
             WHERE a.id IS NULL"""
    args = [user_id]
    if knowledge_point:
        sql += " AND q.knowledge_point = %s"
        args.append(knowledge_point)
    row = query_one(sql + " ORDER BY RAND() LIMIT 1", args)
    if row:
        return row
    if knowledge_point:
        return query_one("SELECT * FROM questions WHERE knowledge_point=%s ORDER BY RAND() LIMIT 1",
                         (knowledge_point,))
    return query_one("SELECT * FROM questions ORDER BY RAND() LIMIT 1")


def submit(user_id: str, question: dict, user_answer: str) -> dict:
    """判分 -> 写答题记录 -> 更新学情画像，返回本次结果。"""
    correct = judge(question, user_answer)
    execute(
        """INSERT INTO answer_records
           (user_id, question_id, user_answer, is_correct, score, mistake_type)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (user_id, question["id"], user_answer, correct, 100 if correct else 0,
         None if correct else "知识点不熟"),
    )
    _update_mastery(user_id, question["subject"], question["knowledge_point"], correct)
    mastery = query_one(
        "SELECT total_count, wrong_count, mastery FROM user_mastery WHERE user_id=%s AND knowledge_point=%s",
        (user_id, question["knowledge_point"]),
    )
    return {"correct": correct, "mastery": mastery}


def _update_mastery(user_id: str, subject: str, kp: str, correct: int) -> None:
    row = query_one(
        "SELECT total_count, wrong_count FROM user_mastery WHERE user_id=%s AND knowledge_point=%s",
        (user_id, kp),
    )
    if row:
        total = row["total_count"] + 1
        wrong = row["wrong_count"] + (0 if correct else 1)
        execute(
            "UPDATE user_mastery SET total_count=%s, wrong_count=%s, mastery=%s "
            "WHERE user_id=%s AND knowledge_point=%s",
            (total, wrong, round(1 - wrong / total, 2), user_id, kp),
        )
    else:
        wrong = 0 if correct else 1
        execute(
            """INSERT INTO user_mastery (user_id, subject, knowledge_point, total_count, wrong_count, mastery)
               VALUES (%s,%s,%s,1,%s,%s)""",
            (user_id, subject, kp, wrong, round(1 - wrong, 2)),
        )


def show_stats(user_id: str) -> None:
    rows = query_all(
        """SELECT knowledge_point, total_count, wrong_count, mastery
           FROM user_mastery WHERE user_id=%s ORDER BY mastery ASC, total_count DESC""",
        (user_id,),
    )
    print(f"\n===== {user_id} 的学情画像 =====")
    if not rows:
        print("（暂无练习记录）")
        return
    for r in rows:
        print(f"  {r['knowledge_point']:<12} 练 {r['total_count']} 次 / 错 {r['wrong_count']} 次 / 掌握度 {r['mastery']}")


def main():
    user_id = input("输入用户标识（回车用 default）: ").strip() or "default"
    show_stats(user_id)

    q = pick_question(user_id)
    if not q:
        print("题库为空，请先运行：python db/seed_questions.py")
        return
    print(f"\n===== 抽到题目 [{q['knowledge_point']}] =====")
    print(q["stem"])
    answer = input("\n你的答案: ").strip()
    result = submit(user_id, q, answer)
    print("\n判分:", "正确 ✓" if result["correct"] else "错误 ✗")
    print("标准答案:", q["answer"])
    print("解析:", q["analysis"])
    m = result["mastery"]
    print(f"该知识点掌握度: {m['mastery']}（练 {m['total_count']} 次 / 错 {m['wrong_count']} 次）")
    show_stats(user_id)


if __name__ == "__main__":
    main()
