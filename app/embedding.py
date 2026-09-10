"""研岸：文本向量化（阿里云百炼 DashScope Embedding，OpenAI 兼容接口）。"""
from openai import OpenAI

from app.config import DASHSCOPE_API_KEY, LLM_BASE_URL

EMBED_MODEL = "text-embedding-v3"
BATCH = 10  # 百炼单次批量上限较小，分批调用

_client = None


def _client_or_raise() -> OpenAI:
    global _client
    if _client is None:
        if not DASHSCOPE_API_KEY or DASHSCOPE_API_KEY.startswith("sk-在这里"):
            raise RuntimeError("请先在 .env 配置 DASHSCOPE_API_KEY")
        _client = OpenAI(api_key=DASHSCOPE_API_KEY, base_url=LLM_BASE_URL)
    return _client


def embed_texts(texts):
    """批量向量化，返回 List[List[float]]。"""
    client = _client_or_raise()
    vectors = []
    for i in range(0, len(texts), BATCH):
        batch = texts[i:i + BATCH]
        resp = client.embeddings.create(model=EMBED_MODEL, input=batch)
        vectors.extend([d.embedding for d in resp.data])
    return vectors


def embed_query(text: str):
    return embed_texts([text])[0]
