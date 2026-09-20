"""研岸 D8：路由 Agent —— 识别用户意图，分发到答疑 / 出题 / 批改 / 规划子 Agent。

设计要点：
1. 带 question_id 的请求直接走批改（确定性规则，不过模型），避免「提交作答」被误判成提问；
2. 其余消息交模型分类成 qa / quiz / grade / plan / chat 五类；
3. qa 走答疑 Agent（多轮记忆存 Redis 并带 TTL，Redis 不可用时自动落回进程内），
   grade 且未指定题目时先返回一道待批改的解答题。

用法: python -m app.router_agent
"""
import sys
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app import cache
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

MAX_HISTORY = 10          # 原文保留的条数
MAX_SUMMARY_CHARS = 800   # 滚动摘要的字数上限

SUMMARY_SYSTEM = (
    "你在维护一段考研答疑对话的滚动摘要。把「已有摘要」和「新增对话」合并成一段新摘要，"
    "只保留对后续答疑有用的信息：学生问过的知识点、暴露出的薄弱点、已经讲清楚的结论、"
    "学生说明过的偏好（比如目标院校、复习进度）。不要复述题目细节，不要写评价和客套话，"
    "直接输出摘要正文，不超过 300 字。"
)


class RouteDecision(BaseModel):
    """意图分类结果。"""
    intent: Literal["qa", "quiz", "grade", "plan", "chat"] = Field(description="意图类别")
    knowledge_point: str = Field(default="", description="涉及的知识点，无则留空")
    days: int = Field(default=0, description="计划天数，无则 0")
    reply: str = Field(default="", description="仅 chat 意图使用的直接回复")


def _pick_turns(messages: list) -> list:
    """从完整消息流里挑出要持久化的「对话轮次」。

    只留 Human / 最终回答两种，工具调用产生的中间消息（带 tool_calls 的 AI 消息
    和 Tool 消息）一律丢弃，原因有二：
    1. 它们带着整段检索原文，体积是对话本身的十倍量级，存 Redis 很浪费；
    2. 这类消息必须成对出现（tool_calls 与 tool_call_id 要配对），一旦按条数
       截断就会出现半截配对，下一轮请求会被模型接口直接拒绝。
    """
    turns = []
    for m in messages:
        kind = getattr(m, "type", "")
        if kind not in ("human", "ai"):
            continue
        if kind == "ai" and getattr(m, "tool_calls", None):
            continue                      # 中间态，不带进下一轮
        content = getattr(m, "content", "")
        if isinstance(content, str) and content:
            turns.append({"role": kind, "content": content})
    return turns


def summarize(previous: str, dropped: list, model=None) -> str:
    """把被挤出窗口的对话压进滚动摘要。

    直接丢弃窗口外的对话，「几轮前提过的薄弱点」就永远消失了；全量留着又会把每轮
    请求的上下文越撑越大。折中：用模型把旧对话压成几百字的摘要，和最近 N 条原文
    一起喂给 Agent。压缩失败时保留旧摘要 —— 退化成原来「只留最近 N 条」的行为，
    但绝不因为一次调用失败就把已有记忆清空。

    model 参数是给测试注入桩用的，生产路径走模块级 _model。
    """
    lines = []
    if previous:
        lines.append("【已有摘要】" + previous)
    for m in dropped:
        who = "学生" if m.get("role") == "human" else "助手"
        lines.append(f"{who}：{(m.get('content') or '')[:400]}")
    try:
        reply = (model or _model).invoke([
            {"role": "system", "content": SUMMARY_SYSTEM},
            {"role": "user", "content": "\n".join(lines)},
        ])
    except Exception as exc:                      # 摘要只是增强，失败不能拖垮这轮对话
        print(f"  [warn] 会话摘要压缩失败，沿用上一版：{type(exc).__name__}: {exc}")
        return previous
    text = getattr(reply, "content", reply)
    if not isinstance(text, str):
        return previous
    text = text.strip()
    return text[:MAX_SUMMARY_CHARS] if text else previous


def _summary_message(user_id: str):
    """把滚动摘要包成一条 system 消息；还没有摘要时返回 None。"""
    text = cache.session_summary_load(user_id)
    return SystemMessage(content="【此前对话摘要】" + text) if text else None


def _history(user_id: str) -> list:
    """读取该用户的多轮记忆并还原成 LangChain 消息（Redis 优先，降级时读进程内）。"""
    restored = []
    summary = _summary_message(user_id)
    if summary is not None:
        restored.append(summary)
    for item in cache.session_load(user_id, limit=MAX_HISTORY):
        if not isinstance(item, dict):
            continue
        role, content = item.get("role"), item.get("content")
        if not isinstance(content, str):
            continue
        if role == "human":
            restored.append(HumanMessage(content=content))
        elif role == "ai":
            restored.append(AIMessage(content=content))
    return restored


def _remember(user_id: str, messages: list) -> None:
    """整段覆盖写入。外置存储后，uvicorn 多 worker 之间也能共享同一份上下文。

    超出窗口的那几条不直接丢，先压进滚动摘要，下一轮还会以 system 消息的形式回来。
    """
    picked = _pick_turns(messages)
    dropped = picked[:-MAX_HISTORY] if len(picked) > MAX_HISTORY else []
    if dropped:
        cache.session_summary_save(user_id, summarize(cache.session_summary_load(user_id), dropped))
    cache.session_save(user_id, picked, limit=MAX_HISTORY)


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
        r = answer_question(message, _history(user_id))
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
