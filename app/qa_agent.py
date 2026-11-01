"""答疑 Agent —— RAG 检索 + 强制引用来源。

用法: python -m app.qa_agent
说明: 模型自主决定调用 search_knowledge 工具检索讲义，
      基于检索片段回答并标注来源；检索不到时明确说明，不编造。
"""
import json

from app.llm import chat
from app.retriever import cached_hybrid_search

SYSTEM_PROMPT = (
    "你是考研数学答疑助手。回答规则：\n"
    "1. 回答知识点或解题方法前，必须先调用 search_knowledge 检索讲义；\n"
    "2. 严格区分「讲义原文」与「补充推导（非讲义原文）」：只有片段中明确出现的内容"
    "才能写成讲义结论；由片段推导、结合通用数学知识补充的内容必须标明是补充，"
    "并说明讲义未直接给出该结论，不得包装成讲义原文；补充推导必须写全适用条件、"
    "变量范围和端点对应关系；换元、开方、三角代换等要注明连续可导、单调性或符号取值条件；\n"
    "3. 回答必须基于检索到的片段，不得编造公式或结论；\n"
    "4. 回答末尾用「来源：xxx」标注出处，就是片段标注里的文件名与页码"
    "（如「讲义.md · 第9页」）；补充推导不能单独作为讲义出处；\n"
    "5. 检索不到相关内容时，明确说明「讲义中未涵盖」，不要硬答；\n"
    "6. 默认先给结论，再给必要步骤；正文控制在 800 字以内，例子最多 2 个，"
    "常见错误最多列 2 条，不重复解释同一条规则。用户明确要求展开时再增加细节；\n"
    "7. 每个例子的上下限必须逐一代入原题核对，不得沿用其他例子的数值；"
    "若无法确认端点，宁可删掉例子，也不能写出错误区间或错误答案。"
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "检索考研知识库，返回与问题最相关的讲义片段。回答知识点/方法类问题前必须调用。",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "检索关键词，如：定积分 计算方法"}},
                "required": ["query"],
            },
        },
    }
]

MAX_TOOL_ROUNDS = 3


def search_knowledge(query: str, top_k: int = 4) -> str:
    """工具实现：混合检索知识库，把片段拼成上下文返回给模型。"""
    hits = cached_hybrid_search(query, top_k=top_k)
    if not hits:
        return "知识库中未检索到相关内容。"
    blocks = []
    for i, h in enumerate(hits, 1):
        blocks.append(f"[片段{i} | 出处: {h.get('cite') or h['source']} | 命中方式: {h['via']}]\n{h['text']}")
    return "\n\n".join(blocks)


def ask(question: str, history=None) -> str:
    """单轮问答：带工具的多轮循环，直到模型给出最终回答。"""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += history or []
    messages.append({"role": "user", "content": question})

    for _ in range(MAX_TOOL_ROUNDS):
        msg = chat(messages, tools=TOOLS)
        if not msg.tool_calls:
            return msg.content
        messages.append(msg)
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            query = args.get("query", question)
            print(f"  [工具调用] search_knowledge(query='{query}')")
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": search_knowledge(query),
            })
    return "（已达到最大工具调用轮数，请换个问法）"


def main():
    print("研岸答疑 Agent（输入 q 退出）")
    history = []
    while True:
        question = input("\n你: ").strip()
        if question.lower() in ("q", "quit", "exit"):
            break
        if not question:
            continue
        answer = ask(question, history)
        print("研岸:", answer)
        history += [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]


if __name__ == "__main__":
    main()
