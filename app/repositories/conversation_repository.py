"""会话和消息持久化操作。"""
from app.db import conn_ctx, execute, query_all, query_one


def create(user_id: str, title: str = "新会话") -> int:
    return execute(
        "INSERT INTO conversations (user_id, title) VALUES (%s, %s)",
        (user_id, title),
    )


def get(conversation_id: int, user_id: str):
    return query_one(
        """SELECT * FROM conversations
           WHERE id = %s AND user_id = %s AND status <> 'deleted'""",
        (conversation_id, user_id),
    )


def list_for_user(user_id: str, limit: int = 20, offset: int = 0):
    return query_all(
        """SELECT c.*,
                  (SELECT COUNT(*) FROM conversation_messages m
                   WHERE m.conversation_id = c.id) AS message_count
           FROM conversations c
           WHERE c.user_id = %s AND c.status <> 'deleted'
           ORDER BY c.updated_at DESC LIMIT %s OFFSET %s""",
        (user_id, limit, offset),
    )


def rename(conversation_id: int, user_id: str, title: str):
    return execute(
        "UPDATE conversations SET title = %s WHERE id = %s AND user_id = %s AND status <> 'deleted'",
        (title, conversation_id, user_id),
    )


def touch(conversation_id: int):
    return execute("UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = %s", (conversation_id,))


def clear_for_user(user_id: str):
    with conn_ctx() as conn, conn.cursor() as cur:
        cur.execute("DELETE m FROM conversation_messages m JOIN conversations c ON c.id = m.conversation_id WHERE c.user_id = %s", (user_id,))
        cur.execute("DELETE FROM conversations WHERE user_id = %s", (user_id,))
        return cur.rowcount


def delete_for_user(conversation_id: int, user_id: str):
    with conn_ctx() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE m FROM conversation_messages m JOIN conversations c ON c.id = m.conversation_id "
            "WHERE m.conversation_id = %s AND c.user_id = %s",
            (conversation_id, user_id),
        )
        cur.execute(
            "DELETE FROM conversations WHERE id = %s AND user_id = %s",
            (conversation_id, user_id),
        )
        return cur.rowcount


def add_message(conversation_id: int, role: str, content: str, **metadata) -> int:
    return execute(
        """INSERT INTO conversation_messages
           (conversation_id, role, content, agent_name, tool_name,
            request_id, latency_ms, input_tokens, output_tokens, response_data)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            conversation_id, role, content,
            metadata.get("agent_name"), metadata.get("tool_name"),
            metadata.get("request_id"), metadata.get("latency_ms"),
            metadata.get("input_tokens"), metadata.get("output_tokens"), metadata.get("response_data"),
        ),
    )


def list_messages(conversation_id: int, user_id: str, limit: int = 50):
    rows = query_all(
        """SELECT m.* FROM conversation_messages m
           JOIN conversations c ON c.id = m.conversation_id
           WHERE m.conversation_id = %s AND c.user_id = %s AND c.status <> 'deleted'
           ORDER BY m.created_at DESC, m.id DESC LIMIT %s""",
        (conversation_id, user_id, limit),
    )
    return list(reversed(rows))
