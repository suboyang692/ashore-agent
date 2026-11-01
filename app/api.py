"""FastAPI 服务 —— 把各 Agent 暴露成 HTTP 接口。

启动:
    uvicorn app.api:app --reload --port 8000
    或 python -m app.api
接口文档:
    http://127.0.0.1:8000/docs

接口一览:
    GET  /health              健康检查
    POST /chat                路由入口（答疑 / 出题 / 批改 / 规划），带 question_id 时视为提交作答
    POST /chat/stream         SSE 流式路由入口（答疑逐 token 返回）
    POST /quiz                直接出题
    POST /plan                直接生成复习计划
    GET  /questions/next      取下一道未做过的题（不返回答案）
    POST /submit              提交作答（按题型自动分流：客观题判分 / 主观题批改）
    GET  /profile/{user_id}   学情画像
    GET  /plan/{user_id}      最近一份复习计划
    GET  /kb/search           混合检索知识库
    GET  /cache/stats         缓存后端 / 命中率 / 知识库版本号

页面:
    GET  /ui/                 单页操作界面（web/index.html）
"""
import json
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import cache, rate_limit
from app.db import query_all, query_one
from app.grader_agent import grade_subjective
from app.planner_agent import DEFAULT_DAYS, make_plan
from app.practice import submit as submit_objective
from app.repositories import plan_repository
from app.question_types import is_subjective, normalize_question_type
from app.quiz_agent import generate_quiz
from app.retriever import cached_hybrid_search
from app.router_agent import public_question, route, stream_route
from app.config import (
    RATE_LIMIT_AGENT_PER_MIN,
    RATE_LIMIT_CHAT_PER_MIN,
    RATE_LIMIT_SEARCH_PER_MIN,
    RATE_LIMIT_SUBMIT_PER_MIN,
    REQUIRE_AUTH,
)
from app.observability import configure_logging, http_middleware, metrics_text
from app.repositories import audit_repository, user_repository
from app.security import decode_token
from app.services import (
    audit_service,
    auth_service,
    conversation_service,
    plan_service,
    practice_service,
)

app = FastAPI(
    title="研岸 Ashore API",
    version="1.0.0",
    description="考研数学多智能体备考助手：答疑 / 出题 / 批改 / 规划",
)
configure_logging()
app.middleware("http")(http_middleware)


WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if WEB_DIR.is_dir():
    app.mount("/ui", StaticFiles(directory=str(WEB_DIR), html=True), name="ui")


class ChatRequest(BaseModel):
    user_id: str = Field(default="default", description="用户标识")
    message: str = Field(description="用户消息；带 question_id 时视为考生作答内容")
    question_id: int | None = Field(default=None, description="配合批改使用，指定题目 id")
    conversation_id: int | None = Field(default=None, description="指定持久化会话；不传保持旧接口行为")


class QuizRequest(BaseModel):
    user_id: str = Field(default="default")
    knowledge_point: str = Field(default="", description="指定知识点；留空则按学情画像挑最薄弱的")


class PlanRequest(BaseModel):
    user_id: str = Field(default="default")
    days: int = Field(default=DEFAULT_DAYS, ge=1, le=30, description="计划天数")


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=6, max_length=64)
    email: str | None = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    username: str
    password: str


class SubmitRequest(BaseModel):
    user_id: str = Field(default="default")
    question_id: int
    answer: str


class UserStatusRequest(BaseModel):
    status: Literal["active", "disabled"]


class UserRoleRequest(BaseModel):
    role: Literal["student", "admin"]


def _resolve_user(requested: str, authorization: str | None,
                  require_token: bool = False) -> str:
    """Resolve and validate the acting user; admins may target other users."""
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Authorization 需为 Bearer <token>")
        payload = decode_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
        user = user_repository.get_by_id(user_id)
        if not user or user.get("status") != "active":
            raise HTTPException(status_code=401, detail="账号不存在或已被禁用")
        if not requested or requested == "default" or requested == user_id:
            return user_id
        if requested != user_id:
            if user.get("role") != "admin":
                raise HTTPException(status_code=403, detail="无权访问其他用户的数据")
            return requested
    if require_token or REQUIRE_AUTH:
        raise HTTPException(status_code=401, detail="请先登录")
    return requested


def _require_admin(user_id: str) -> dict:
    user = user_repository.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="账号不存在")
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


