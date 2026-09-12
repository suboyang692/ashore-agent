"""研岸 D3：LangGraph 状态图编排 —— 答疑 Agent 从手写循环升级为图编排。

图结构（ReAct）:
    agent 节点（调模型，决定是否用工具）
        │ 有 tool_calls
        ▼
    tools 节点（执行 search_knowledge 检索知识库）
        │
        └──► 回到 agent 节点，直到模型给出最终回答 → END

用法: python -m app.graph_agent
"""
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
    "2. 回答必须基于检索到的片段，不得编造公式或结论；\n"
    "3. 回答末尾用「来源：xxx」标注引用自哪个片段；\n"
    "4. 检索不到相关内容时，明确说明「讲义中未涵盖」，不要硬答。"
)


@tool
def search_knowledge(query: str) -> str:
    """检索考研知识库，返回与问题最相关的讲义片段。回答知识点或方法类问题前必须调用。"""
    hits = cached_hybrid_search(query, top_k=4)
    if not hits:
        return "知识库中未检索到相关内容。"
    blocks = []
    for i, h in enumerate(hits, 1):
        blocks.append(f"[片段{i} | 来源: {h['source']} | 命中方式: {h['via']}]\n{h['text']}")
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
    return {"answer": msgs[-1].content, "messages": msgs}


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
