"""研岸 D1：LLM 客户端封装（OpenAI 兼容接口，阿里云百炼）。"""
from openai import OpenAI
from app.config import DASHSCOPE_API_KEY, LLM_BASE_URL, LLM_MODEL

_client = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not DASHSCOPE_API_KEY or DASHSCOPE_API_KEY.startswith("sk-在这里"):
            raise RuntimeError("请先在 .env 配置 DASHSCOPE_API_KEY")
        _client = OpenAI(api_key=DASHSCOPE_API_KEY, base_url=LLM_BASE_URL)
    return _client


def chat(messages, tools=None, temperature=0.3):
    """普通对话 / 带工具（Function Calling）的对话，返回 message 对象。"""
    kwargs = dict(model=LLM_MODEL, messages=messages, temperature=temperature)
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    resp = get_client().chat.completions.create(**kwargs)
    return resp.choices[0].message
