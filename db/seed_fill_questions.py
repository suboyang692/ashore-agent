"""补充填空题种子数据。

用法:
    python db/seed_fill_questions.py

幂等：已存在 source='seed-fill-v1' 的题则跳过。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import execute, query_one

SOURCE = "seed-fill-v1"

QUESTIONS = [
    ("考研数学", "函数与极限", "等价无穷小", "填空",
     "lim(x→0) (e^x - 1 - x) / x² = ____。", "1/2",
     "e^x = 1 + x + x²/2 + o(x²)，故极限为 1/2。", 3),
    ("考研数学", "一元积分学", "定积分计算", "填空",
     "∫₀^(π/2) sin x dx = ____。", "1",
     "原函数为 -cos x，代入上下限得 -cos(π/2)+cos0 = 1。", 2),
    ("考研数学", "导数与微分", "函数极值", "填空",
     "f(x)=x³-3x 的极小值为 ____。", "-2",
     "f'(x)=3x²-3，极小值点为 x=1，f(1)=1-3=-2。", 3),
    ("考研数学", "导数与微分", "复合函数求导", "填空",
     "d/dx ln(1+x²) 在 x=1 处的值为 ____。", "1",
     "导数为 2x/(1+x²)，代入 x=1 得 1。", 2),
    ("考研数学", "线性代数", "行列式", "填空",
     "行列式 |1 2; 3 4| = ____。", "-2",
     "二阶行列式等于 1×4-2×3=-2。", 2),
    ("考研数学", "一元积分学", "定积分计算", "填空",
     "∫₀¹ 1/(1+x²) dx = ____。", "π/4",
     "原函数为 arctan x，代入上下限得 π/4。", 3),
    ("考研数学", "函数与极限", "重要极限", "填空",
     "lim(x→0) tan x / x = ____。", "1",
     "tan x ~ x，故极限为 1。", 2),
    ("考研数学", "微分中值定理", "罗尔定理", "填空",
     "若 f(x)=x²-2x 在 [0,2] 上满足罗尔定理，则定理中的 ξ = ____。", "1",
     "f(0)=f(2)=0，由 f'(x)=2x-2=0 得 ξ=1。", 3),
]


def main():
    exists = query_one("SELECT id FROM questions WHERE source = %s LIMIT 1", (SOURCE,))
    if exists:
        total = query_one(
            "SELECT COUNT(*) AS c FROM questions WHERE question_type='填空'"
        )["c"]
        print(f"已存在补充填空题（source={SOURCE}），跳过。当前填空题 {total} 道")
        return
    for subject, chapter, kp, qtype, stem, answer, analysis, difficulty in QUESTIONS:
        execute(
            """INSERT INTO questions
               (subject, chapter, knowledge_point, question_type, stem, answer,
                analysis, difficulty, source)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (subject, chapter, kp, qtype, stem, answer, analysis, difficulty, SOURCE),
        )
    total = query_one(
        "SELECT COUNT(*) AS c FROM questions WHERE question_type='填空'"
    )["c"]
    print(f"[ok] 已插入 {len(QUESTIONS)} 道填空题，当前填空题共 {total} 道")


if __name__ == "__main__":
    main()
