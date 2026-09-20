"""研岸 D13：采集真实用户作答，补进评测集。

评测集原先 100% 是模型合成的，指标再高也只说明「模型和自己对答案」。这个脚本
把真人作答收进来：从题库抽题 -> 你写解题过程 -> 批改 Agent 先给一版预判 ->
你确认或改掉 -> 写入 eval/dataset.json（source=human）并落库。

半自动标注是有意的：全人工标注你坚持不了几十条，全自动标注等于没有人工。
让模型先判、人只做「同意 / 改成 X」，标注成本能压到每条十几秒。

用法:
    python eval/collect.py                   # 随机抽一道还没采过的题
    python eval/collect.py --kp 定积分计算    # 指定知识点
    python eval/collect.py --exam             # 只抽 2023 年数学二真题
    python eval/collect.py --list             # 看已采集多少条
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import execute, query_all, query_one
from app.grader_agent import MISTAKE_TYPES, PASS_SCORE, grade_answer

DATASET = Path(__file__).resolve().parent / "dataset.json"
EXAM_SOURCE = "2023年数学二真题"


# ---------- 纯函数（tests/test_collect.py 覆盖） ----------

def build_item(question: dict, user_answer: str, mistake: str, passed: bool,
               case: str = "", rubric: str = "", source: str = "human") -> dict:
    """按 dataset.json 的 grading 条目结构拼一条样本。"""
    return {
        "stem": question["stem"],
        "answer": question["answer"],
        "case": case or question.get("knowledge_point", ""),
        "user_answer": user_answer.strip(),
        "expect_mistake": mistake,
        "expect_pass": bool(passed),
        "rubric": rubric,
        "source": source,
    }


def is_duplicate(data: dict, item: dict) -> bool:
    """同题干 + 同作答才算重复：同一道题的不同错法都要收进来。"""
    for old in data.get("grading", []):
        if old["stem"] == item["stem"] and old["user_answer"] == item["user_answer"]:
            return True
    return False


def merge(data: dict, item: dict) -> bool:
    """把样本并进评测集；重复返回 False。"""
    if is_duplicate(data, item):
        return False
    data.setdefault("grading", []).append(item)
    return True


def load_dataset() -> dict:
    return json.loads(DATASET.read_text(encoding="utf-8"))


def save_dataset(data: dict) -> None:
    DATASET.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------- 交互流程 ----------

def pick(exam_only: bool, kp: str = "", user_id: str = "default"):
    """抽一道还没采集过的题。优先解答题：客观题文本比对就够了，批改 Agent 是给主观题用的。"""
    sql = "SELECT * FROM questions WHERE 1=1"
    args = []
    if exam_only:
        sql += " AND source = %s"
        args.append(EXAM_SOURCE)
    if kp:
        sql += " AND knowledge_point = %s"
        args.append(kp)
    sql += " ORDER BY (question_type = '解答') DESC, RAND()"
    for row in query_all(sql, args):
        done = query_one("SELECT id FROM answer_records WHERE user_id=%s AND question_id=%s",
                         (user_id, row["id"]))
        if not done:
            return row
    return None


def read_answer() -> str:
    print("\n写下你的解题过程（单独一行 END 结束；直接回车跳过这题）：")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "END":
            break
        if not lines and not line.strip():
            return ""
        lines.append(line)
    return "\n".join(lines).strip()


def confirm(prejudge: dict) -> tuple:
    """让用户确认或修改模型的预判。返回 (错因, 是否通过)。"""
    print(f"\n批改 Agent 预判：错因 = {prejudge['mistake_type']}，得分 = {prejudge['score']}")
    answer = input("同意吗？直接回车=同意，或输入新的错因（" + "/".join(MISTAKE_TYPES) + "）：").strip()
    mistake = answer if answer in MISTAKE_TYPES else prejudge["mistake_type"]
    if answer and answer not in MISTAKE_TYPES:
        print(f"  「{answer}」不是合法错因，保留预判值 {mistake}")
    passed = prejudge["score"] >= PASS_SCORE
    toggle = input(f"通过判定保留「{'通过' if passed else '不通过'}」吗？(y=保留 / n=翻转)：").strip().lower()
    if toggle == "n":
        passed = not passed
    return mistake, passed


def main():
    ap = argparse.ArgumentParser(description="采集真实作答，补进评测集")
    ap.add_argument("--kp", default="", help="指定知识点")
    ap.add_argument("--exam", action="store_true", help="只抽 2023 年数学二真题")
    ap.add_argument("--user", default="default")
    ap.add_argument("--list", action="store_true", help="只看统计")
    args = ap.parse_args()

    data = load_dataset()
    if args.list:
        from collections import Counter
        c = Counter(it.get("source", "synthetic") for it in data["grading"])
        print(f"批改样本 {len(data['grading'])} 条：" + "、".join(f"{k}={v}" for k, v in sorted(c.items())))
        print(f"其中真实作答（human）{c.get('human', 0)} 条 —— 目标是 30 条以上")
        return

    question = pick(args.exam, args.kp, args.user)
    if not question:
        print("题库里没有未采集过的题了（换 --kp、加题，或换 --user）")
        return

    print(f"\n===== [{question['knowledge_point']} | {question['question_type']} | "
          f"{question.get('source')}] =====")
    print(question["stem"])

    user_answer = read_answer()
    if not user_answer:
        print("已跳过")
        return

    prejudge = grade_answer(question["stem"], question["answer"], question.get("analysis") or "",
                            user_answer)
    print(f"\n【标准答案】{question['answer']}")
    print(f"【解析】{(question.get('analysis') or '')[:200]}")
    mistake, passed = confirm(prejudge)

    case = input("一句话描述这道作答的问题（可回车跳过）：").strip()
    item = build_item(question, user_answer, mistake, passed, case=case or "真实作答")
    if not merge(data, item):
        print("\n这条（同题干 + 同作答）已经在评测集里了，未重复添加")
        return
    save_dataset(data)

    execute(
        """INSERT INTO answer_records
           (user_id, question_id, user_answer, is_correct, score, mistake_type, mistake_detail)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (args.user, question["id"], user_answer, 1 if passed else 0,
         prejudge["score"], mistake, prejudge.get("comment", "")[:2000]),
    )

    from collections import Counter
    c = Counter(it.get("source", "synthetic") for it in data["grading"])
    print(f"\n[ok] 已写入 eval/dataset.json：批改样本 {len(data['grading'])} 条"
          f"（human {c.get('human', 0)} 条）")
    print("改完记得跑一遍评测：python eval/run_eval.py")


if __name__ == "__main__":
    main()
