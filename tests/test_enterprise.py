"""Enterprise guardrails: RBAC, rate limiting, request IDs and metrics."""
from fastapi.testclient import TestClient

from app import api, rate_limit
from app.observability import reset_metrics
from app.security import create_token


def _user(user_id: str, role: str = "student", status: str = "active"):
    return {
        "id": user_id, "username": user_id, "email": None,
        "role": role, "status": status,
    }


def test_rate_limit_blocks_after_limit():
    assert rate_limit.check("chat", "u-1", 2)[0] is True
    assert rate_limit.check("chat", "u-1", 2)[0] is True
    allowed, retry_after = rate_limit.check("chat", "u-1", 2)
    assert allowed is False
    assert retry_after > 0


def test_disabled_account_token_is_rejected(monkeypatch):
    monkeypatch.setattr(api.user_repository, "get_by_id", lambda uid: _user(uid, status="disabled"))
    client = TestClient(api.app, headers={"Authorization": f"Bearer {create_token('u-1')}"})
    assert client.get("/attempts").status_code == 401


def test_admin_can_list_users(monkeypatch):
    monkeypatch.setattr(
        api.user_repository, "get_by_id",
        lambda uid: _user(uid, role="admin" if uid == "admin-1" else "student"),
    )
    monkeypatch.setattr(
        api.user_repository, "list_all",
        lambda limit, offset, query: [_user("student-1")],
    )
    client = TestClient(api.app, headers={"Authorization": f"Bearer {create_token('admin-1')}"})
    response = client.get("/admin/users")
    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "student-1"


def test_student_cannot_access_admin(monkeypatch):
    monkeypatch.setattr(api.user_repository, "get_by_id", lambda uid: _user(uid))
    client = TestClient(api.app, headers={"Authorization": f"Bearer {create_token('student-1')}"})
    assert client.get("/admin/users").status_code == 403


def test_admin_cannot_disable_self(monkeypatch):
    monkeypatch.setattr(api.user_repository, "get_by_id", lambda uid: _user(uid, role="admin"))
    client = TestClient(api.app, headers={"Authorization": f"Bearer {create_token('admin-1')}"})
    response = client.patch("/admin/users/admin-1/status", json={"status": "disabled"})
    assert response.status_code == 400


def test_admin_status_change_writes_audit(monkeypatch):
    monkeypatch.setattr(
        api.user_repository, "get_by_id",
        lambda uid: _user(uid, role="admin" if uid == "admin-1" else "student"),
    )
    monkeypatch.setattr(api.user_repository, "set_status", lambda uid, status: 1)
    events = []
    monkeypatch.setattr(
        api.audit_service, "record",
        lambda *args, **kwargs: events.append((args, kwargs)),
    )
    client = TestClient(api.app, headers={"Authorization": f"Bearer {create_token('admin-1')}"})
    response = client.patch("/admin/users/student-1/status", json={"status": "disabled"})
    assert response.status_code == 200
    assert events[0][0][1] == "admin.user_status"
    assert events[0][0][3] == "student-1"


def test_admin_can_list_audit_logs(monkeypatch):
    monkeypatch.setattr(
        api.user_repository, "get_by_id",
        lambda uid: _user(uid, role="admin" if uid == "admin-1" else "student"),
    )
    monkeypatch.setattr(
        api.audit_repository, "list_all",
        lambda limit, offset: [{
            "id": 1, "actor_id": "admin-1", "actor_name": "admin",
            "action": "admin.user_status", "target_type": "user",
            "target_id": "student-1", "request_id": "trace-1",
            "ip": "127.0.0.1", "detail": {"to": "disabled"},
            "created_at": "2026-11-01T12:00:00",
        }],
    )
    monkeypatch.setattr(api.audit_repository, "count_all", lambda: 1)
    client = TestClient(api.app, headers={"Authorization": f"Bearer {create_token('admin-1')}"})
    response = client.get("/admin/audit-logs")
    assert response.status_code == 200
    assert response.json()["items"][0]["action"] == "admin.user_status"
    assert response.json()["total"] == 1


def test_request_id_and_metrics_exposed():
    reset_metrics()
    client = TestClient(api.app)
    response = client.get("/health", headers={"X-Request-ID": "trace-test-1"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "trace-test-1"
    metrics = client.get("/metrics").text
    assert "ashore_http_requests_total" in metrics
    assert 'route="/health"' in metrics
