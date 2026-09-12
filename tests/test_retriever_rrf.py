"""混合检索的 RRF 融合（D2 的修复点：BM25 结果曾被向量结果淹没）。"""
from app import retriever


def _hit(text, via="vector"):
    return {"text": text, "source": "\u8bb2\u4e49.md", "score": 0.0, "via": via}


def test_rrf_keeps_results_from_both_retrievers(monkeypatch):
    monkeypatch.setattr(retriever, "vector_search",
                        lambda q, k=5: [_hit("A"), _hit("B")])
    monkeypatch.setattr(retriever, "bm25_search",
                        lambda q, k=5: [_hit("C", "bm25"), _hit("D", "bm25")])
    out = retriever.hybrid_search("任意查询", top_k=4)
    assert {h["text"] for h in out} == {"A", "B", "C", "D"}


def test_rrf_rewards_docs_found_by_both_retrievers(monkeypatch):
    monkeypatch.setattr(retriever, "vector_search",
                        lambda q, k=5: [_hit("v0"), _hit("v1"), _hit("共享")])
    monkeypatch.setattr(retriever, "bm25_search",
                        lambda q, k=5: [_hit("共享", "bm25"), _hit("b0", "bm25")])
    out = retriever.hybrid_search("q", top_k=5)
    assert out[0]["text"] == "共享"
    assert out[0]["rrf_score"] > out[1]["rrf_score"]


def test_rrf_respects_top_k(monkeypatch):
    monkeypatch.setattr(retriever, "vector_search",
                        lambda q, k=5: [_hit(f"v{i}") for i in range(5)])
    monkeypatch.setattr(retriever, "bm25_search",
                        lambda q, k=5: [_hit(f"b{i}", "bm25") for i in range(5)])
    assert len(retriever.hybrid_search("q", top_k=3)) == 3


def test_rrf_handles_empty_results(monkeypatch):
    monkeypatch.setattr(retriever, "vector_search", lambda q, k=5: [])
    monkeypatch.setattr(retriever, "bm25_search", lambda q, k=5: [])
    assert retriever.hybrid_search("q", top_k=5) == []
