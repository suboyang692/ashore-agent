"""答题尝试与错因明细持久化操作。"""
from app.db import execute, query_all, query_one


def create_attempt(user_id: str, question_id: int, answer_text: str, request_id=None) -> int:
    return execute(
        """INSERT INTO practice_attempts
           (user_id, question_id, answer_text, request_id)
           VALUES (%s,%s,%s,%s)""",
        (user_id, question_id, answer_text, request_id),
    )


def get_attempt(attempt_id: int, user_id: str):
    return query_one(
        "SELECT * FROM practice_attempts WHERE id = %s AND user_id = %s",
        (attempt_id, user_id),
    )


def finish_attempt(attempt_id: int, score, is_correct, status="graded") -> int:
    return execute(
        """UPDATE practice_attempts
           SET score = %s, is_correct = %s, grading_status = %s, graded_at = NOW()
           WHERE id = %s""",
        (score, is_correct, status, attempt_id),
    )


def add_mistake(attempt_id: int, mistake_type: str, **detail) -> int:
    return execute(
        """INSERT INTO mistake_records
           (attempt_id, knowledge_point, mistake_type, original_text, reason, correct_method)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (
            attempt_id, detail.get("knowledge_point"), mistake_type,
            detail.get("original_text"), detail.get("reason"),
            detail.get("correct_method"),
        ),
    )


def list_attempts(user_id: str, limit: int = 20, offset: int = 0):
    return query_all(
        """SELECT a.*, q.knowledge_point, q.question_type
           FROM practice_attempts a JOIN questions q ON q.id = a.question_id
           WHERE a.user_id = %s ORDER BY a.submitted_at DESC LIMIT %s OFFSET %s""",
        (user_id, limit, offset),
    )


def get_attempt_detail(attempt_id: int, user_id: str):
    """单次作答详情：题目、得分、错因明细一起返回。"""
    attempt = query_one(
        """SELECT a.*, q.stem, q.knowledge_point, q.question_type,
                  q.answer AS standard_answer, q.analysis
           FROM practice_attempts a JOIN questions q ON q.id = a.question_id
           WHERE a.id = %s AND a.user_id = %s""",
        (attempt_id, user_id),
    )
    if not attempt:
        return None
    attempt["mistakes"] = query_all(
        "SELECT * FROM mistake_records WHERE attempt_id = %s ORDER BY id",
        (attempt_id,),
    )
    return attempt


def list_mistakes(user_id: str, knowledge_point=None, mistake_type=None,
                  limit: int = 20, offset: int = 0):
    sql = """SELECT m.*, a.question_id, a.score, a.submitted_at, q.stem
             FROM mistake_records m
             JOIN practice_attempts a ON a.id = m.attempt_id
             JOIN questions q ON q.id = a.question_id
             WHERE a.user_id = %s"""
    args = [user_id]
    if knowledge_point:
        sql += " AND m.knowledge_point = %s"
        args.append(knowledge_point)
    if mistake_type:
        sql += " AND m.mistake_type = %s"
        args.append(mistake_type)
    sql += " ORDER BY m.id DESC LIMIT %s OFFSET %s"
    args += [limit, offset]
    return query_all(sql, args)
