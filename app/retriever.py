"""研岸 D2-B：混合检索 —— 向量检索 + BM25，去重合并返回 top-k。"""
import sys

import jieba
from rank_bm25 import BM25Okapi

from app.embedding import embed_query
from app.ingest import get_collection


def _tokenize(text: str):
    return [w for w in jieba.lcut(text) if w.strip()]


def vector_search(query: str, top_k: int = 5):
    col = get_collection()
    if col.count() == 0:
        return []
    res = col.query(query_embeddings=[embed_query(query)], n_results=min(top_k, col.count()))
    hits = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        hits.append({"text": doc, "source": meta.get("source", ""), "score": 1 - dist, "via": "vector"})
    return hits


def bm25_search(query: str, top_k: int = 5):
    col = get_collection()
    data = col.get(include=["documents", "metadatas"])
    docs = data.get("documents") or []
    if not docs:
        return []
    bm25 = BM25Okapi([_tokenize(d) for d in docs])
    scores = bm25.get_scores(_tokenize(query))
    ranked = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)[:top_k]
    out = []
    for i in ranked:
        meta = (data["metadatas"][i] or {}) if data.get("metadatas") else {}
        out.append({"text": docs[i], "source": meta.get("source", ""),
                    "score": float(scores[i]), "via": "bm25"})
    return out


def hybrid_search(query: str, top_k: int = 5):
    """向量 + BM25 各取若干，按文本前缀去重合并（向量结果优先）。"""
    merged, seen = [], set()
    for hit in vector_search(query, top_k) + bm25_search(query, top_k):
        key = hit["text"][:60]
        if key in seen:
            continue
        seen.add(key)
        merged.append(hit)
    return merged[:top_k]


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "定积分怎么计算"
    for hit in hybrid_search(query):
        via, source, text = hit["via"], hit["source"], hit["text"][:80]
        print(f"[{via}] {source} | {text}…")
