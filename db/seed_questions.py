"""研岸 D2：题库种子数据（考研数学，8 道客观题）。

用法: python db/seed_questions.py
幂等: 已存在 source='seed-v1' 的题则跳过，不重复插入。
说明: questions 表无 options 字段，选择题选项直接拼进 stem 存储。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import execute, query_one

SOURCE = "seed-v1"

QUESTIONS = [
    ("考研数学", "函数与极限", "重要极限", "选择",
     "lim(x→0) sin3x / x = ?", "B", "等价无穷小：sin3x ~ 3x，故极限为 3。", 2,
     "A. 1/3 | B. 3 | C. 1 | D. ∞"),
    ("考研数学", "函数与极限", "重要极限", "选择",
     "lim(x→∞) (1 + 1/x)^x = ?", "B", "第二个重要极限，结果为 e。", 2,
     "A. 1 | B. e | C. 0 | D. ∞"),
    ("考研数学", "函数与极限", "等价无穷小", "选择",
     "lim(x→0) (1 - cos x) / x² = ?", "A", "1 - cos x ~ x²/2，故极限为 1/2。", 3,
     "A. 1/2 | B. 1 | C. 2 | D. 0"),
    ("考研数学", "导数与微分", "复合函数求导", "填空",
     "d/dx (x² · e^x) 在 x = 1 处的值 = ?", "3e", "(x²e^x)' = e^x(x² + 2x)，代入 x=1 得 3e。", 3, ""),
    ("考研数学", "导数与微分", "函数极值", "选择",
     "f(x) = x³ - 3x 的极小值点是?", "B", "f'(x)=3x²-3=0 得 x=±1；f''(1)=6>0，x=1 为极小值点。", 3,
     "A. x = -1 | B. x = 1 | C. x = 0 | D. x = ±1"),
    ("考研数学", "一元积分学", "定积分计算", "选择",
     "∫₀¹ 2x dx = ?", "B", "原函数 x²，代入上下限得 1。", 2,
     "A. 2 | B. 1 | C. 1/2 | D. 0"),
    ("考研数学", "一元积分学", "对称性与奇偶性", "选择",
     "∫₋₁¹ x³ dx = ?", "A", "x³ 是奇函数且区间对称，积分为 0。", 2,
     "A. 0 | B. 1/2 | C. 1 | D. 2"),
    ("考研数学", "微分中值定理", "拉格朗日中值定理", "选择",
     "拉格朗日中值定理的结论是存在 ξ∈(a,b)，使 f(b) - f(a) = ?", "B",
     "拉氏定理：f(b)-f(a)=f'(ξ)(b-a)。", 3,
     "A. f'(ξ) | B. f'(ξ)(b-a) | C. f(ξ)(b-a) | D. f'(ξ)/(b-a)"),
]


def main():
    exists = query_one("SELECT id FROM questions WHERE source = %s LIMIT 1", (SOURCE,))
    if exists:
        total = query_one("SELECT COUNT(*) AS c FROM questions")["c"]
        print(f"已存在种子题（source={SOURCE}），跳过。题库现有 {total} 道")
        return
    for subject, chapter, kp, qtype, stem, answer, analysis, diff, options in QUESTIONS:
        full_stem = stem + ("\n" + options if options else "")
        execute(
            """INSERT INTO questions
               (subject, chapter, knowledge_point, question_type, stem, answer, analysis, difficulty, source)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (subject, chapter, kp, qtype, full_stem, answer, analysis, diff, SOURCE),
        )
    total = query_one("SELECT COUNT(*) AS c FROM questions")["c"]
    print(f"[ok] 已插入 {len(QUESTIONS)} 道种子题，题库共 {total} 道")


if __name__ == "__main__":
    main()
