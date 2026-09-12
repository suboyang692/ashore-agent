"""研岸 D6：出题 Agent —— 针对薄弱知识点命制变式题并入库。

图结构（LangGraph）:
    START -> analyze（定位薄弱知识点 + 取参考题）
          -> generate（LLM 命制变式题，结构化输出）
          -> save（写入 questions 表）
          -> END

用法:
    python -m app.quiz_agent            # 自动选最薄弱知识点
    python -m app.quiz_agent 定积分      # 指定知识点
"""
import re
import sys
from typing import TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from app.db import execute, query_all, query_one

# 复用答疑/批改 Agent 同一个模型实例
from app.graph_agent import _model

QUIZ_COUNT = 3
SOURCE_TAG = "generated-v1"


_ANSWER_JUNK = re.compile(r"^(math|latex|text)\s*[:：]\s*", re.IGNORECASE)


def clean_answer(text: str) -> str:
    """清洗模型输出的答案：去 math: 前缀、LaTeX 符号、多余空白。"""
    t = (text or "").strip()
    t = _ANSWER_JUNK.sub("", t)
    t = re.sub(r"\\text\{([^}]*)\}", r"\1", t)
    t = t.replace("$", "").replace("\\(", "").replace("\\)", "").replace("\\[", "").replace("\\]", "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


_SELF_TALK = ["此前分析有误", "之前的分析有误", "重新审视", "我刚才", "更正："]
_SELF_TALK_HEAD = re.compile(r"^(此前分析有误|之前的分析有误|重新审视|我刚才|更正)[，,。：:、\s]*")


def clean_analysis(text: str) -> str:
    """清洗解析：丢掉写错的尝试，并从正确推导处开始，不留自我纠错痕迹。"""
    t = (text or "").strip()
    for bad in _SELF_TALK:
        idx = t.find(bad)
        if idx > 0:
            t = t[idx:]
            break
    return _SELF_TALK_HEAD.sub("", t).strip()

_OPTION_RE = re.compile(r"^\s*([A-Da-d])\s*[.、．:：)）]\s*(.+)$")
_BLANK_EQ = re.compile(r"([A-Za-zα-ωΑ-Ω][^=，。；,;:\n]*)=\s*[_＿]{3,}")


def _norm(text: str) -> str:
    """比对用归一化：去空白、统一撇号。"""
    t = (text or "").replace(" ", "").replace("　", "")
    return t.replace("’", "'").replace("′", "'").replace("`", "'")


def coerce_choice_answer(answer: str, options: str) -> str:
    """选择题答案统一为选项字母：模型给的是选项内容时反查字母。"""
    a = _norm(clean_answer(answer))
    if re.fullmatch(r"[A-Da-d]", a):
        return a.upper()
    items = []
    for part in re.split(r"[|｜]", options or ""):
        m = _OPTION_RE.match(part.strip())
        if m:
            items.append((m.group(1).upper(), _norm(m.group(2))))
    for letter, text in items:
        if text and text == a:
            return letter
    for letter, text in items:
        if text and a and min(len(text), len(a)) >= 2 and (text in a or a in text):
            return letter
    return a


def strip_blank_prefix(answer: str, stem: str) -> str:
    """填空题答案若重复了题干等号左边，只保留空处的值。"""
    if "=" not in (answer or ""):
        return answer
    m = _BLANK_EQ.search(_norm(stem))
    if not m:
        return answer
    head, _, tail = answer.partition("=")
    if _norm(head) == _norm(m.group(1)):
        return tail.strip()
    return answer


def final_answer(q: dict) -> str:
    """展示与入库共用的答案规范化入口。"""
    a = clean_answer(q.get("answer", ""))
    if "选择" in (q.get("question_type") or ""):
        return coerce_choice_answer(a, q.get("options", ""))
    return strip_blank_prefix(a, q.get("stem", ""))


QUIZ_SYSTEM = (
    "你是一位考研数学命题老师，擅长针对同一知识点命制变式题。\n"
    "【命题要求】\n"
    "1. 不得与原题重复，必须变换数字、条件、问法或考查角度（可正向变逆向、单项变综合）；\n"
    "2. 难度控制在 2-4；\n"
    "3. 每题必须给出标准答案与解析；\n"
    "4. 选择题的选项写成「A. xx | B. xx | C. xx | D. xx」放入 options 字段，非选择题 options 留空；\n"
    "5. 题目必须可解、条件完整、无歧义；\n"
    "6. 生成前先在心里完整解一遍，确认答案正确再输出。\n"
    "【格式硬要求】\n"
    "- answer 只写最终答案的纯文本：选择题写选项字母（如 B）；填空题写数值或表达式（如 1/2、3e、x=1）；\n"
    "- 选择题的 answer 必须且只能是单个大写字母 A/B/C/D，禁止写选项内容；\n"
    "- 填空题的 answer 只填空处的值，不要重复题干中已给出的等号左边；\n"
    "- answer 禁止出现 LaTeX 命令、禁止 $ 符号、禁止 math: 之类前缀；\n"
    "- analysis 直接给出正确的推导过程，禁止展示试错、犹豫、自我纠正或\"此前的分析有误\"这类内容；\n"
    "- analysis 中的每一步推导必须与最终答案一致，不得自相矛盾。\n"
    "【题型判定】\n"
    "- 题干给出 A/B/C/D 选项 -> question_type 写「选择」；\n"
    "- 题干含填空横线且无选项 -> 写「填空」，且题干不要出现「证明：」这类作答指令，直接把待填内容写成横线；\n"
    "- 其余 -> 写「解答」。"
)


class GeneratedQuestion(BaseModel):
    """一道命制出的变式题。"""
    question_type: str = Field(description="题型：选择/填空/解答")
    stem: str = Field(description="题干")
    options: str = Field(default="", description="选择题选项，非选择题留空")
    answer: str = Field(description="标准答案")
    analysis: str = Field(description="详细解析")
    difficulty: int = Field(default=3, description="难度 1-5")


class QuizSet(BaseModel):
    """一次命制的题目集合。"""
    questions: list[GeneratedQuestion] = Field(description=f"共 {QUIZ_COUNT} 道变式题")


class State(TypedDict):
    user_id: str
    knowledge_point: str
    subject: str
    chapter: str
    reference: list
    generated: list
    saved: int


def analyze_node(state: State):
    """定位目标知识点：优先用参数，其次取学情画像中最薄弱的，最后随机。"""
    kp = state.get("knowledge_point")
    user_id = state.get("user_id", "default")

    if not kp:
        row = query_one(
            """SELECT knowledge_point FROM user_mastery
               WHERE user_id = %s ORDER BY mastery ASC, wrong_count DESC LIMIT 1""",
            (user_id,),
        )
        if row:
            kp = row["knowledge_point"]
            print(f"  [analyze] 依据学情画像选中薄弱知识点: {kp}")
        else:
            rnd = query_one("SELECT knowledge_point FROM questions ORDER BY RAND() LIMIT 1")
            kp = rnd["knowledge_point"] if rnd else "定积分"
            print(f"  [analyze] 无学情记录，随机选中知识点: {kp}")

    meta = query_one("SELECT subject, chapter FROM questions WHERE knowledge_point = %s LIMIT 1", (kp,))
    refs = query_all(
        "SELECT question_type, stem, answer, analysis FROM questions WHERE knowledge_point = %s LIMIT 2",
        (kp,),
    )
    print(f"  [analyze] 参考已有题目 {len(refs)} 道")
    return {
        "knowledge_point": kp,
        "subject": meta["subject"] if meta else "考研数学",
        "chapter": meta["chapter"] if meta else "未分类",
        "reference": refs,
    }


def generate_node(state: State):
    """命制变式题（结构化输出）。"""
    refs_text = "\n".join(
        f"- [{r['question_type']}] {r['stem']}\n  答案: {r['answer']}" for r in state["reference"]
    ) or "（该知识点暂无参考题）"
    prompt = (
        f"知识点：{state['knowledge_point']}（属于 {state['chapter']}）\n\n"
        f"已有题目：\n{refs_text}\n\n"
        f"请命制 {QUIZ_COUNT} 道变式题，输出结构化结果。"
    )
    result = _model.with_structured_output(QuizSet).invoke(
        [{"role": "system", "content": QUIZ_SYSTEM}, {"role": "user", "content": prompt}]
    )
    questions = [q.model_dump() for q in result.questions]
    print(f"  [generate] 已命制 {len(questions)} 道变式题")
    return {"generated": questions}


def save_node(state: State):
    """入库：写入 questions 表（source=generated-v1）。"""
    saved = 0
    for q in state["generated"]:
        answer = final_answer(q)
        analysis = clean_analysis(q["analysis"])
        if "选择" in (q["question_type"] or "") and not re.fullmatch(r"[A-D]", answer):
            print(f"  [save][skip] 选择题答案无法映射成选项字母，跳过：{answer!r}")
            continue
        # 入库前校验：答案不能为空、不能残留 LaTeX 命令
        if not answer or "\\" in answer or "{" in answer:
            print(f"  [save][skip] 答案格式不合规，跳过：{q['answer']!r}")
            continue
        stem = q["stem"] + ("\n" + q["options"] if q.get("options") else "")
        execute(
            """INSERT INTO questions
               (subject, chapter, knowledge_point, question_type, stem, answer, analysis, difficulty, source)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (state["subject"], state["chapter"], state["knowledge_point"], q["question_type"],
             stem, answer, analysis, q["difficulty"], SOURCE_TAG),
        )
        saved += 1
    print(f"  [save] 已入库 {saved} 道（source={SOURCE_TAG}）")
    return {"saved": saved}


def build_graph():
    graph = StateGraph(State)
    graph.add_node("analyze", analyze_node)
    graph.add_node("generate", generate_node)
    graph.add_node("save", save_node)
    graph.set_entry_point("analyze")
    graph.add_edge("analyze", "generate")
    graph.add_edge("generate", "save")
    graph.add_edge("save", END)
    return graph.compile()


def generate_quiz(user_id: str = "default", knowledge_point: str = "") -> dict:
    """可复用入口：命制变式题并入题库，返回结果 dict。"""
    return build_graph().invoke({"user_id": user_id, "knowledge_point": knowledge_point})


def main():
    graph = build_graph()
    user_id = input("输入用户标识（回车用 default）: ").strip() or "default"
    kp = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else ""
    if kp:
        print(f"指定知识点: {kp}")

    print("\n出题中…")
    result = graph.invoke({"user_id": user_id, "knowledge_point": kp})

    print(f"\n===== 本次命制（知识点：{result['knowledge_point']}）=====")
    for i, q in enumerate(result["generated"], 1):
        print(f"\n--- 第 {i} 题 [{q['question_type']} | 难度 {q['difficulty']}] ---")
        print(q["stem"])
        if q.get("options"):
            print(q["options"])
        print(f"答案: {final_answer(q)}")
        print(f"解析: {clean_analysis(q['analysis'])}")

    print(f"\n共入库 {result['saved']} 道，可直接运行 python -m app.practice 练习新题")


if __name__ == "__main__":
    main()
