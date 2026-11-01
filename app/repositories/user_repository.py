"""用户持久化操作。"""
from app.db import execute, query_all, query_one


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


def list_all(limit: int = 20, offset: int = 0, query: str = ""):
    sql = """SELECT id, username, email, role, status, created_at, last_login_at
             FROM users"""
    args = []
    if query.strip():
        sql += " WHERE username LIKE %s OR id LIKE %s"
        term = f"%{query.strip()}%"
        args.extend([term, term])
    sql += " ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s"
    args.extend([limit, offset])
    return query_all(sql, tuple(args))


def set_status(user_id: str, status: str) -> int:
    return execute("UPDATE users SET status = %s WHERE id = %s", (status, user_id))


def set_role(user_id: str, role: str) -> int:
    return execute("UPDATE users SET role = %s WHERE id = %s", (role, user_id))


def count_active_admins() -> int:
    row = query_one(
        "SELECT COUNT(*) AS total FROM users WHERE role = 'admin' AND status = 'active'"
    )
    return int(row["total"] if row else 0)
