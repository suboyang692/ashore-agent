"""研岸 D4：批改 Agent —— LLM 批改主观解答题，错因归类并落库。

图结构（LangGraph）:
    START -> grader 节点（结构化批改：得分/对错/错因/评语/建议）
          -> persist 节点（写 answer_records + 更新 user_mastery）
          -> END

用法: python -m app.grader_agent
"""
from typing import TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from app.db import execute, query_one
from app.graph_agent import _model
from app.practice import _update_mastery

GRADER_SYSTEM = (
    "你是一位考研数学阅卷老师，负责批改考生解答题。请严格按以下顺序执行。\n"
    "【最高优先级硬规则】\n"
    "若考生最终答案与标准答案一致，且作答中出现了解题方法名称"
    "（如「泰勒展开」「分部积分」「洛必达」「求导判别」等），则一律判「无错误」，给 90-100 分。\n"
    "不得因过程简略、未写 u/v 选取、未写余项阶数、未验证前提、表述不严谨而改判为其他错因。\n"
    "【示例】\n"
    "- 标准答案 1/2，作答「用泰勒展开，e^x≈1+x+x²/2，代入得 1/2」→ 无错误，95；\n"
    "- 标准答案 1/2，作答「1/2」→ 结论跳跃，50（无任何方法说明）；\n"
    "- 标准答案 1，作答「分部积分得 x·e^x + e^x，代入得 2e」→ 计算错误，20。\n"
    "【判分区间】\n"
    "- 无错误：90-100；\n"
    "- 表述不规范（答案对但漏写 +C、漏写定义域）：70-85；\n"
    "- 结论跳跃（只有结论、无方法无过程）：40-59；\n"
    "- 计算错误（方法公式对、运算错）：10-50；\n"
    "- 知识点不熟（公式或概念本身写错）：0-30；\n"
    "- 方法误用（方法本身不适用，如求极限用积分法）：0-20；\n"
    "- 审题错误（看错题目条件）：0-30。\n"
    "【判错因步骤，按顺序自问】\n"
    "1. 方法本身适用吗？不适用 → 方法误用；\n"
    "2. 看错题目条件了吗？→ 审题错误；\n"
    "3. 方法适用，但公式或概念本身写错吗？→ 知识点不熟；\n"
    "4. 方法、公式都对，只是运算出错吗？→ 计算错误；\n"
    "5. 只有结论、没有过程吗？→ 结论跳跃；\n"
    "6. 答案对但书写不规范吗？→ 表述不规范；\n"
    "7. 都不符合 → 无错误。\n"
    "【一致性要求】mistake_type 字段必须与 comment 中给出的错因完全一致，不得自相矛盾。\n"
    "【输出要求】\n"
    "- comment 按「错误原文—出错原因—正确写法」组织，无错误则写「无」；\n"
    "- suggestion 给出下一步针对性练习建议。"
)

MISTAKE_TYPES = [
    "计算错误", "方法误用", "审题错误", "结论跳跃", "知识点不熟", "表述不规范", "无错误",
]
PASS_SCORE = 60


class GradeResult(BaseModel):
    """批改结果的结构化输出。"""
    score: int = Field(description="得分，0-100 的整数")
    mistake_type: str = Field(description="错因类别，必须是给定枚举之一")
    comment: str = Field(description="按「错误原文—出错原因—正确写法」组织的评语")
    suggestion: str = Field(description="下一步练习建议")


class State(TypedDict):
    user_id: str
    question: dict
    user_answer: str
    grade: dict


def grade_answer(stem: str, answer: str, analysis: str, user_answer: str) -> dict:
    """可复用的批改函数（评测脚本也用它）。返回结构化批改结果 dict。"""
    prompt = (
        f"【题目】{stem}\n"
        f"【标准答案】{answer}\n"
        f"【评分解析】{analysis or '（无）'}\n"
        f"【考生作答】{user_answer}\n\n"
        "请批改并输出结构化结果。"
    )
    result = _model.with_structured_output(GradeResult).invoke(
        [{"role": "system", "content": GRADER_SYSTEM}, {"role": "user", "content": prompt}]
    )
    if result.mistake_type not in MISTAKE_TYPES:
        result.mistake_type = "知识点不熟"
    return result.model_dump()


def grader_node(state: State):
    """批改节点：结构化输出得分、错因、评语、建议。"""
    q = state["question"]
    return {"grade": grade_answer(q["stem"], q["answer"], q.get("analysis"), state["user_answer"])}


def persist_node(state: State):
    """落库节点：写答题记录并更新学情画像。"""
    q, g = state["question"], state["grade"]
    correct = 1 if g["score"] >= PASS_SCORE else 0
    execute(
        """INSERT INTO answer_records
           (user_id, question_id, user_answer, is_correct, score, mistake_type, mistake_detail)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (state["user_id"], q["id"], state["user_answer"], correct, g["score"],
         g["mistake_type"], g["comment"]),
    )
    _update_mastery(state["user_id"], q["subject"], q["knowledge_point"], correct)
    return {}


def build_graph():
    graph = StateGraph(State)
    graph.add_node("grader", grader_node)
    graph.add_node("persist", persist_node)
    graph.set_entry_point("grader")
    graph.add_edge("grader", "persist")
    graph.add_edge("persist", END)
    return graph.compile()


def pick_subjective(user_id: str):
    return query_one(
        """SELECT q.* FROM questions q
           LEFT JOIN answer_records a ON a.question_id = q.id AND a.user_id = %s
           WHERE q.question_type = '解答' AND a.id IS NULL
           ORDER BY RAND() LIMIT 1""",
        (user_id,),
    )


def main():
    graph = build_graph()
    user_id = input("输入用户标识（回车用 default）: ").strip() or "default"
    q = pick_subjective(user_id)
    if not q:
        print("没有可批改的解答题，请先运行：python db/seed_subjective.py")
        return
    print(f"\n===== 解答题 [{q['knowledge_point']}] =====")
    print(q["stem"])
    print("\n（请写下你的完整解题过程，输入空行结束）")
    lines = []
    while True:
        line = input()
        if not line.strip():
            break
        lines.append(line)
    user_answer = "\n".join(lines).strip()
    if not user_answer:
        print("未输入作答，退出。")
        return

    print("\n批改中…")
    result = graph.invoke({"user_id": user_id, "question": q, "user_answer": user_answer})
    g = result["grade"]
    print("\n===== 批改结果 =====")
    print(f"得分: {g['score']}")
    print(f"错因: {g['mistake_type']}")
    print(f"评语: {g['comment']}")
    print(f"建议: {g['suggestion']}")
    print(f"\n标准答案: {q['answer']}")
    print(f"解析: {q['analysis']}")


if __name__ == "__main__":
    main()
