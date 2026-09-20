"""知识库入库 —— 文档 -> 切片 -> 向量化 -> ChromaDB。

入库成功后把 Redis 里的检索缓存版本号 +1，避免用户拿到已作废的切片。

另外三点：
  1. 支持 `<!-- page: N -->` 页码锚点（app/exam_ocr.py 转录真题时写入），按页切片并把
     页码写进元数据，检索出处才能显示成「文件名 · 第N页」而不是只有文件名；PDF 走
     pdfplumber 时也补上同样的锚点。
  2. 入库前先删掉该来源的旧切片。切片策略或 ID 规则一变，旧 ID 就再也覆盖不到，
     不删就是新旧共存，检索结果开始出现重复。
  3. PDF 文本层过薄时给出提示 —— 公式型/扫描件用 pdfplumber 只会抽出到处是空洞的
     骨架（「(1)曲线 的斜渐近线为 (A) (B)」），应当先用 app.exam_ocr 转录。

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

from app import cache
from app.config import BASE_DIR
from app.embedding import embed_texts

KNOWLEDGE_DIR = BASE_DIR / "knowledge"
CHROMA_DIR = BASE_DIR / "data" / "chroma"
COLLECTION = "ashore_kb"

CHUNK_SIZE = 400
CHUNK_OVERLAP = 80

PAGE_MARK = re.compile(r"<!--\s*page:\s*(\d+)\s*-->")
THIN_PAGE_CHARS = 120       # 每页平均抽不到这么多字符，基本可以断定文本层是空的


def _read_pdf(path: Path) -> str:
    import pdfplumber

    parts, page_count = [], 0
    with pdfplumber.open(path) as pdf:
        page_count = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            text = (page.extract_text() or "").strip()
            if text:
                parts.append(f"<!-- page: {i + 1} -->\n{text}")
    body = "\n\n".join(parts)
    avg = len(body) / page_count if page_count else 0
    if page_count and avg < THIN_PAGE_CHARS:
        print(f"  [warn] {path.name}: 平均每页只抽出 {avg:.0f} 个字符，文本层过薄。")
        print("         公式型 / 扫描件请先转录成 Markdown 再入库：")
        print(f"         python -m app.exam_ocr {path.as_posix()}")
    return body


def read_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _read_pdf(path)
    if suffix in (".md", ".txt"):
        return path.read_text(encoding="utf-8", errors="ignore")
    raise ValueError(f"不支持的格式: {suffix}（支持 .pdf/.md/.txt）")


def split_by_page(text: str):
    """按 `<!-- page: N -->` 锚点切成 [(页码, 正文)]；没有锚点则整篇算第 0 页。"""
    marks = list(PAGE_MARK.finditer(text))
    if not marks:
        return [(0, text)]
    spans = []
    for i, mark in enumerate(marks):
        start = mark.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        seg = text[start:end].strip()
        if seg:
            spans.append((int(mark.group(1)), seg))
    return spans


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
    col = get_collection()

    ids, documents, metadatas = [], [], []
    for page, seg in split_by_page(text):
        for i, chunk in enumerate(split_text(seg)):
            ids.append(f"{path.stem}-p{page}-{i}")
            documents.append(chunk)
            metadatas.append({"source": path.name, "page": page, "chunk_index": i})

    if not documents:
        print(f"  [skip] {path.name}: 没有提取到有效文本")
        return 0

    # 先清掉该来源的旧切片：改了切片策略或 ID 规则后旧切片再也覆盖不到，
    # 不清就是新旧共存，检索结果开始出现重复。
    stale = col.get(where={"source": path.name}).get("ids") or []
    if stale:
        col.delete(ids=stale)
        print(f"  [clean] {path.name}: 清掉旧切片 {len(stale)} 个")

    vectors = embed_texts(documents)
    col.upsert(ids=ids, documents=documents, embeddings=vectors, metadatas=metadatas)
    pages = len({m["page"] for m in metadatas if m["page"]})
    tail = f"，覆盖 {pages} 页" if pages else ""
    print(f"  [ok] {path.name}: {len(documents)} 个切片入库{tail}")
    return len(documents)


def main():
    args = sys.argv[1:]
    if args:
        targets = [Path(a) for a in args]
    else:
        targets = sorted(p for p in KNOWLEDGE_DIR.glob("*") if p.suffix.lower() in (".pdf", ".md", ".txt"))
    if not targets:
        print(f"{KNOWLEDGE_DIR} 下没有可入库的文件（.pdf/.md/.txt）")
        return
    total = 0
    for p in targets:
        print(f"处理: {p.name}")
        total += ingest_file(p)
    col = get_collection()
    print(f"\n完成：本次 {total} 个切片，知识库当前共 {col.count()} 个切片")
    if total:
        # 版本号 +1：旧版本的检索缓存再也命中不到，由 TTL 自然回收（不用 KEYS 扫删）
        print(f"检索缓存版本号 -> {cache.bump_kb_version()}（旧缓存已失效）")


if __name__ == "__main__":
    main()
