"""Async job persistence."""
import json
from uuid import uuid4

from app.db import execute, query_all, query_one


def _decode(row):
    if not row:
        return row
    for key in ("payload", "result"):
        value = row.get(key)
        if isinstance(value, str):
            try:
                row[key] = json.loads(value)
            except (TypeError, ValueError):
                pass
    return row


def create(user_id, job_type, payload) -> str:
    job_id = uuid4().hex
    execute(
        """INSERT INTO jobs (id, user_id, job_type, status, progress, payload)
           VALUES (%s,%s,%s,'pending',0,%s)""",
        (job_id, user_id, job_type, json.dumps(payload, ensure_ascii=False)),
    )
    return job_id


def get(job_id: str):
    return _decode(query_one("SELECT * FROM jobs WHERE id = %s", (job_id,)))


def list_all(status: str = "", limit: int = 20, offset: int = 0):
    sql = "SELECT * FROM jobs"
    args = []
    if status:
        sql += " WHERE status = %s"
        args.append(status)
    sql += " ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s"
    args.extend([limit, offset])
    return [_decode(row) for row in query_all(sql, tuple(args))]


def count_all(status: str = "") -> int:
    if status:
        row = query_one("SELECT COUNT(*) AS total FROM jobs WHERE status=%s", (status,))
    else:
        row = query_one("SELECT COUNT(*) AS total FROM jobs")
    return int(row["total"] if row else 0)


def mark_running(job_id: str) -> int:
    return execute(
        """UPDATE jobs SET status='running', progress=5,
                  started_at=NOW(), error_message=NULL
           WHERE id=%s""",
        (job_id,),
    )


def update_progress(job_id: str, progress: int) -> int:
    return execute(
        "UPDATE jobs SET progress=%s WHERE id=%s",
        (max(0, min(int(progress), 99)), job_id),
    )


def mark_success(job_id: str, result: dict) -> int:
    return execute(
        """UPDATE jobs SET status='success', progress=100, result=%s,
                  error_message=NULL, finished_at=NOW()
           WHERE id=%s""",
        (json.dumps(result, ensure_ascii=False), job_id),
    )


def mark_failed(job_id: str, message: str) -> int:
    return execute(
        """UPDATE jobs SET status='failed', error_message=%s, finished_at=NOW()
           WHERE id=%s""",
        ((message or "unknown error")[:2000], job_id),
    )
