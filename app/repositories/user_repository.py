"""用户持久化操作。"""
from app.db import execute, query_one


def get_by_id(user_id: str):
    return query_one("SELECT * FROM users WHERE id = %s", (user_id,))


def get_by_username(username: str):
    return query_one("SELECT * FROM users WHERE username = %s", (username,))


def create(user_id: str, username: str, role: str = "student",
           email: str = None, password_hash: str = None) -> int:
    return execute(
        """INSERT INTO users (id, username, role, status, email, password_hash)
           VALUES (%s, %s, %s, 'active', %s, %s)""",
        (user_id, username, role, email, password_hash),
    )


def touch_login(user_id: str) -> int:
    return execute("UPDATE users SET last_login_at = NOW() WHERE id = %s", (user_id,))
