"""会话服务：提供用户隔离的会话读写入口。"""
import json

from app import cache
from app.repositories import conversation_repository
from app.services.user_service import ensure_active

EMPTY_TITLE = "新会话"


def create_conversation(user_id: str, title: str = "新会话") -> int:
    ensure_active(user_id)
    return conversation_repository.create(user_id, title)


def append_message(conversation_id: int, user_id: str, role: str, content: str, **metadata) -> int:
    ensure_active(user_id)
    if not content.strip():
        raise ValueError("消息内容不能为空")
    if not conversation_repository.get(conversation_id, user_id):
        raise LookupError("会话不存在或无权访问")
    return conversation_repository.add_message(conversation_id, role, content, **metadata)


def get_messages(conversation_id: int, user_id: str, limit: int = 50):
    ensure_active(user_id)
    if not conversation_repository.get(conversation_id, user_id):
        raise LookupError("会话不存在或无权访问")
    rows = conversation_repository.list_messages(conversation_id, user_id, limit)
    for row in rows:
        if isinstance(row.get("response_data"), str):
            row["response_data"] = json.loads(row["response_data"])
    return rows


def memory_key(user_id: str, conversation_id: int) -> str:
    return f"{user_id}:conversation:{conversation_id}"


def restore_memory(conversation_id: int, user_id: str):
    get_conversation(conversation_id, user_id)
    key = memory_key(user_id, conversation_id)
    if not cache.session_load(key):
        rows = get_messages(conversation_id, user_id, limit=100)
        cache.session_save(key, [
            {"role": "human" if row["role"] == "user" else "ai", "content": row["content"]}
            for row in rows if row["role"] in ("user", "assistant")
        ])
    return key


def list_conversations(user_id: str):
    ensure_active(user_id)
    rows = conversation_repository.list_for_user(user_id, limit=100)
    empty = [row for row in rows
             if row.get("title") == EMPTY_TITLE and int(row.get("message_count", 0)) == 0]
    if len(empty) <= 1:
        return rows
    for duplicate in empty[1:]:
        cache.session_clear(memory_key(user_id, duplicate["id"]))
        conversation_repository.delete_for_user(duplicate["id"], user_id)
    duplicates = {row["id"] for row in empty[1:]}
    return [row for row in rows if row["id"] not in duplicates]


def start_conversation(user_id: str):
    """新建会话是幂等的：已有空白会话时复用它，不重复插入。"""
    rows = list_conversations(user_id)
    for row in rows:
        if row.get("title") == EMPTY_TITLE and int(row.get("message_count", 0)) == 0:
            return row["id"]
    return conversation_repository.create(user_id, EMPTY_TITLE)


def get_conversation(conversation_id: int, user_id: str):
    ensure_active(user_id)
    row = conversation_repository.get(conversation_id, user_id)
    if not row:
        raise LookupError("会话不存在或无权访问")
    return row


def save_turn(conversation_id: int, user_id: str, message: str, result: dict):
    conversation = get_conversation(conversation_id, user_id)
    conversation_repository.add_message(conversation_id, "user", message)
    conversation_repository.add_message(
        conversation_id, "assistant", result["reply"],
        response_data=json.dumps({"intent": result["intent"], "data": result["data"]}, ensure_ascii=False),
    )
    if conversation["title"] == "新会话":
        conversation_repository.rename(conversation_id, user_id, message[:60])
    conversation_repository.touch(conversation_id)


def clear_conversations(user_id: str):
    for conversation in list_conversations(user_id):
        cache.session_clear(memory_key(user_id, conversation["id"]))
    return conversation_repository.clear_for_user(user_id)


def delete_conversation(conversation_id: int, user_id: str):
    get_conversation(conversation_id, user_id)
    cache.session_clear(memory_key(user_id, conversation_id))
    return conversation_repository.delete_for_user(conversation_id, user_id)
