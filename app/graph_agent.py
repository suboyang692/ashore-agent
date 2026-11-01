"""答疑 Agent —— LangGraph 状态图编排的 ReAct 循环。

图结构（ReAct）:
    agent 节点（调模型，决定是否用工具）
        │ 有 tool_calls
        ▼
    tools 节点（执行 search_knowledge 检索知识库）
        │
        └──► 回到 agent 节点，直到模型给出最终回答 → END

用法: python -m app.graph_agent
"""
import re
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from app.config import DASHSCOPE_API_KEY, LLM_BASE_URL, LLM_MODEL
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


_SOURCE_BLOCK_RE = re.compile(
    r"\[片段(?P<fragment>\d+) \| 出处: (?P<cite>[^|\]]+) \| 命中方式: (?P<via>[^\]\n]+)\]\n"
    r"(?P<text>.*?)(?=\n\n\[片段|\Z)",
    re.S,
)
_CITE_LINE_RE = re.compile(r"来源\s*[:：]\s*([^\n]+)")
_PAGE_RE = re.compile(r"^(?P<source>.*?)\s*·\s*第(?P<page>\d+)页$")
_PAGE_RANGE_RE = re.compile(r"第(?P<start>\d+)(?:\s*[-–—~至]\s*(?P<end>\d+))?页")
_CITE_SPLIT_RE = re.compile(r"[、,，;；]")
_NO_SOURCE_MARKERS = ("未涵盖", "未收录", "未找到", "没有找到", "无法回答", "未提供")


def _clean_token(text: str) -> str:
    return text.strip().strip("*`_ ").strip().rstrip("。；;，,）)】]")


def _parse_cite(cite: str) -> tuple[str, int | None]:
    """把「文件名 · 第N页」拆成文件名与页码；没有页码就保留整段文件名。"""
    match = _PAGE_RE.match(cite.strip())
    if not match:
        return cite.strip(), None
    return match.group("source").strip(), int(match.group("page"))


def _citation_tokens(answer: str) -> list[str]:
    tokens = []
    for match in _CITE_LINE_RE.finditer(answer or ""):
        tail = match.group(1).split("。")[0]
        for part in _CITE_SPLIT_RE.split(tail):
            token = _clean_token(part)
            if token and not any(marker in token for marker in _NO_SOURCE_MARKERS):
                tokens.append(token)
    return tokens


def _matches_cited_source(token: str, item: dict) -> bool:
    """判断一条来源是否被「文件名 · 第N页」或「第N-M页」覆盖。"""
    if not item["source"] or item["source"] not in token:
        return False
    page_match = _PAGE_RANGE_RE.search(token)
    if not page_match:
        return True
    if item["page"] is None:
        return False
    start = int(page_match.group("start"))
    end = int(page_match.group("end") or start)
    return start <= item["page"] <= end


def extract_sources(messages: list, answer: str) -> list[dict]:
    """从工具消息中提取本次检索来源，并标记回答明确引用的条目。

    工具输出是模型实际看到的检索上下文，比从回答正文猜文件名可靠。
    同一出处只保留一条，重复切片合并到首次出现的来源里。
    """
    by_cite: dict[str, dict] = {}
    for message in messages or []:
        if getattr(message, "type", "") != "tool":
            continue
        content = getattr(message, "content", "")
        if not isinstance(content, str):
            continue
        for match in _SOURCE_BLOCK_RE.finditer(content):
            cite = match.group("cite").strip()
            source, page = _parse_cite(cite)
            excerpt = match.group("text").strip()
            item = by_cite.get(cite)
            if item:
                if excerpt and excerpt not in item["excerpt"]:
                    item["excerpt"] = f"{item['excerpt']}\n\n{excerpt}".strip()[:1200]
                continue
            by_cite[cite] = {
                "fragment": int(match.group("fragment")),
                "cite": cite,
                "source": source,
                "page": page,
                "via": match.group("via").strip(),
                "excerpt": excerpt[:1200],
                "cited": False,
            }

    sources = list(by_cite.values())
    fragment_counts: dict[int, int] = {}
    for item in sources:
        fragment_counts[item["fragment"]] = fragment_counts.get(item["fragment"], 0) + 1

    for token in _citation_tokens(answer):
        for item in sources:
            fragment_token = f"片段{item['fragment']}"
            exact_fragment = token == fragment_token and fragment_counts[item["fragment"]] == 1
            exact_cite = token == item["cite"]
            file_and_page = _matches_cited_source(token, item)
            if exact_fragment or exact_cite or file_and_page:
                item["cited"] = True
    return sources


