"""研岸 D5：评测脚本 —— 检索 Top-5 召回率 + 批改错因/通过判定准确率。

用法: python eval/run_eval.py
输出: 终端指标 + 每条样本写入 eval_annotations 表（badcase 可追溯）
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import execute
from app.grader_agent import PASS_SCORE, grade_answer
from app.retriever import hybrid_search

DATASET = Path(__file__).resolve().parent / "dataset.json"


def _save(task_type, input_text, expected, actual, is_pass, reason=None):
    execute(
        """INSERT INTO eval_annotations
           (task_type, input_text, expected_output, actual_output, is_pass, badcase_reason)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (task_type, input_text, expected, actual, is_pass, reason),
    )


def eval_retrieval(items):
    hits = 0
    print("===== 检索评测（Top-5 是否召回期望内容）=====")
    for it in items:
        results = hybrid_search(it["query"], top_k=5)
        text = " ".join(r["text"] for r in results)
        hit = any(kw in text for kw in it["expect_any"])
        hits += hit
        print(f"  [{'命中' if hit else '未命中'}] {it['query']}")
        if not hit:
            print(f"        top5 预览: {text[:120].replace(chr(10), ' ')}…")
        _save("检索", it["query"], "|".join(it["expect_any"]), text[:2000],
              1 if hit else 0, None if hit else "Top-5 未召回期望关键词")
    return hits, len(items)


def eval_grading(items):
    mistake_ok = pass_ok = 0
    print("\n===== 批改评测（错因 + 通过判定）=====")
    for it in items:
        g = grade_answer(it["stem"], it["answer"], "", it["user_answer"])
        passed = g["score"] >= PASS_SCORE
        m_ok = g["mistake_type"] == it["expect_mistake"]
        p_ok = passed == it["expect_pass"]
        mistake_ok += m_ok
        pass_ok += p_ok
        flag = "对" if (m_ok and p_ok) else "错"
        print(f"  [{flag}] 期望错因 {it['expect_mistake']} / 实际 {g['mistake_type']} | 得分 {g['score']}")
        if not (m_ok and p_ok):
            print(f"        作答: {it['user_answer'][:60]}…")
            print(f"        评语: {g['comment'][:100]}…")
        _save("批改", it["user_answer"][:500],
              f"{it['expect_mistake']}|pass={it['expect_pass']}",
              f"{g['mistake_type']}|score={g['score']}|pass={passed}",
              1 if (m_ok and p_ok) else 0,
              None if (m_ok and p_ok) else f"期望 {it['expect_mistake']}，实际 {g['mistake_type']}")
    return mistake_ok, pass_ok, len(items)


def main():
    data = json.loads(DATASET.read_text(encoding="utf-8"))

    rh, rt = eval_retrieval(data["retrieval"])
    print(f"\n检索 Top-5 召回率: {rh}/{rt} = {rh / rt:.1%}")

    mh, ph, gt = eval_grading(data["grading"])
    print(f"\n错因判定准确率: {mh}/{gt} = {mh / gt:.1%}")
    print(f"通过/不通过判定准确率: {ph}/{gt} = {ph / gt:.1%}")

    print("\n每条样本已写入 eval_annotations 表（可用 python -m app.inspect_db 查看 badcase）")


if __name__ == "__main__":
    main()
