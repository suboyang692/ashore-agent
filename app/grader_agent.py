"""研岸 D4：批改 Agent —— LLM 批改主观解答题，错因归类并落库。

图结构（LangGraph）:
    START -> grader 节点（结构化批改：得分/对错/错因/评语/建议）
          -> persist 节点（写 answer_records + 更新 user_mastery）
          -> END

用法: python -m app.grader_agent
"""
from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from app.db import execute, query_one
from app.practice import _update_mastery
from app.graph_agent import _model

GRADER_SYSTEM = (
    "你是一位考研数学阅卷老师，负责批改考生解答题。\n"
    "评分要求：\n"
    "1. 严格对照标准答案，按步骤给分（0-100）；\n"
    "2. 错因必须从以下选项中选择一个：计算错误 / 结论跳跃 / 知识点不熟 / 表述不规范 / 无错误；\n"
    "3. comment 按「错误原文—出错原因—正确写法」组织，无错误则写「无」；\n"
    "4. suggestion 给出下一步针对性练习建议。"
)

MISTAKE_TYPES = ["计算错误", "结论跳跃", "知识点不熟", "表述不规范", "无错误"]
PASS_SCORE = 60


class GradeResult(BaseModel):
    """批改结果的结构化输出。"""
    score: int = Field(description="得分，0-100 的整数")
    mistake_type: str = Field(description="错因，必须是：计算错误/结论跳跃/知识点不熟/表述不规范/无错误")
    comment: str = Field(description="按「错误原文—出错原因—正确写法」组织的评语")
    suggestion: str = Field(description="下一步练习建议")


class State(TypedDict):
    user_id: str
    question: dict
    user_answer: str
    grade: dict


def grader_node(state: State):
    """批改节点：结构化输出得分、错因、评语、建议。"""
    q = state["question"]
    prompt = (
        f"【题目】{q['stem']}\n"
        f"【标准答案】{q['answer']}\n"
        f"【评分解析】{q.get('analysis') or '（无）'}\n"
        f"【考生作答】{state['user_answer']}\n\n"
        "请批改并输出结构化结果。"
    )
    result = _model.with_structured_output(GradeResult).invoke(
        [{"role": "system", "content": GRADER_SYSTEM}, {"role": "user", "content": prompt}]
    )
    if result.mistake_type not in MISTAKE_TYPES:
        result.mistake_type = "知识点不熟"
    return {"grade": result.model_dump()}


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
