"""研岸：查看 RAG 知识库内容与混合检索效果。

用法:
    python -m app.inspect_kb                # 知识库概况 + 切片样本
    python -m app.inspect_kb "定积分 计算"    # 对比 向量 / BM25 / 混合 三种检索结果
"""
import sys

import chromadb

from app.ingest import CHROMA_DIR, COLLECTION
from app.retriever import bm25_search, hybrid_search, vector_search


def show_overview():
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    col = client.get_or_create_collection(name=COLLECTION)
    print("===== 知识库概况 =====")
    print(f"  存储位置: {CHROMA_DIR}")
    print(f"  切片总数: {col.count()}")
    data = col.get(include=["documents", "metadatas"])
    docs = data.get("documents") or []
    metas = data.get("metadatas") or []
    stat = {}
    for m in metas:
        m = m or {}
        entry = stat.setdefault(m.get("source", "未知"), {"chunks": 0, "pages": set()})
        entry["chunks"] += 1
        if m.get("page"):
            entry["pages"].add(m["page"])
    print("  按来源统计:")
    for s, e in stat.items():
        tail = f"，覆盖 {len(e['pages'])} 页" if e["pages"] else ""
        print(f"    - {s}: {e['chunks']} 个切片{tail}")
    print("\n===== 切片样本（前 5 个，各截断 100 字）=====")
    for i, d in enumerate(docs[:5]):
        meta = metas[i] or {}
        page = meta.get("page") or 0
        src = meta.get("source", "") + (f" · 第{page}页" if page else "")
        print(f"\n[{i + 1}] 来源: {src}\n    {d[:100].replace(chr(10), ' ')}…")


def show_search(query: str):
    print(f"===== 检索对比: 「{query}」=====")
    print("\n--- 1) 纯向量检索（语义相似）---")
    for h in vector_search(query, 5):
        print(f"  [{h['score']:.3f}] {h['text'][:70].replace(chr(10), ' ')}…")
    print("\n--- 2) 纯 BM25 检索（关键词匹配）---")
    for h in bm25_search(query, 5):
        print(f"  [{h['score']:.3f}] {h['text'][:70].replace(chr(10), ' ')}…")
    print("\n--- 3) 混合检索（最终喂给 Agent 的结果）---")
    for h in hybrid_search(query, 5):
        src = h.get("cite") or h["source"]
        print(f"  [{h['via']} | rrf={h.get('rrf_score', 0)}] {h['text'][:60].replace(chr(10), ' ')}…")
        print(f"      出处: {src}")


def main():
    if len(sys.argv) > 1:
        show_search(" ".join(sys.argv[1:]))
    else:
        show_overview()


if __name__ == "__main__":
    main()
