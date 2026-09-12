"""研岸 D8：路由 Agent —— 识别用户意图，分发到答疑 / 出题 / 批改 / 规划子 Agent。

设计要点：
1. 带 question_id 的请求直接走批改（确定性规则，不过模型），避免「提交作答」被误判成提问；
2. 其余消息交模型分类成 qa / quiz / grade / plan / chat 五类；
3. qa 走答疑 Agent（带进程内多轮记忆），quiz 走薄弱点出题，plan 走学情规划，
   grade 且未指定题目时先返回一道待批改的解答题。

用法: python -m app.router_agent
"""
import sys
from typing import Literal

from pydantic import BaseModel, Field

from app.db import query_one
from app.grader_agent import grade_subjective, pick_subjective
from app.graph_agent import _model, answer_question
from app.planner_agent import DEFAULT_DAYS, make_plan
from app.quiz_agent import generate_quiz

ROUTER_SYSTEM = (
    "你是考研备考助手的意图路由器，只做分类，不回答题目本身。\n"
    "【意图类别】\n"
    "- qa：询问知识点、概念、公式或解题方法（例：定积分怎么算、罗尔定理的条件是什么）；\n"
    "- quiz：要求出题、练题、来几道变式题（例：给我出几道极限的题）；\n"
    "- grade：提交解题过程要求批改（例：看我这个做法对不对）；\n"
    "- plan：要求制定复习计划或安排学习进度（例：帮我规划这周怎么复习）；\n"
    "- chat：与学习无关的寒暄或其他（例：你是谁、在吗）。\n"
    "【字段要求】\n"
    "- intent 必须是上述五类之一；\n"
    "- knowledge_point 仅在 qa / quiz 时填写（如「定积分」），抽不到就留空字符串；\n"
    "- days 仅在 plan 时填写计划天数，用户没提就填 0；\n"
    "- reply 仅在 chat 时填写一句友好的中文回复，其余意图留空。"
)

MAX_HISTORY = 10


class RouteDecision(BaseModel):
    """意图分类结果。"""
    intent: Literal["qa", "quiz", "grade", "plan", "chat"] = Field(description="意图类别")
    knowledge_point: str = Field(default="", description="涉及的知识点，无则留空")
    days: int = Field(default=0, description="计划天数，无则 0")
    reply: str = Field(default="", description="仅 chat 意图使用的直接回复")


# 进程内多轮记忆（重启即清空；后续可替换为 Redis）
_HISTORY: dict = {}


def _remember(user_id: str, messages: list) -> None:
    _HISTORY[user_id] = messages[-MAX_HISTORY:]


def classify(message: str) -> RouteDecision:
    """调用模型做意图分类。"""
    return _model.with_structured_output(RouteDecision).invoke(
        [{"role": "system", "content": ROUTER_SYSTEM}, {"role": "user", "content": message}]
    )


def public_question(q: dict) -> dict:
    """对外返回题目时隐去答案与解析，避免直接看答案。"""
    return {
        "id": q["id"],
        "knowledge_point": q["knowledge_point"],
        "question_type": q["question_type"],
        "stem": q["stem"],
        "difficulty": q.get("difficulty"),
    }


def _grade(user_id: str, question_id: int, user_answer: str) -> dict:
    """指定了题目时直接批改（message 视为考生作答）。"""
    q = query_one("SELECT * FROM questions WHERE id=%s", (question_id,))
    if not q:
        return {"intent": "grade", "reply": f"题目 {question_id} 不存在。", "data": {}}
    g = grade_subjective(user_id, q, user_answer)
    return {
        "intent": "grade",
        "reply": f"得分 {g['score']}，错因：{g['mistake_type']}。{g['comment']}",
        "data": {
            "score": g["score"], "mistake_type": g["mistake_type"], "comment": g["comment"],
            "suggestion": g["suggestion"], "standard_answer": q["answer"], "analysis": q["analysis"],
        },
    }


def route(user_id: str = "default", message: str = "", question_id: int | None = None) -> dict:
    """路由入口：返回 {intent, reply, data}。"""
    if question_id is not None:
        return _grade(user_id, question_id, message)

    decision = classify(message)
    print(f"  [router] 意图={decision.intent} 知识点={decision.knowledge_point or '-'}")

    if decision.intent == "qa":
        r = answer_question(message, _HISTORY.get(user_id))
        _remember(user_id, r["messages"])
        return {"intent": "qa", "reply": r["answer"], "data": {}}

    if decision.intent == "quiz":
        r = generate_quiz(user_id, decision.knowledge_point)
        return {
            "intent": "quiz",
            "reply": f"已围绕「{r['knowledge_point']}」命制 {r['saved']} 道变式题并入库，可以开始练习了。",
            "data": {"knowledge_point": r["knowledge_point"], "saved": r["saved"]},
        }

    if decision.intent == "grade":
        q = pick_subjective(user_id)
        if not q:
            return {"intent": "grade", "reply": "题库里暂时没有待批改的解答题。", "data": {}}
        return {
            "intent": "grade",
            "reply": "请作答下面这道题，然后把解题过程发给我批改。",
            "data": {"question": public_question(q)},
        }

    if decision.intent == "plan":
        days = decision.days or DEFAULT_DAYS
        r = make_plan(user_id, days)
        return {
            "intent": "plan",
            "reply": f"已生成 {days} 天复习计划。学情诊断：{r['plan']['summary']}",
            "data": {"plan_id": r["plan_id"], "days": r["plan"]["days"]},
        }

    return {
        "intent": "chat",
        "reply": decision.reply or "我在，随时可以问我考研数学的问题。",
        "data": {},
    }


def main():
    user_id = (sys.argv[1] if len(sys.argv) > 1 else "") or "default"
    print(f"研岸路由 Agent（用户：{user_id}，输入 q 退出）")
    while True:
        message = input("\n你: ").strip()
        if message.lower() in ("q", "quit", "exit"):
            break
        if not message:
            continue
        r = route(user_id, message)
        print(f"研岸[{r['intent']}]:", r["reply"])


if __name__ == "__main__":
    main()
