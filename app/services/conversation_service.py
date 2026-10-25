"""会话服务：提供用户隔离的会话读写入口。"""
from app.repositories import conversation_repository
from app.services.user_service import ensure_active


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
    return conversation_repository.list_messages(conversation_id, user_id, limit)
