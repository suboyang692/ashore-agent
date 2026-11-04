"""Document upload, versioning and ingestion worker tests."""
from pathlib import Path

from fastapi.testclient import TestClient

from app import api, worker
from app.repositories import document_repository, job_repository
from app.services import document_service
from app.security import create_token


def _admin(uid):
    return {"id": uid, "username": "admin", "email": None,
            "role": "admin", "status": "active"}


def test_upload_creates_document_version_and_job(monkeypatch, tmp_path):
    monkeypatch.setattr(document_service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(document_repository, "get_by_hash", lambda file_hash: None)
    monkeypatch.setattr(document_repository, "create", lambda *args: 11)
    monkeypatch.setattr(document_repository, "create_version", lambda *args: 12)
    monkeypatch.setattr(
        document_repository, "get",
        lambda document_id: {"id": document_id, "status": "processing",
                             "title": "定积分", "file_name": "定积分.md"},
    )
    jobs = []
    monkeypatch.setattr(
        job_repository, "create",
        lambda owner_id, job_type, payload: jobs.append((owner_id, job_type, payload)) or "job-1",
    )
    monkeypatch.setattr(document_service, "enqueue_document_job", lambda job_id: "thread")

    result = document_service.upload("admin-1", "定积分.md", b"# test", "定积分")

    assert result["job_id"] == "job-1"
    assert result["duplicate"] is False
    assert result["transport"] == "thread"
    assert jobs[0][2]["document_id"] == 11
    assert len(list(tmp_path.iterdir())) == 1


def test_duplicate_upload_does_not_create_job(monkeypatch, tmp_path):
    monkeypatch.setattr(document_service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(
        document_repository, "get_by_hash",
        lambda file_hash: {"id": 3, "status": "ready", "title": "已存在"},
    )
    called = []
    monkeypatch.setattr(job_repository, "create", lambda *args: called.append(args))

    result = document_service.upload("admin-1", "lesson.md", b"# test")

    assert result["duplicate"] is True
    assert result["job_id"] is None
    assert called == []


def test_worker_indexes_chunks_and_marks_success(monkeypatch, tmp_path):
    path = tmp_path / "lesson.md"
    path.write_text("<!-- page: 1 -->\n定积分换元法", encoding="utf-8")
    updates = []
    monkeypatch.setattr(job_repository, "get", lambda job_id: {
        "id": job_id, "payload": {
            "document_id": 7, "version_id": 8,
            "path": str(path), "source_name": "定积分讲义.md",
        },
    })
    monkeypatch.setattr(job_repository, "mark_running", lambda job_id: updates.append(("running", job_id)))
    monkeypatch.setattr(job_repository, "update_progress", lambda job_id, value: None)
    monkeypatch.setattr(job_repository, "mark_success", lambda job_id, result: updates.append(("success", result)))
    monkeypatch.setattr(job_repository, "mark_failed", lambda job_id, message: updates.append(("failed", message)))
    monkeypatch.setattr(worker, "_safe_path", lambda raw: path)
    monkeypatch.setattr(worker, "read_file", lambda target: target.read_text(encoding="utf-8"))
    monkeypatch.setattr(worker, "embed_texts", lambda docs: [[0.1, 0.2] for _ in docs])
    monkeypatch.setattr(worker.cache, "bump_kb_version", lambda: 1)
    monkeypatch.setattr(document_repository, "update_status", lambda *args: None)
    monkeypatch.setattr(document_repository, "update_version_status", lambda *args: None)
    monkeypatch.setattr(document_repository, "add_chunks", lambda version_id, chunks: len(chunks))

    class FakeCollection:
        def __init__(self):
            self.deleted = False
            self.upserted = None

        def delete(self, where):
            self.deleted = where

        def upsert(self, **kwargs):
            self.upserted = kwargs

    collection = FakeCollection()
    monkeypatch.setattr(worker, "get_collection", lambda: collection)

    result = worker.process_document_job("job-1")

    assert result["chunks"] == 1
    assert updates[0][0] == "running"
    assert updates[-1][0] == "success"
    assert collection.deleted == {"document_id": "7"}
    assert collection.upserted["metadatas"][0]["source"] == "定积分讲义.md"


def test_admin_upload_endpoint(monkeypatch):
    monkeypatch.setattr(api.user_repository, "get_by_id", _admin)
    monkeypatch.setattr(api.audit_service, "record", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        api.document_service, "upload",
        lambda actor, file_name, content, title: {
            "document": {"id": 1, "title": title or Path(file_name).stem},
            "job_id": "job-1", "duplicate": False, "transport": "thread",
        },
    )
    client = TestClient(
        api.app, headers={"Authorization": f"Bearer {create_token('admin-1')}"},
    )
    response = client.post(
        "/admin/documents/upload",
        files={"file": ("lesson.md", b"# test", "text/markdown")},
        data={"title": "测试讲义"},
    )
    assert response.status_code == 200
    assert response.json()["job_id"] == "job-1"
