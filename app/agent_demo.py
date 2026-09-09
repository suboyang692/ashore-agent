"""研岸 D1：跑通第一个 Agent —— 大模型自主判断是否调用工具。

运行: python -m app.agent_demo
说明: 演示 ReAct 的最小骨架：用户提问 -> 模型决定调工具 -> 拿结果 -> 组织最终回答。
D1 的知识库是 stub 占位，后续接入向量检索。
"""
import json

from app.llm import chat

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_knowledge_explain",
            "description": "获取某个考研知识点的讲解与典型方法。当用户问某个知识点怎么理解、怎么考时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "knowledge_point": {"type": "string", "description": "知识点名称，如：极限、定积分、资本资产定价模型"}
                },
                "required": ["knowledge_point"],
            },
        },
    }
]

# D1 占位知识库：之后替换为「教材切片 + 向量检索」
KNOWLEDGE_STUB = {
    "极限": "求极限核心方法：等价无穷小替换、洛必达法则、夹逼准则。注意等价替换只在乘除因子中可用。",
    "定积分": "定积分计算四大方法：牛顿-莱布尼茨公式、换元积分、分部积分、对称区间奇偶性化简。",
    "资本资产定价模型": "CAPM: E(Ri)=Rf+βi[E(Rm)-Rf]。β 衡量系统性风险，非系统性风险可被分散。",
}


def call_tool(name: str, args: dict) -> str:
    if name == "get_knowledge_explain":
        return KNOWLEDGE_STUB.get(args.get("knowledge_point", ""), "知识库暂无该知识点讲解（D1 为占位数据）。")
    return "未知工具"


def main():
    question = input("请输入你的考研问题（直接回车用默认示例）: ").strip()
    if not question:
        question = "定积分这个知识点怎么理解？做题常用什么方法？"
    messages = [{"role": "user", "content": question}]

    print("\n[1/3] 调用大模型，等待是否触发工具…\n")
    msg = chat(messages, tools=TOOLS)

    if msg.tool_calls:
        tool = msg.tool_calls[0]
        print(f"[2/3] 模型决定调用工具: {tool.function.name}({tool.function.arguments})")
        result = call_tool(tool.function.name, json.loads(tool.function.arguments))
        print(f"      工具返回: {result[:60]}…")
        messages.append(msg)  # assistant 的 tool_calls 回传
        messages.append({"role": "tool", "tool_call_id": tool.id, "content": result})
        print("\n[3/3] 让模型基于工具结果组织最终回答…\n")
        final = chat(messages)
    else:
        print("[2/3] 模型未触发工具，直接回答")
        final = msg

    print("===== 最终回答 =====\n" + final.content)


if __name__ == "__main__":
    main()
