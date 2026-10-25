"""认证：密码哈希、JWT 校验与接口边界。"""
import pytest

from app.security import create_token, decode_token, hash_password, verify_password


def test_password_hash_roundtrip():
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert verify_password("secret123", hashed)
    assert not verify_password("wrong", hashed)


def test_verify_rejects_empty_hash():
    assert not verify_password("x", "")


def test_token_roundtrip():
    token = create_token("u-1")
    assert decode_token(token)["sub"] == "u-1"


def test_token_rejects_tampering():
    token = create_token("u-1")
    parts = token.split(".")
    parts[1] = parts[1][:-2] + "aa"
    assert decode_token(".".join(parts)) is None


def test_token_rejects_expired():
    assert decode_token(create_token("u-1", ttl=-1)) is None


def test_token_rejects_garbage():
    assert decode_token("not-a-token") is None
    assert decode_token("") is None


pytest.importorskip("httpx", reason="FastAPI TestClient 需要 httpx")


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app import api
    return TestClient(api.app)


def test_register_returns_token_and_hides_hash(client, monkeypatch):
    from app import api
    monkeypatch.setattr(api.auth_service, "register", lambda u, p, e: "new-id")
    monkeypatch.setattr(api.user_repository, "get_by_id",
                        lambda uid: {"id": uid, "username": "bob", "email": None,
                                     "role": "student", "status": "active",
                                     "password_hash": "hidden"})
    body = client.post("/auth/register", json={"username": "bob", "password": "secret123"}).json()
    assert body["user"]["id"] == "new-id"
    assert "password_hash" not in body["user"]
    assert decode_token(body["token"])["sub"] == "new-id"


def test_register_duplicate_returns_400(client, monkeypatch):
    from app import api

    def boom(u, p, e):
        raise ValueError("用户名已存在")

    monkeypatch.setattr(api.auth_service, "register", boom)
    assert client.post("/auth/register", json={"username": "bob", "password": "secret123"}).status_code == 400


def test_login_bad_password_returns_401(client, monkeypatch):
    from app import api

    def boom(u, p):
        raise PermissionError("用户名或密码错误")

    monkeypatch.setattr(api.auth_service, "login", boom)
    assert client.post("/auth/login", json={"username": "bob", "password": "x"}).status_code == 401


def test_me_requires_token(client):
    assert client.get("/auth/me").status_code == 401


def test_me_returns_current_user(client, monkeypatch):
    from app import api
    monkeypatch.setattr(api.user_repository, "get_by_id",
                        lambda uid: {"id": uid, "username": "bob", "email": None,
                                     "role": "student", "status": "active"})
    token = create_token("u-1")
    body = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert body["id"] == "u-1"


def test_token_cannot_read_other_users_data(client):
    token = create_token("u-1")
    r = client.get("/attempts?user_id=u-2", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_invalid_token_returns_401(client):
    r = client.get("/attempts", headers={"Authorization": "Bearer bad.token.here"})
    assert r.status_code == 401