@tool
def search_knowledge(query: str) -> str:
    """检索考研知识库，返回与问题最相关的讲义片段。回答知识点或方法类问题前必须调用。"""
    hits = cached_hybrid_search(query, top_k=4)
    if not hits:
        return "知识库中未检索到相关内容。"
    blocks = []
    for i, h in enumerate(hits, 1):
        blocks.append(f"[片段{i} | 出处: {h.get('cite') or h['source']} | 命中方式: {h['via']}]\n{h['text']}")
    return "\n\n".join(blocks)


TOOLS = [search_knowledge]

_model = ChatOpenAI(
    model=LLM_MODEL, api_key=DASHSCOPE_API_KEY, base_url=LLM_BASE_URL, temperature=0.3
)
_model_with_tools = _model.bind_tools(TOOLS)


class State(TypedDict):
    messages: Annotated[list, add_messages]


def agent_node(state: State):
    """模型节点：带工具调用能力，决定下一步是调用工具还是给出回答。"""
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = _model_with_tools.invoke(messages)
    return {"messages": [response]}


def _message_text(message) -> str:
    """把模型消息的文本内容归一成字符串；兼容分段内容格式。"""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)
    return ""


def tools_node(state: State):
    """工具节点：执行模型请求的工具调用，把结果写回消息流。"""
    last = state["messages"][-1]
    outputs = []
    for call in last.tool_calls:
        print(f"  [工具调用] {call['name']}({call['args']})")
        result = search_knowledge.invoke(call["args"])
        outputs.append(ToolMessage(content=result, tool_call_id=call["id"]))
    return {"messages": outputs}


def should_continue(state: State):
    """条件边：模型还要调工具就去 tools 节点，否则结束。"""
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else END


def build_graph():
    graph = StateGraph(State)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()


_GRAPH = None


def _graph():
    """进程内复用编译后的图，避免每次调用重复编译。"""
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def answer_question(question: str, history: list | None = None) -> dict:
    """可复用入口：给定问题（可带历史消息），返回回答与更新后的消息历史。"""
    messages = list(history or [])
    messages.append(HumanMessage(content=question))
    result = _graph().invoke({"messages": messages})
    msgs = result["messages"]
    answer = msgs[-1].content
    return {
        "answer": answer,
        "messages": msgs,
        "sources": extract_sources(msgs, answer if isinstance(answer, str) else ""),
    }


async def stream_answer_question(question: str, history: list | None = None):
    """流式答疑：逐 token 产出文本，最后补上完整消息与结构化来源。

    这等价于 answer_question 的 ReAct 循环，只是把模型的 invoke 换成 astream。
    事件格式：
        {"type": "token", "text": "..."}
        {"type": "complete", "answer": "...", "messages": [...], "sources": [...]}
    """
    messages = list(history or [])
    messages.append(HumanMessage(content=question))
    final_answer = ""

    for _ in range(4):
        request_messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
        gathered = None
        async for chunk in _model_with_tools.astream(request_messages):
            gathered = chunk if gathered is None else gathered + chunk
            text = _message_text(chunk)
            if text:
                yield {"type": "token", "text": text}

        if gathered is None:
            break

        messages.append(gathered)
        tool_calls = getattr(gathered, "tool_calls", None) or []
        if not tool_calls:
            final_answer = _message_text(gathered)
            if not final_answer.strip():
                messages.pop()
            break

        for call in tool_calls:
            print(f"  [工具调用] {call['name']}({call['args']})")
            result = search_knowledge.invoke(call["args"])
            messages.append(ToolMessage(content=result, tool_call_id=call["id"]))

    # 有些模型会连续调用工具直到轮数耗尽，或返回空的非工具回复。
    # 这时再走一次不绑定工具的模型，强制产出面向用户的最终答案。
    if not final_answer.strip():
        request_messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
        gathered = None
        async for chunk in _model.astream(request_messages):
            gathered = chunk if gathered is None else gathered + chunk
            text = _message_text(chunk)
            if text:
                yield {"type": "token", "text": text}
        if gathered is not None:
            messages.append(gathered)
            final_answer = _message_text(gathered)

    yield {
        "type": "complete",
        "answer": final_answer,
        "messages": messages,
        "sources": extract_sources(messages, final_answer),
    }


def main():
    graph = build_graph()
    print("研岸 LangGraph 答疑 Agent（输入 q 退出）")
    history = []
    while True:
        question = input("\n你: ").strip()
        if question.lower() in ("q", "quit", "exit"):
            break
        if not question:
            continue
        r = answer_question(question, history)
        print("研岸:", r["answer"])
        history = r["messages"]


if __name__ == "__main__":
    main()
