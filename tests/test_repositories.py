"""Repository / Service 层契约测试：只验证 SQL 参数和用户隔离，不连接真实数据库。"""
from app.repositories import conversation_repository, practice_repository, user_repository
from app.services import conversation_service


def test_user_repository_passes_identity(monkeypatch):
    seen = {}
    monkeypatch.setattr(user_repository, "query_one", lambda sql, args: seen.update(args=args) or {"id": args[0], "status": "active"})
    assert user_repository.get_by_id("u-1")["id"] == "u-1"
    assert seen["args"] == ("u-1",)


def test_conversation_service_rejects_cross_user_access(monkeypatch):
    monkeypatch.setattr(conversation_service, "ensure_active", lambda user_id: {"id": user_id, "status": "active"})
    monkeypatch.setattr(conversation_repository, "get", lambda conversation_id, user_id: None)
    try:
        conversation_service.append_message(1, "u-1", "user", "hello")
    except LookupError as exc:
        assert "无权" in str(exc)
    else:
        raise AssertionError("cross-user conversation access must fail")


def test_practice_repository_writes_attempt(monkeypatch):
    seen = {}
    monkeypatch.setattr(practice_repository, "execute", lambda sql, args: seen.update(args=args) or 9)
    assert practice_repository.create_attempt("u-1", 3, "答案", "req-1") == 9
    assert seen["args"] == ("u-1", 3, "答案", "req-1")
