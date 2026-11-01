"""Best-effort audit logging that never breaks the business request."""
import logging

from app.repositories import audit_repository

log = logging.getLogger("ashore.audit")


def record(actor_id, action, target_type=None, target_id=None,
           request_id=None, ip=None, detail=None) -> None:
    try:
        audit_repository.record(
            actor_id, action, target_type, target_id, request_id, ip, detail,
        )
    except Exception as error:
        log.warning("audit write failed: %s", error)
