"""用户服务：统一用户存在性与状态校验。"""
from app.repositories import user_repository


def ensure_active(user_id: str):
    user = user_repository.get_by_id(user_id)
    if not user:
        raise LookupError(f"用户 {user_id} 不存在")
    if user.get("status") != "active":
        raise PermissionError("用户已被禁用")
    return user


def ensure_default_user():
    user = user_repository.get_by_id("default")
    if user:
        return user
    user_repository.create("default", "default")
    return user_repository.get_by_id("default")