def _rate_limit(subject: str, scope: str, limit: int) -> None:
    allowed, retry_after = rate_limit.check(scope, subject, limit)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="请求过于频繁，请稍后重试",
            headers={"Retry-After": str(retry_after)},
        )


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _agent_error_message(error: Exception) -> str:
    """把供应商异常收敛成学生能理解、且不泄露内部结构的提示。"""
    text = str(error)
    lower = text.lower()
    if "arrearage" in lower or "overdue-payment" in lower or "access denied" in lower:
        return "模型服务暂时不可用：百炼账户余额不足或状态异常，请检查账户后重试。"
    if "timeout" in lower or "超时" in text:
        return "模型服务响应超时，请稍后重试。"
    if "rate limit" in lower or "429" in text:
        return "请求过于频繁，请稍后重试。"
    return "处理失败，请稍后重试。"


@app.post("/auth/register")
def register(req: RegisterRequest, request: Request):
    """注册并直接签发 Token。"""
    ip = _client_ip(request)
    _rate_limit(f"ip:{ip}", "register", 5)
    try:
        user_id = auth_service.register(req.username, req.password, req.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    user = user_repository.get_by_id(user_id)
    audit_service.record(
        user_id, "auth.register", "user", user_id,
        _request_id(request), ip, {"username": req.username},
    )
    return {"token": auth_service.issue_token(user_id),
            "user": auth_service.public_user(user)}


@app.post("/auth/login")
def login(req: LoginRequest, request: Request):
    """账号密码登录。"""
    ip = _client_ip(request)
    _rate_limit(f"ip:{ip}", "login", 10)
    try:
        user = auth_service.login(req.username, req.password)
    except PermissionError as e:
        audit_service.record(
            None, "auth.login_failed", "user", req.username,
            _request_id(request), ip, {"reason": str(e)},
        )
        raise HTTPException(status_code=401, detail=str(e))
    audit_service.record(
        user["id"], "auth.login", "user", user["id"],
        _request_id(request), ip,
    )
    return {"token": auth_service.issue_token(user["id"]),
            "user": auth_service.public_user(user)}


@app.get("/auth/me")
def me(authorization: str | None = Header(default=None)):
    """当前登录用户。"""
    user_id = _resolve_user("", authorization, require_token=True)
    user = user_repository.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return auth_service.public_user(user)


@app.get("/")
def root():
    """根路径：给出接口入口，避免直接访问出现 404。"""
    return {
        "name": "研岸 Ashore API",
        "version": app.version,
        "docs": "/docs",
        "ui": "/ui/",
        "endpoints": [
            "/chat", "/chat/stream", "/quiz", "/plan", "/questions/next",
            "/submit", "/profile/{user_id}", "/plan/{user_id}", "/kb/search",
            "/cache/stats", "/health", "/ready", "/metrics",
            "/attempts", "/mistakes", "/admin/users", "/admin/overview",
            "/admin/audit-logs",
        ],
    }


@app.get("/health")
def health():
    """健康检查。"""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness probe: database is required; cache may be in fallback mode."""
    try:
        query_one("SELECT 1 AS ok")
    except Exception as error:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": "error",
                     "error": type(error).__name__},
        )
    return {
        "status": "ready",
        "database": "ok",
        "cache_backend": cache.backend_name(),
        "kb_version": cache.kb_version(),
    }


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    """Prometheus text exposition; expose only on the internal network."""
    return metrics_text()


@app.get("/admin/overview")
def admin_overview(authorization: str | None = Header(default=None)):
    actor = _resolve_user("", authorization, require_token=True)
    _require_admin(actor)
    return {
        "users": query_one("SELECT COUNT(*) AS total FROM users")["total"],
        "questions": query_one("SELECT COUNT(*) AS total FROM questions")["total"],
        "conversations": query_one("SELECT COUNT(*) AS total FROM conversations")["total"],
        "attempts": query_one("SELECT COUNT(*) AS total FROM practice_attempts")["total"],
        "cache": cache.stats(),
    }


@app.get("/admin/users")
def admin_users(q: str = "", limit: int = 20, offset: int = 0,
                authorization: str | None = Header(default=None)):
    actor = _resolve_user("", authorization, require_token=True)
    _require_admin(actor)
    return {
        "items": user_repository.list_all(min(max(limit, 1), 100), max(offset, 0), q),
        "limit": min(max(limit, 1), 100),
        "offset": max(offset, 0),
    }


@app.get("/admin/audit-logs")
def admin_audit_logs(limit: int = 20, offset: int = 0,
                     authorization: str | None = Header(default=None)):
    actor = _resolve_user("", authorization, require_token=True)
    _require_admin(actor)
    page_size = min(max(limit, 1), 100)
    page_offset = max(offset, 0)
    return {
        "items": audit_repository.list_all(page_size, page_offset),
        "total": audit_repository.count_all(),
        "limit": page_size,
        "offset": page_offset,
    }


@app.patch("/admin/users/{user_id}/status")
def admin_set_user_status(user_id: str, req: UserStatusRequest, request: Request,
                          authorization: str | None = Header(default=None)):
    actor = _resolve_user("", authorization, require_token=True)
    _require_admin(actor)
    if user_id == actor:
        raise HTTPException(status_code=400, detail="不能修改自己的账号状态")
    target = user_repository.get_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.get("role") == "admin" and req.status == "disabled":
        if user_repository.count_active_admins() <= 1:
            raise HTTPException(status_code=400, detail="不能禁用最后一个管理员")
    user_repository.set_status(user_id, req.status)
    audit_service.record(
        actor, "admin.user_status", "user", user_id,
        _request_id(request), _client_ip(request),
        {"from": target.get("status"), "to": req.status},
    )
    return {"id": user_id, "status": req.status}


@app.patch("/admin/users/{user_id}/role")
def admin_set_user_role(user_id: str, req: UserRoleRequest, request: Request,
                        authorization: str | None = Header(default=None)):
    actor = _resolve_user("", authorization, require_token=True)
    _require_admin(actor)
    if user_id == actor:
        raise HTTPException(status_code=400, detail="不能修改自己的角色")
    target = user_repository.get_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.get("role") == "admin" and req.role != "admin":
        if user_repository.count_active_admins() <= 1:
            raise HTTPException(status_code=400, detail="不能降级最后一个管理员")
    user_repository.set_role(user_id, req.role)
    audit_service.record(
        actor, "admin.user_role", "user", user_id,
        _request_id(request), _client_ip(request),
        {"from": target.get("role"), "to": req.role},
    )
    return {"id": user_id, "role": req.role}


@app.get("/conversations")
def conversations(authorization: str | None = Header(default=None)):
    user_id = _resolve_user("", authorization, require_token=True)
    return {"items": conversation_service.list_conversations(user_id)}


@app.post("/conversations")
def create_conversation(authorization: str | None = Header(default=None)):
    user_id = _resolve_user("", authorization, require_token=True)
    conversation_id = conversation_service.start_conversation(user_id)
    return conversation_service.get_conversation(conversation_id, user_id)


@app.get("/conversations/{conversation_id}/messages")
def conversation_messages(conversation_id: int, authorization: str | None = Header(default=None)):
    user_id = _resolve_user("", authorization, require_token=True)
    try:
        return {"items": conversation_service.get_messages(conversation_id, user_id, limit=100)}
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error))


@app.delete("/conversations")
def clear_conversations(authorization: str | None = Header(default=None)):
    user_id = _resolve_user("", authorization, require_token=True)
    return {"deleted": conversation_service.clear_conversations(user_id)}


@app.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: int, authorization: str | None = Header(default=None)):
    user_id = _resolve_user("", authorization, require_token=True)
    try:
        return {"deleted": conversation_service.delete_conversation(conversation_id, user_id)}
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error))


@app.post("/chat")
def chat(req: ChatRequest, authorization: str | None = Header(default=None)):
    """路由入口：一句话交给路由 Agent 决定走答疑 / 出题 / 批改 / 规划。"""
    try:
        user_id = _resolve_user(req.user_id, authorization, require_token=True)
        _rate_limit(user_id, "chat", RATE_LIMIT_CHAT_PER_MIN)
        memory_key = user_id
        if req.conversation_id is not None:
            memory_key = conversation_service.restore_memory(req.conversation_id, user_id)
        if req.conversation_id is None:
            result = route(user_id, req.message, req.question_id)
        else:
            result = route(user_id, req.message, req.question_id, memory_key=memory_key)
        if req.conversation_id is not None:
            conversation_service.save_turn(req.conversation_id, user_id, req.message, result)
        return result
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print(f"[chat] {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=_agent_error_message(e))


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest, authorization: str | None = Header(default=None)):
    """流式答疑：SSE 输出 token、元信息、来源和最终结果。"""
    user_id = _resolve_user(req.user_id, authorization, require_token=True)
    _rate_limit(user_id, "chat", RATE_LIMIT_CHAT_PER_MIN)
    memory_key = user_id
    if req.conversation_id is not None:
        try:
            memory_key = conversation_service.restore_memory(req.conversation_id, user_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error))
    async def events():
        try:
            if req.conversation_id is None:
                stream = stream_route(user_id, req.message, req.question_id)
            else:
                stream = stream_route(user_id, req.message, req.question_id, memory_key=memory_key)
            async for event in stream:
                if event["type"] == "done" and req.conversation_id is not None:
                    conversation_service.save_turn(req.conversation_id, user_id, req.message, event["result"])
                yield _sse(event)
        except Exception as e:
            print(f"[chat/stream] {type(e).__name__}: {e}")
            yield _sse({"type": "error", "message": _agent_error_message(e)})
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/quiz")
def quiz(req: QuizRequest, authorization: str | None = Header(default=None)):
    """直接出题：返回本次新命制并入库的题目（不含答案）。"""
    try:
        user_id = _resolve_user(req.user_id, authorization, require_token=True)
        _rate_limit(user_id, "quiz", RATE_LIMIT_AGENT_PER_MIN)
        before = query_one("SELECT COALESCE(MAX(id), 0) AS m FROM questions")["m"]
        r = generate_quiz(user_id, req.knowledge_point)
    except Exception as e:
        print(f"[quiz] {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=_agent_error_message(e))
    rows = query_all("SELECT * FROM questions WHERE id > %s ORDER BY id", (before,))
    return {
        "knowledge_point": r["knowledge_point"],
        "saved": r["saved"],
        "questions": [public_question(x) for x in rows],
    }


@app.post("/plan")
def plan(req: PlanRequest, authorization: str | None = Header(default=None)):
    """直接生成复习计划。"""
    try:
        user_id = _resolve_user(req.user_id, authorization, require_token=True)
        _rate_limit(user_id, "plan", RATE_LIMIT_AGENT_PER_MIN)
        r = make_plan(user_id, req.days)
    except Exception as e:
        print(f"[plan] {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=_agent_error_message(e))
    return {
        "plan_id": r["plan_id"],
        "days": req.days,
        "summary": r["plan"]["summary"],
        "schedule": r["plan"]["days"],
    }


@app.get("/questions/next")
def next_question(user_id: str = "default", question_type: str = "",
                  knowledge_point: str = "",
                  authorization: str | None = Header(default=None)):
    """取一道该用户没做过的题（不返回答案与解析）。"""
    user_id = _resolve_user(user_id, authorization, require_token=True)
    _rate_limit(user_id, "question_next", RATE_LIMIT_SEARCH_PER_MIN)
    sql = """SELECT q.* FROM questions q
             LEFT JOIN answer_records a ON a.question_id = q.id AND a.user_id = %s
             WHERE a.id IS NULL"""
    args = [user_id]
    if question_type:
        try:
            question_type = normalize_question_type(question_type)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        sql += " AND q.question_type = %s"
        args.append(question_type)
    if knowledge_point.strip():
        sql += " AND q.knowledge_point = %s"
        args.append(knowledge_point.strip())
    q = query_one(sql + " ORDER BY RAND() LIMIT 1", args)
    if not q:
        raise HTTPException(status_code=404, detail="没有未做过的题目了")
    return public_question(q)


@app.post("/submit")
def submit(req: SubmitRequest, authorization: str | None = Header(default=None)):
    """提交作答：选择题/填空题走精确判分，解答题走批改 Agent。"""
    user_id = _resolve_user(req.user_id, authorization, require_token=True)
    _rate_limit(user_id, "submit", RATE_LIMIT_SUBMIT_PER_MIN)
    q = query_one("SELECT * FROM questions WHERE id=%s", (req.question_id,))
    if not q:
        raise HTTPException(status_code=404, detail=f"题目 {req.question_id} 不存在")

    if is_subjective(q):
        g = grade_subjective(user_id, q, req.answer)
        return {
            "type": "subjective",
            "attempt_id": g.get("attempt_id"),
            "score": g["score"],
            "mistake_type": g["mistake_type"],
            "comment": g["comment"],
            "suggestion": g["suggestion"],
            "standard_answer": q["answer"],
            "analysis": q["analysis"],
        }

    r = submit_objective(user_id, q, req.answer)
    return {
        "type": "objective",
        "attempt_id": r.get("attempt_id"),
        "correct": bool(r["correct"]),
        "mastery": r["mastery"],
        "standard_answer": q["answer"],
        "analysis": q["analysis"],
    }


@app.get("/attempts")
def list_attempts(user_id: str = "default", limit: int = 20, offset: int = 0,
                  authorization: str | None = Header(default=None)):
    """答题历史：按提交时间倒序分页。"""
    user_id = _resolve_user(user_id, authorization)
    return {"user_id": user_id,
            "items": practice_service.list_attempts(user_id, min(limit, 100), offset)}


@app.get("/attempts/{attempt_id}")
def attempt_detail(attempt_id: int, user_id: str = "default",
                   authorization: str | None = Header(default=None)):
    """单次作答详情：题目、得分与错因明细。"""
    user_id = _resolve_user(user_id, authorization)
    try:
        return practice_service.get_attempt(user_id, attempt_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/mistakes")
def list_mistakes(user_id: str = "default", knowledge_point: str = "",
                  mistake_type: str = "", limit: int = 20, offset: int = 0,
                  authorization: str | None = Header(default=None)):
    """错题本：按知识点或错因筛选。"""
    user_id = _resolve_user(user_id, authorization)
    return {"user_id": user_id, "items": practice_service.list_mistakes(
        user_id, knowledge_point or None, mistake_type or None, min(limit, 100), offset)}


@app.post("/plan-items/{item_id}/complete")
def complete_plan_item(item_id: int, user_id: str = "default",
                       authorization: str | None = Header(default=None)):
    """勾选完成一个复习计划项（幂等）。"""
    user_id = _resolve_user(user_id, authorization)
    try:
        return plan_service.complete_item(user_id, item_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/profile/{user_id}")
def profile(user_id: str, authorization: str | None = Header(default=None)):
    """学情画像：各知识点的练习次数、错误次数与掌握度。"""
    user_id = _resolve_user(user_id, authorization)
    rows = query_all(
        """SELECT knowledge_point, subject, total_count, wrong_count, mastery
           FROM user_mastery WHERE user_id = %s
           ORDER BY mastery ASC, wrong_count DESC""",
        (user_id,),
    )
    weak = [r["knowledge_point"] for r in rows if float(r["mastery"]) < 0.6]
    return {"user_id": user_id, "items": rows, "weak_points": weak}


@app.get("/plan/{user_id}")
def latest_plan(user_id: str, include_items: bool = False,
                authorization: str | None = Header(default=None)):
    """最近一份复习计划。

    include_items=true 时额外返回拆好的计划明细，前端可逐项展示和勾选完成。
    """
    user_id = _resolve_user(user_id, authorization)
    row = query_one(
        "SELECT * FROM review_plans WHERE user_id = %s ORDER BY id DESC LIMIT 1", (user_id,)
    )
    if not row:
        raise HTTPException(status_code=404, detail="该用户还没有复习计划")
    body = {
        "plan_id": row["id"],
        "days": row["days"],
        "summary": row["summary"],
        "schedule": json.loads(row["content"]),
        "created_at": row["created_at"],
    }
    if include_items:
        body["items"] = plan_repository.list_items(row["id"])
    return body


@app.get("/cache/stats")
def cache_stats(authorization: str | None = Header(default=None)):
    """缓存后端与命中率。backend 是 memory 就说明 Redis 没连上、已自动降级。"""
    actor = _resolve_user("", authorization, require_token=True)
    _require_admin(actor)
    return cache.stats()


@app.get("/kb/search")
def kb_search(q: str, top_k: int = 4,
              authorization: str | None = Header(default=None)):
    """混合检索知识库（向量 + BM25，RRF 融合）。"""
    user_id = _resolve_user("", authorization, require_token=True)
    _rate_limit(user_id, "kb_search", RATE_LIMIT_SEARCH_PER_MIN)
    hits = cached_hybrid_search(q, top_k=top_k)
    return {"query": q, "count": len(hits), "hits": hits}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
