"""研岸 D2-B：混合检索 —— 向量检索 + BM25，用 RRF 按排名融合。

RRF(Reciprocal Rank Fusion): score(d) = Σ 1/(k + rank(d))，k 取 60（论文默认）。
好处: 两种检索各自擅长的结果都能进入最终 top-k，不会被一方淹没。
"""
import sys

import jieba
from rank_bm25 import BM25Okapi

from app.embedding import embed_query
from app.ingest import get_collection

RRF_K = 60


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
    """向量 + BM25 各取 top_k，用 RRF 融合排名后返回前 top_k。"""
    vec_hits = vector_search(query, top_k)
    bm25_hits = bm25_search(query, top_k)

    scores, store = {}, {}
    for hits, tag in ((vec_hits, "vector"), (bm25_hits, "bm25")):
        for rank, hit in enumerate(hits):
            key = hit["text"][:60]
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank + 1)
            if key not in store:
                store[key] = {"text": hit["text"], "source": hit["source"], "via": tag}

    ranked = sorted(scores, key=lambda k: scores[k], reverse=True)[:top_k]
    out = []
    for key in ranked:
        item = dict(store[key])
        item["rrf_score"] = round(scores[key], 5)
        out.append(item)
    return out


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "定积分怎么计算"
    for hit in hybrid_search(query):
        via, source, text, rrf = hit["via"], hit["source"], hit["text"][:80], hit["rrf_score"]
        print(f"[{via} | rrf={rrf}] {source} | {text}…")
