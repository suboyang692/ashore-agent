"""Append-only audit log persistence."""
import json

from app.db import execute, query_all, query_one


def record(actor_id, action, target_type=None, target_id=None,
           request_id=None, ip=None, detail=None) -> int:
    payload = json.dumps(detail, ensure_ascii=False) if detail is not None else None
    return execute(
        """INSERT INTO audit_logs
           (actor_id, action, target_type, target_id, request_id, ip, detail)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (actor_id, action, target_type, target_id, request_id, ip, payload),
    )


def list_all(limit: int = 20, offset: int = 0):
    return query_all(
        """SELECT a.id, a.actor_id, u.username AS actor_name, a.action,
                  a.target_type, a.target_id, a.request_id, a.ip, a.detail,
                  a.created_at
           FROM audit_logs a
           LEFT JOIN users u ON u.id = a.actor_id
           ORDER BY a.id DESC LIMIT %s OFFSET %s""",
        (limit, offset),
    )


def count_all() -> int:
    row = query_one("SELECT COUNT(*) AS total FROM audit_logs")
    return int(row["total"] if row else 0)
