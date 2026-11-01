"""模型配置自检：先看配置，再用 --live 验证账户、模型和工具调用。

用法:
    python -m app.inspect_llm
    python -m app.inspect_llm --live
    python -m app.inspect_llm --live --tools
"""
import sys

from app.config import DASHSCOPE_API_KEY, EMBED_MODEL, LLM_BASE_URL, LLM_MODEL


def mask_key(key: str) -> str:
    if not key:
        return "（未配置）"
    if key.startswith("sk-在这里"):
        return "（仍是示例占位值）"
    if len(key) < 10:
        return "***"
    return f"{key[:6]}...{key[-4:]}"


def _billing_hint(error: Exception) -> str | None:
    text = str(error)
    lower = text.lower()
    if "arrearage" in lower or "overdue-payment" in lower or "access denied" in lower:
        return "百炼账户余额不足或状态异常，请先在控制台结清欠费/检查账户状态。"
    if "invalid api key" in lower or "incorrect api key" in lower:
        return "API Key 无效或不属于当前百炼账户。"
    return None


def main() -> int:
    print("===== 模型配置 =====")
    print("LLM_MODEL  :", LLM_MODEL)
    print("LLM_BASE_URL:", LLM_BASE_URL)
    print("EMBED_MODEL:", EMBED_MODEL)
    print("API Key    :", mask_key(DASHSCOPE_API_KEY))
    if "--live" not in sys.argv:
        print("\n只检查了配置；加 --live 会真实调用一次模型（消耗少量额度）。")
        return 0

    try:
        from openai import OpenAI

        client = OpenAI(api_key=DASHSCOPE_API_KEY, base_url=LLM_BASE_URL)
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": "只回复：模型可用"}],
            max_tokens=32,
        )
        print("\n[ok] 文本调用成功：", response.choices[0].message.content)
    except Exception as error:
        print(f"\n[fail] {type(error).__name__}: {error}")
        hint = _billing_hint(error)
        if hint:
            print("提示：", hint)
        return 1

    if "--tools" not in sys.argv:
        return 0

    tools = [{
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "检索考研讲义",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    }]
    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": "请调用 search_knowledge 检索定积分"}],
            tools=tools,
            tool_choice="auto",
            max_tokens=64,
        )
        calls = response.choices[0].message.tool_calls or []
        print("[ok] 工具调用成功：" if calls else "[warn] 模型没有发起工具调用")
        for call in calls:
            print("     ", call.function.name, call.function.arguments)
        return 0 if calls else 2
    except Exception as error:
        print(f"[fail] 工具调用失败：{type(error).__name__}: {error}")
        hint = _billing_hint(error)
        if hint:
            print("提示：", hint)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
