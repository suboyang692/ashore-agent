"""研岸 D2-B：混合检索 —— 向量检索 + BM25，用 RRF 按排名融合。

D11 追加：cached_hybrid_search() 在 hybrid_search() 外面套了一层 Redis 缓存
（本文件的 hybrid_search 保持纯函数，评测脚本仍然每次真检索）。
D13 追加：命中结果带上切片页码与 cite（「文件名 · 第N页」），答疑 Agent 引用出处时
才有页码可给 —— 否则引用只能到文件名，用户没法回到原文核对。

RRF(Reciprocal Rank Fusion): score(d) = Σ 1/(k + rank(d))，k 取 60（论文默认）。
好处: 两种检索各自擅长的结果都能进入最终 top-k，不会被一方淹没。
"""
import sys

import jieba
from rank_bm25 import BM25Okapi

from app import cache
from app.embedding import embed_query
from app.ingest import get_collection

RRF_K = 60


def _tokenize(text: str):
    return [w for w in jieba.lcut(text) if w.strip()]


def cite_of(hit: dict) -> str:
    """切片出处文案：有页码给「文件名 · 第N页」，没有就只给文件名。"""
    source = hit.get("source") or "未知来源"
    page = hit.get("page") or 0
    return f"{source} · 第{page}页" if page else source


def vector_search(query: str, top_k: int = 5):
    col = get_collection()
    if col.count() == 0:
        return []
    res = col.query(query_embeddings=[embed_query(query)], n_results=min(top_k, col.count()))
    hits = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        hits.append({"text": doc, "source": meta.get("source", ""),
                     "page": meta.get("page") or 0, "score": 1 - dist, "via": "vector"})
    return hits


def bm25_search(query: str, top_k: int = 5):
    col = get_collection()
    data = col.get(include=["documents", "metadatas"])
    docs = data.get("documents") or []
    if not docs:
        return []
    bm25 = BM25Okapi([_tokenize(d) for d in docs])
    scores = bm25.get_scores(_tokenize(query))
    # 分数为 0 的命中要丢掉：BM25Okapi 对完全不含查询词的文档也会给出一条记录，
    # 而 top_k 是按条数截断的 —— 不筛的话这些切片照样进 RRF，白拿一份 1/(k+rank)
    # 的排名分，把不相关内容顶进最终结果。先筛再截断，才不会白白少召回几条。
    ranked = [i for i in sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)
              if scores[i] > 0][:top_k]
    out = []
    for i in ranked:
        meta = (data["metadatas"][i] or {}) if data.get("metadatas") else {}
        out.append({"text": docs[i], "source": meta.get("source", ""),
                    "page": meta.get("page") or 0,
                    "score": float(scores[i]), "via": "bm25"})
    return out


def hybrid_search(query: str, top_k: int = 5):
    """向量 + BM25 各取 top_k，用 RRF 融合排名后返回前 top_k。"""
    vec_hits = vector_search(query, top_k)
    bm25_hits = bm25_search(query, top_k)

    scores, store = {}, {}
    for hits, tag in ((vec_hits, "vector"), (bm25_hits, "bm25")):
        for rank, hit in enumerate(hits):
            key = hit["text"][:60]
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank + 1)
            if key not in store:
                store[key] = {"text": hit["text"], "source": hit["source"],
                              "page": hit.get("page") or 0, "via": tag}

    ranked = sorted(scores, key=lambda k: scores[k], reverse=True)[:top_k]
    out = []
    for key in ranked:
        item = dict(store[key])
        item["rrf_score"] = round(scores[key], 5)
        item["cite"] = cite_of(item)
        out.append(item)
    return out


def cached_hybrid_search(query: str, top_k: int = 5):
    """带 Redis 缓存的混合检索。

    同一查询在知识库未变更（kb_version 未变）时直接命中缓存；
    空结果不写缓存，否则「知识库还没入库」会被固化下来。
    """
    key = cache.retrieval_key(query, top_k)
    cached = cache.get_json(key)
    if cached is not None:
        return cached
    hits = hybrid_search(query, top_k)
    if hits:
        cache.set_json(key, hits, ttl=cache.CACHE_TTL)
    return hits


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "定积分怎么计算"
    for hit in hybrid_search(query):
        print(f"[{hit['via']} | rrf={hit['rrf_score']}] "
              f"{hit.get('cite') or hit['source']} | {hit['text'][:80]}…")
