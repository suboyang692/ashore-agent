"""研岸 D7：规划 Agent —— 读学情画像 + 题库缺口，生成个性化复习计划并落库。

图结构（LangGraph）:
    START -> profile（读学情画像 + 题库资源统计）
          -> plan（LLM 生成 N 天复习计划，结构化输出）
          -> save（写入 review_plans 表）
          -> END

用法:
    python -m app.planner_agent          # 默认 7 天
    python -m app.planner_agent 14       # 14 天
"""
import json
import re
import sys
from typing import TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from app.db import execute, query_all
from app.graph_agent import _model

DEFAULT_DAYS = 7

PLANNER_SYSTEM = (
    "你是考研数学备考规划老师，要根据学生的真实学情制定可执行的复习计划。\n"
    "【排期原则】\n"
    "1. 掌握度低、错得多的知识点优先，安排在靠前的日子；\n"
    "2. 同一知识点不要连续多天重复，二次强化至少间隔 2 天；\n"
    "3. 每天任务量控制在 60-90 分钟：12-15 道客观题，或 3-4 道解答/证明题；\n"
    "4. 每天安排的题目数不得超过该知识点的可用题量，未做过的题优先；\n"
    "5. 每天聚焦 1-2 个知识点，最后一天做综合回顾与错题重做；\n"
    "6. 没有练习记录的知识点属于空白区，也要排入计划。\n"
    "【格式要求】\n"
    "- summary 用 2-3 句话诊断当前学情，点出最薄弱的 1-2 个知识点；\n"
    "- 每天的 tasks 必须写清「做什么 + 做多少」，例如「重做错题 3 道 + 新题 8 道」；\n"
    "- reason 必须引用具体数字（掌握度 / 错误次数 / 可用题量），不得空泛；\n"
    "- reason 只写结论性依据，1-2 句话，禁止出现自我校验、反问、括号内试算或改口（如「等等」「不——」「校验：」）。"
)


_PLAN_JUNK = re.compile(r"(校验[:：]|核查[:：]|重新审视|等等[，,。]|不——|不对[，,]|等一下|我算错)")


def clean_reason(text: str) -> str:
    """清理解释里的自我校验痕迹：从触发词回退到最近的左括号，整段一起去掉。"""
    t = (text or "").strip()
    m = _PLAN_JUNK.search(t)
    if not m:
        return t
    head = t[:m.start()]
    idx = max(head.rfind("（"), head.rfind("("))
    if idx > 0:
        head = head[:idx]
    return head.rstrip(" ，,。;；、（）()")


class DayPlan(BaseModel):
    """一天的计划。"""
    day: int = Field(description="第几天，从 1 开始")
    focus: str = Field(description="当日主题")
    knowledge_points: list[str] = Field(description="当日复习的知识点")
    tasks: str = Field(description="具体任务与题量")
    reason: str = Field(description="安排理由，须引用学情数字")


class ReviewPlan(BaseModel):
    """一份完整的复习计划。"""
    summary: str = Field(description="学情诊断")
    days: list[DayPlan] = Field(description="逐日计划")


class State(TypedDict):
    user_id: str
    days: int
    profile: list
    bank: list
    plan: dict
    plan_id: int


def profile_node(state: State):
    """读学情画像与题库资源，作为规划的事实依据。"""
    user_id = state["user_id"]
    profile = query_all(
        """SELECT knowledge_point, subject, total_count, wrong_count, mastery
           FROM user_mastery WHERE user_id = %s
           ORDER BY mastery ASC, wrong_count DESC""",
        (user_id,),
    )
    bank = query_all(
        """SELECT q.knowledge_point,
                  COUNT(*) AS total,
                  SUM(CASE WHEN a.id IS NULL THEN 1 ELSE 0 END) AS undone
           FROM questions q
           LEFT JOIN answer_records a ON a.question_id = q.id AND a.user_id = %s
           GROUP BY q.knowledge_point
           ORDER BY q.knowledge_point""",
        (user_id,),
    )
    print(f"  [profile] 学情记录 {len(profile)} 条 / 题库覆盖 {len(bank)} 个知识点")
    return {"profile": profile, "bank": bank}


def plan_node(state: State):
    """让模型基于真实数据生成计划（结构化输出）。"""
    if state["profile"]:
        profile_text = "\n".join(
            f"- {r['knowledge_point']}：练 {r['total_count']} 次 / 错 {r['wrong_count']} 次 / 掌握度 {r['mastery']}"
            for r in state["profile"]
        )
    else:
        profile_text = "（该用户暂无练习记录，属于零基础冷启动）"

    bank_text = "\n".join(
        f"- {r['knowledge_point']}：共 {r['total']} 题，其中 {r['undone']} 题未做过"
        for r in state["bank"]
    ) or "（题库为空）"

    prompt = (
        f"学生标识：{state['user_id']}\n\n"
        f"【学情画像】（掌握度越低越薄弱）\n{profile_text}\n\n"
        f"【题库资源】\n{bank_text}\n\n"
        f"请制定 {state['days']} 天复习计划，输出结构化结果。"
    )
    result = _model.with_structured_output(ReviewPlan).invoke(
        [{"role": "system", "content": PLANNER_SYSTEM}, {"role": "user", "content": prompt}]
    )
    plan = result.model_dump()
    for d in plan["days"]:
        d["reason"] = clean_reason(d.get("reason", ""))
    print(f"  [plan] 已生成 {len(plan['days'])} 天计划")
    return {"plan": plan}


def save_node(state: State):
    """计划落库：写入 review_plans。"""
    plan = state["plan"]
    plan_id = execute(
        """INSERT INTO review_plans (user_id, days, summary, content)
           VALUES (%s,%s,%s,%s)""",
        (state["user_id"], state["days"], plan["summary"],
         json.dumps(plan["days"], ensure_ascii=False)),
    )
    print(f"  [save] 计划已入库 review_plans.id={plan_id}")
    return {"plan_id": plan_id}


def build_graph():
    graph = StateGraph(State)
    graph.add_node("profile", profile_node)
    graph.add_node("plan", plan_node)
    graph.add_node("save", save_node)
    graph.set_entry_point("profile")
    graph.add_edge("profile", "plan")
    graph.add_edge("plan", "save")
    graph.add_edge("save", END)
    return graph.compile()


def make_plan(user_id: str = "default", days: int = DEFAULT_DAYS) -> dict:
    """可复用入口：生成复习计划并落库，返回结果 dict。"""
    return build_graph().invoke({"user_id": user_id, "days": days})


def main():
    user_id = input("输入用户标识（回车用 default）: ").strip() or "default"
    days = DEFAULT_DAYS
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        days = int(sys.argv[1])

    print(f"\n生成 {days} 天复习计划中…")
    result = build_graph().invoke({"user_id": user_id, "days": days})
    plan = result["plan"]

    print(f"\n===== 学情诊断（{user_id}）=====")
    print(plan["summary"])
    print(f"\n===== {days} 天复习计划（plan_id={result['plan_id']}）=====")
    for d in plan["days"]:
        print(f"\n第 {d['day']} 天 | {d['focus']}")
        print(f"  知识点: {'、'.join(d['knowledge_points'])}")
        print(f"  任务: {d['tasks']}")
        print(f"  依据: {d['reason']}")


if __name__ == "__main__":
    main()
