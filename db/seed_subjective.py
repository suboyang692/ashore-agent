"""研岸 D4：主观解答题种子数据（供批改 Agent 使用）。

用法: python db/seed_subjective.py
来源标记: seed-subj-v1（幂等，重复运行跳过）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import execute, query_one

SOURCE = "seed-subj-v1"

QUESTIONS = [
    ("考研数学", "一元积分学", "分部积分", "解答",
     "计算定积分 ∫₀¹ x·e^x dx",
     "1",
     "用分部积分：∫x·e^x dx = x·e^x - ∫e^x dx = x·e^x - e^x。代入上下限：(1·e - e) - (0 - 1) = 0 + 1 = 1。",
     3),
    ("考研数学", "函数与极限", "泰勒展开", "解答",
     "求极限 lim(x→0) (e^x - 1 - x) / x²",
     "1/2",
     "e^x 在 x=0 处泰勒展开：e^x = 1 + x + x²/2 + o(x²)，代入分子得 x²/2 + o(x²)，除以 x² 后极限为 1/2。",
     4),
    ("考研数学", "导数与微分", "函数极值", "解答",
     "求函数 f(x) = x³ - 3x² + 2 的极值",
     "极大值 f(0)=2，极小值 f(2)=-2",
     "f'(x)=3x²-6x=3x(x-2)，驻点 x=0,2。f''(x)=6x-6：f''(0)=-6<0 为极大值 f(0)=2；f''(2)=6>0 为极小值 f(2)=-2。",
     3),
    ("考研数学", "一元积分学", "不定积分", "解答",
     "计算不定积分 ∫ x·ln x dx",
     "x²/2 · ln x - x²/4 + C",
     "分部积分：令 u=ln x, dv=x dx，则 du=dx/x, v=x²/2；原式 = x²/2·ln x - ∫ x/2 dx = x²/2·ln x - x²/4 + C。",
     3),
]


def main():
    if query_one("SELECT id FROM questions WHERE source = %s LIMIT 1", (SOURCE,)):
        total = query_one("SELECT COUNT(*) AS c FROM questions WHERE question_type='解答'")["c"]
        print(f"已存在主观题种子（source={SOURCE}），跳过。当前解答题 {total} 道")
        return
    for subject, chapter, kp, qtype, stem, answer, analysis, diff in QUESTIONS:
        execute(
            """INSERT INTO questions
               (subject, chapter, knowledge_point, question_type, stem, answer, analysis, difficulty, source)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (subject, chapter, kp, qtype, stem, answer, analysis, diff, SOURCE),
        )
    total = query_one("SELECT COUNT(*) AS c FROM questions WHERE question_type='解答'")["c"]
    print(f"[ok] 已插入 {len(QUESTIONS)} 道主观解答题，当前解答题共 {total} 道")


if __name__ == "__main__":
    main()
