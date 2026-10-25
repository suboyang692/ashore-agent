"""答题历史与错题本查询服务。"""
from app.repositories import practice_repository


def list_attempts(user_id: str, limit: int = 20, offset: int = 0):
    return practice_repository.list_attempts(user_id, limit, offset)


def get_attempt(user_id: str, attempt_id: int):
    detail = practice_repository.get_attempt_detail(attempt_id, user_id)
    if not detail:
        raise LookupError("答题记录不存在或无权访问")
    return detail


def list_mistakes(user_id: str, knowledge_point=None, mistake_type=None,
                  limit: int = 20, offset: int = 0):
    return practice_repository.list_mistakes(
        user_id, knowledge_point, mistake_type, limit, offset
    )
