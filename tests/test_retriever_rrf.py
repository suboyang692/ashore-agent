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


class _FakeCollection:
    """只实现 bm25_search 用到的那一个方法。"""

    def __init__(self, docs):
        self._docs = docs

    def get(self, include=None):
        return {"documents": self._docs,
                "metadatas": [{"source": "\u8bb2\u4e49.md", "page": 0} for _ in self._docs]}


def test_bm25_search_drops_zero_score_hits(monkeypatch):
    """BM25 给不含查询词的文档 0 分 —— 这种命中不能进 RRF，否则白拿一份排名分。

    实测现象：「2023 斜渐近线」的纯 BM25 结果里有两条 0 分切片，它们随后出现在
    混合检索的 top-5 里，把真正相关的片段挤掉了位置。
    """
    monkeypatch.setattr(retriever, "get_collection", lambda: _FakeCollection(
        ["分部积分法的选 u 口诀：反对幂指三", "完全不相关的一段话", "另一个无关段落"]))
    hits = retriever.bm25_search("分部积分法", top_k=5)
    assert hits, "包含查询词的切片应该被召回"
    assert all(h["score"] > 0 for h in hits)
    assert all("分部积分法" in h["text"] for h in hits)


def test_bm25_search_returns_empty_when_nothing_matches(monkeypatch):
    monkeypatch.setattr(retriever, "get_collection",
                        lambda: _FakeCollection(["分部积分法", "定积分计算"]))
    assert retriever.bm25_search("zzzz-corpus-miss", top_k=5) == []


def test_rrf_handles_empty_results(monkeypatch):
    monkeypatch.setattr(retriever, "vector_search", lambda q, k=5: [])
    monkeypatch.setattr(retriever, "bm25_search", lambda q, k=5: [])
    assert retriever.hybrid_search("q", top_k=5) == []
