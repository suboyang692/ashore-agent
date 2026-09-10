"""研岸 D2-B：知识库入库 —— 文档 -> 切片 -> 向量化 -> ChromaDB。

支持格式: .pdf / .md / .txt
用法:
    python -m app.ingest                  # 入库 knowledge/ 下全部文件
    python -m app.ingest knowledge/xxx.md # 入库指定文件
"""
import re
import sys
from pathlib import Path

import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import BASE_DIR
from app.embedding import embed_texts

KNOWLEDGE_DIR = BASE_DIR / "knowledge"
CHROMA_DIR = BASE_DIR / "data" / "chroma"
COLLECTION = "ashore_kb"

CHUNK_SIZE = 400
CHUNK_OVERLAP = 80


def read_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        import pdfplumber
        parts = []
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages):
                t = page.extract_text() or ""
                if t.strip():
                    parts.append(f"[第{i + 1}页]\n{t}")
        return "\n".join(parts)
    if suffix in (".md", ".txt"):
        return path.read_text(encoding="utf-8", errors="ignore")
    raise ValueError(f"不支持的格式: {suffix}（支持 .pdf/.md/.txt）")


def split_text(text: str):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", "。", "；", " ", ""],
    )
    return [c for c in splitter.split_text(text) if c.strip()]


def get_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection(name=COLLECTION, metadata={"hnsw:space": "cosine"})


def ingest_file(path: Path) -> int:
    text = read_file(path)
    chunks = split_text(text)
    if not chunks:
        print(f"  [skip] {path.name}: 没有提取到有效文本")
        return 0
    vectors = embed_texts(chunks)
    col = get_collection()
    ids = [f"{path.stem}-{i}" for i in range(len(chunks))]
    metadatas = [{"source": path.name, "chunk_index": i} for i in range(len(chunks))]
    col.upsert(ids=ids, documents=chunks, embeddings=vectors, metadatas=metadatas)
    print(f"  [ok] {path.name}: {len(chunks)} 个切片入库")
    return len(chunks)


def main():
    args = sys.argv[1:]
    if args:
        targets = [Path(a) for a in args]
    else:
        targets = sorted([p for p in KNOWLEDGE_DIR.glob("*") if p.suffix.lower() in (".pdf", ".md", ".txt")])
    if not targets:
        print(f"{KNOWLEDGE_DIR} 下没有可入库的文件（.pdf/.md/.txt）")
        return
    total = 0
    for p in targets:
        print(f"处理: {p.name}")
        total += ingest_file(p)
    col = get_collection()
    print(f"\n完成：本次 {total} 个切片，知识库当前共 {col.count()} 个切片")


if __name__ == "__main__":
    main()
