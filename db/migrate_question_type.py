"""研岸 D12：题型枚举收敛 —— 清洗历史数据并把列收紧成 ENUM。

背景：早期模型出题会写「选择题 / 填空题」，而种子数据用「选择 / 填空 / 解答」。
判分分流是按字符串精确匹配的（practice.judge 里 `== "选择"` 才走选项字母比对，
api 的 /submit 里 `== "解答"` 才转批改 Agent），多一个「题」字就会静默走错
分支 —— 不报错，只是判错，或者那道题永远抽不出来。

这个脚本做三件事：体检 -> 清洗 -> 收紧列类型。可重复执行。

用法:
    python db/migrate_question_type.py           # 只体检，不改动
    python db/migrate_question_type.py --apply    # 清洗 + 把列改成 ENUM
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import execute, query_all
from app.question_types import TYPES, normalize_question_type

ENUM_LIST = ",".join(f"'{t}'" for t in TYPES)
COLUMN_DDL = (
    f"ALTER TABLE questions MODIFY question_type ENUM({ENUM_LIST}) NOT NULL "
    "COMMENT '题型，三选一；判分分流依赖它（见 app/question_types.py）'"
)


def scan():
    """返回 (每种题型的行数, 需要清洗的清单, 认不出来的清单)。"""
    rows = query_all(
        "SELECT question_type, COUNT(*) AS n FROM questions "
        "GROUP BY question_type ORDER BY n DESC"
    )
    plan, unknown = [], []
    for r in rows:
        raw, n = r["question_type"], r["n"]
        try:
            canonical = normalize_question_type(raw)
        except ValueError:
            unknown.append((raw, n))
            continue
        if canonical != raw:
            plan.append((raw, canonical, n))
    return rows, plan, unknown


def show_rows(rows):
    for r in rows:
        raw, n = r["question_type"], r["n"]
        try:
            canonical = normalize_question_type(raw)
            note = "" if canonical == raw else f"  <- 需要清洗为 {canonical!r}"
        except ValueError:
            note = "  <- 无法识别，需人工确认"
        print(f"  {raw!r:<12} {n:>4} 行{note}")


def column_type():
    return query_all("SHOW COLUMNS FROM questions LIKE 'question_type'")[0]["Type"]


def main():
    apply_changes = "--apply" in sys.argv

    rows, plan, unknown = scan()
    print("===== 题型体检 =====")
    if not rows:
        print("  （题库为空）")
        return 0
    show_rows(rows)

    if unknown:
        print(f"\n[!] 有 {len(unknown)} 种题型无法自动识别。ENUM 会把它们静默截成空串，")
        print("    所以先人工确认，再决定是加别名还是改数据。本次不做任何改动。")
        return 1

    if plan:
        total = sum(n for _, _, n in plan)
        print(f"\n共 {total} 行需要清洗。")
        if not apply_changes:
            print("确认无误后加 --apply 执行。")
            return 0
        print("\n===== 清洗 =====")
        for raw, canonical, _ in plan:
            changed = execute(
                "UPDATE questions SET question_type=%s WHERE question_type=%s",
                (canonical, raw),
            )
            print(f"  [fix] {raw!r} -> {canonical!r}（{changed} 行）")
    else:
        print("\n题型已经是标准写法，无需清洗。")
        if not apply_changes:
            return 0

    print("\n===== 收紧列类型 =====")
    execute(COLUMN_DDL)
    print(f"  question_type 现在的类型：{column_type()}")

    print("\n===== 复核 =====")
    show_rows(query_all(
        "SELECT question_type, COUNT(*) AS n FROM questions "
        "GROUP BY question_type ORDER BY n DESC"
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
