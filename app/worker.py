"""Background worker for document parsing, chunking and indexing."""
import hashlib
from pathlib import Path

from app import cache
from app.config import EMBED_MODEL, UPLOAD_DIR
from app.embedding import embed_texts
from app.ingest import get_collection, read_file, split_by_page, split_text
from app.repositories import document_repository, job_repository


def _safe_path(raw_path: str) -> Path:
    path = Path(raw_path).resolve()
    root = UPLOAD_DIR.resolve()
    if root != path.parent and root not in path.parents:
        raise ValueError("文档路径不在上传目录内")
    if not path.is_file():
        raise FileNotFoundError(f"文档文件不存在: {path.name}")
    return path


def process_document_job(job_id: str) -> dict:
    job = job_repository.get(job_id)
    if not job:
        raise LookupError(f"任务不存在: {job_id}")
    payload = job.get("payload") or {}
    document_id = int(payload["document_id"])
    version_id = int(payload["version_id"])
    path = _safe_path(payload["path"])
    source_name = payload.get("source_name") or path.name

    job_repository.mark_running(job_id)
    document_repository.update_status(document_id, "processing")
    document_repository.update_version_status(version_id, "processing")

    try:
        text = read_file(path)
        records, documents, metadatas, ids = [], [], [], []
        chunk_no = 0
        pages = 0
        for page, segment in split_by_page(text):
            if page:
                pages += 1
            for index, content in enumerate(split_text(segment)):
                vector_id = f"doc-{document_id}-v{version_id}-p{page}-{index}"
                records.append({
                    "chunk_no": chunk_no,
                    "content": content,
                    "page_no": page or None,
                    "vector_id": vector_id,
                    "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                })
                ids.append(vector_id)
                documents.append(content)
                metadatas.append({
                    "source": source_name,
                    "page": page,
                    "chunk_index": index,
                    "document_id": str(document_id),
                    "version_id": str(version_id),
                })
                chunk_no += 1
        if not documents:
            raise ValueError("没有提取到有效文本")

        job_repository.update_progress(job_id, 40)
        vectors = embed_texts(documents)
        job_repository.update_progress(job_id, 80)

        collection = get_collection()
        collection.delete(where={"document_id": str(document_id)})
        collection.upsert(
            ids=ids, documents=documents, embeddings=vectors, metadatas=metadatas,
        )
        document_repository.add_chunks(version_id, records)
        document_repository.update_version_status(version_id, "ready")
        document_repository.update_status(document_id, "ready")
        cache.bump_kb_version()

        result = {
            "chunks": len(records),
            "pages": pages,
            "embedding_model": EMBED_MODEL,
        }
        job_repository.mark_success(job_id, result)
        return result
    except Exception as error:
        message = str(error) or type(error).__name__
        document_repository.update_version_status(version_id, "failed", message)
        document_repository.update_status(document_id, "failed", message)
        job_repository.mark_failed(job_id, message)
        raise
