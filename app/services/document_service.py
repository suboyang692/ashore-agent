"""Document upload, versioning and ingestion job orchestration."""
import hashlib
from pathlib import Path

from app.config import EMBED_MODEL, MAX_UPLOAD_MB, UPLOAD_DIR
from app.repositories import document_repository, job_repository
from app.task_queue import enqueue_document_job

ALLOWED_EXTENSIONS = {".pdf", ".md", ".txt"}
MAX_BYTES = MAX_UPLOAD_MB * 1024 * 1024


def _validate(file_name: str, content: bytes) -> str:
    suffix = Path(file_name or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("仅支持 .pdf、.md、.txt 文件")
    if not content:
        raise ValueError("文件内容为空")
    if len(content) > MAX_BYTES:
        raise ValueError(f"文件不能超过 {MAX_UPLOAD_MB} MB")
    return suffix


def _storage_path(file_hash: str, suffix: str) -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR / f"{file_hash}{suffix}"


def _create_job(document_id: int, version_id: int, path: Path,
                source_name: str, owner_id: str):
    job_id = job_repository.create(owner_id, "document_ingest", {
        "document_id": document_id,
        "version_id": version_id,
        "path": str(path),
        "source_name": source_name,
    })
    transport = enqueue_document_job(job_id)
    return job_id, transport


def upload(owner_id: str, file_name: str, content: bytes, title: str = ""):
    suffix = _validate(file_name, content)
    digest = hashlib.sha256(content).hexdigest()
    existing = document_repository.get_by_hash(digest)
    if existing:
        if existing["status"] == "failed":
            return reindex(existing["id"], owner_id)
        return {"document": existing, "job_id": None, "duplicate": True,
                "transport": None}

    display_name = Path(file_name).name[:255]
    title = (title or Path(file_name).stem).strip()[:255]
    document_id = document_repository.create(
        owner_id, title, display_name, digest, "user_upload",
    )
    path = _storage_path(digest, suffix)
    path.write_bytes(content)
    version_id = document_repository.create_version(
        document_id, "upload-v1", EMBED_MODEL, "recursive-400-80",
    )
    job_id, transport = _create_job(document_id, version_id, path, display_name, owner_id)
    return {
        "document": document_repository.get(document_id),
        "version_id": version_id,
        "job_id": job_id,
        "duplicate": False,
        "transport": transport,
    }


def reindex(document_id: int, owner_id: str):
    document = document_repository.get(document_id)
    if not document:
        raise LookupError("文档不存在")
    suffix = Path(document["file_name"]).suffix.lower()
    path = _storage_path(document["file_hash"], suffix)
    if not path.is_file():
        raise LookupError("原始文件不存在，无法重新入库")
    document_repository.update_status(document_id, "processing")
    version_id = document_repository.create_version(
        document_id, "upload-v1", EMBED_MODEL, "recursive-400-80",
    )
    job_id, transport = _create_job(
        document_id, version_id, path, document["file_name"], owner_id,
    )
    return {
        "document": document_repository.get(document_id),
        "version_id": version_id,
        "job_id": job_id,
        "duplicate": False,
        "transport": transport,
    }


def list_documents(limit: int, offset: int):
    return {
        "items": document_repository.list_all(limit, offset),
        "total": document_repository.count_all(),
        "limit": limit,
        "offset": offset,
    }


def detail(document_id: int):
    document = document_repository.get(document_id)
    if not document:
        raise LookupError("文档不存在")
    versions = document_repository.list_versions(document_id)
    if versions:
        versions[0]["chunks"] = document_repository.list_chunks(versions[0]["id"], 20)
    return {"document": document, "versions": versions}


def retry_job(job_id: str, owner_id: str):
    job = job_repository.get(job_id)
    if not job:
        raise LookupError("任务不存在")
    if job["status"] not in ("failed", "cancelled"):
        raise ValueError("只有失败或已取消的任务可以重试")
    payload = job.get("payload") or {}
    new_id = job_repository.create(owner_id, job["job_type"], payload)
    transport = enqueue_document_job(new_id)
    return {"job": job_repository.get(new_id), "transport": transport}
