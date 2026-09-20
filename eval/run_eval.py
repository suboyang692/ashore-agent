"""评测脚本 —— 检索 Top-5 召回率 + 批改错因/通过判定准确率。

评测集按来源分别统计 ——
    synthetic 模型合成冷启动语料 / exam 真题题干（app.exam_ocr.py 转录入库）/
    human 真实用户作答（用 eval/collect.py 采集后并入）
不分开统计的话，「合成语料上 94%」和「真实作答上 94%」在报告里长得一模一样，
但后者才说明系统在真实分布上的表现。

用法: python eval/run_eval.py
输出: 终端指标（总体 + 分来源）+ 每条样本写入 eval_annotations 表（badcase 可追溯）
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


def _report(title, rows):
    """rows: [(source, ok)] -> 总体 + 分来源的准确率。"""
    total = len(rows)
    hit = sum(1 for _, ok in rows if ok)
    print(f"\n{title}: {hit}/{total} = {hit / total:.1%}")
    by_source = {}
    for source, ok in rows:
        bucket = by_source.setdefault(source, [0, 0])
        bucket[1] += 1
        bucket[0] += 1 if ok else 0
    if len(by_source) > 1:
        for source in sorted(by_source):
            ok_n, all_n = by_source[source]
            print(f"    - {source:<10} {ok_n}/{all_n} = {ok_n / all_n:.1%}")


def eval_retrieval(items):
    rows = []
    print("===== 检索评测（Top-5 是否召回期望内容）=====")
    for it in items:
        results = hybrid_search(it["query"], top_k=5)
        text = " ".join(r["text"] for r in results)
        okay = any(kw in text for kw in it["expect_any"])
        rows.append((it.get("source", "synthetic"), okay))
        print(f"  [{'命中' if okay else '未命中'}] ({it.get('source', '-')}) {it['query']}")
        if not okay:
            print(f"        top5 预览: {text[:120].replace(chr(10), ' ')}…")
        _save("检索", it["query"], "|".join(it["expect_any"]), text[:2000],
              1 if okay else 0, None if okay else "Top-5 未召回期望关键词")
    return rows


def eval_grading(items):
    mistake_rows, pass_rows = [], []
    print("\n===== 批改评测（错因 + 通过判定）=====")
    for it in items:
        source = it.get("source", "synthetic")
        g = grade_answer(it["stem"], it["answer"], "", it["user_answer"])
        passed = g["score"] >= PASS_SCORE
        m_ok = g["mistake_type"] == it["expect_mistake"]
        p_ok = passed == it["expect_pass"]
        mistake_rows.append((source, m_ok))
        pass_rows.append((source, p_ok))
        flag = "对" if (m_ok and p_ok) else "错"
        print(f"  [{flag}] ({source}) 期望错因 {it['expect_mistake']} / 实际 {g['mistake_type']} | 得分 {g['score']}")
        if not (m_ok and p_ok):
            print(f"        作答: {it['user_answer'][:60]}…")
            print(f"        评语: {g['comment'][:100]}…")
        _save("批改", it["user_answer"][:500],
              f"{it['expect_mistake']}|pass={it['expect_pass']}",
              f"{g['mistake_type']}|score={g['score']}|pass={passed}",
              1 if (m_ok and p_ok) else 0,
              None if (m_ok and p_ok) else f"期望 {it['expect_mistake']}，实际 {g['mistake_type']}")
    return mistake_rows, pass_rows


def main():
    data = json.loads(DATASET.read_text(encoding="utf-8"))

    _report("检索 Top-5 召回率", eval_retrieval(data["retrieval"]))

    mistake_rows, pass_rows = eval_grading(data["grading"])
    _report("错因判定准确率", mistake_rows)
    _report("通过/不通过判定准确率", pass_rows)

    print("\n每条样本已写入 eval_annotations 表（可用 python -m app.inspect_db 查看 badcase）")


if __name__ == "__main__":
    main()
