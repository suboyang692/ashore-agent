"""注册、登录与令牌签发。"""
from uuid import uuid4

from app.repositories import user_repository
from app.security import create_token, hash_password, verify_password


def register(username: str, password: str, email: str = None) -> str:
    username = username.strip()
    if len(username) < 2:
        raise ValueError("用户名至少 2 个字符")
    if len(password) < 6:
        raise ValueError("密码至少 6 位")
    if user_repository.get_by_username(username):
        raise ValueError("用户名已存在")
    user_id = uuid4().hex
    user_repository.create(
        user_id, username, email=email, password_hash=hash_password(password)
    )
    return user_id


def login(username: str, password: str) -> dict:
    user = user_repository.get_by_username(username.strip())
    if not user or not verify_password(password, user.get("password_hash")):
        raise PermissionError("用户名或密码错误")
    if user.get("status") != "active":
        raise PermissionError("账号已被禁用")
    user_repository.touch_login(user["id"])
    return user


def issue_token(user_id: str) -> str:
    return create_token(user_id)


def public_user(user: dict) -> dict:
    """对外返回的用户信息，绝不带 password_hash。"""
    return {
        "id": user["id"],
        "username": user["username"],
        "email": user.get("email"),
        "role": user.get("role"),
        "status": user.get("status"),
    }
