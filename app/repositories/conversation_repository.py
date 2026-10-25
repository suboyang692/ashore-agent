"""会话和消息持久化操作。"""
from app.db import execute, query_all, query_one


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
        """SELECT * FROM conversations
           WHERE user_id = %s AND status <> 'deleted'
           ORDER BY updated_at DESC LIMIT %s OFFSET %s""",
        (user_id, limit, offset),
    )


def add_message(conversation_id: int, role: str, content: str, **metadata) -> int:
    return execute(
        """INSERT INTO conversation_messages
           (conversation_id, role, content, agent_name, tool_name,
            request_id, latency_ms, input_tokens, output_tokens)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            conversation_id, role, content,
            metadata.get("agent_name"), metadata.get("tool_name"),
            metadata.get("request_id"), metadata.get("latency_ms"),
            metadata.get("input_tokens"), metadata.get("output_tokens"),
        ),
    )


def list_messages(conversation_id: int, user_id: str, limit: int = 50):
    return query_all(
        """SELECT m.* FROM conversation_messages m
           JOIN conversations c ON c.id = m.conversation_id
           WHERE m.conversation_id = %s AND c.user_id = %s
           ORDER BY m.created_at ASC, m.id ASC LIMIT %s""",
        (conversation_id, user_id, limit),
    )
