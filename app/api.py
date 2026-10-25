"""FastAPI 服务 —— 把各 Agent 暴露成 HTTP 接口。

启动:
    uvicorn app.api:app --reload --port 8000
    或 python -m app.api
接口文档:
    http://127.0.0.1:8000/docs

接口一览:
    GET  /health              健康检查
    POST /chat                路由入口（答疑 / 出题 / 批改 / 规划），带 question_id 时视为提交作答
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

from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import cache
from app.db import query_all, query_one
from app.grader_agent import grade_subjective
from app.planner_agent import DEFAULT_DAYS, make_plan
from app.practice import submit as submit_objective
from app.repositories import plan_repository
from app.question_types import is_subjective, normalize_question_type
from app.quiz_agent import generate_quiz
from app.retriever import cached_hybrid_search
from app.router_agent import public_question, route
from app.config import REQUIRE_AUTH
from app.repositories import user_repository
from app.security import decode_token
from app.services import auth_service, plan_service, practice_service

app = FastAPI(
    title="研岸 Ashore API",
    version="1.0.0",
    description="考研数学多智能体备考助手：答疑 / 出题 / 批改 / 规划",
)


WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if WEB_DIR.is_dir():
    app.mount("/ui", StaticFiles(directory=str(WEB_DIR), html=True), name="ui")


class ChatRequest(BaseModel):
    user_id: str = Field(default="default", description="用户标识")
    message: str = Field(description="用户消息；带 question_id 时视为考生作答内容")
    question_id: int | None = Field(default=None, description="配合批改使用，指定题目 id")


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


def _resolve_user(requested: str, authorization: str | None,
                  require_token: bool = False) -> str:
    """有 Token 就以 Token 为准；没开强制登录时兼容旧 user_id 参数。"""
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Authorization 需为 Bearer <token>")
        payload = decode_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
        user_id = payload.get("sub")
        if requested and requested != user_id:
            raise HTTPException(status_code=403, detail="无权访问其他用户的数据")
        return user_id
    if require_token or REQUIRE_AUTH:
        raise HTTPException(status_code=401, detail="请先登录")
    return requested


@app.post("/auth/register")
def register(req: RegisterRequest):
    """注册并直接签发 Token。"""
    try:
        user_id = auth_service.register(req.username, req.password, req.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    user = user_repository.get_by_id(user_id)
    return {"token": auth_service.issue_token(user_id),
            "user": auth_service.public_user(user)}


@app.post("/auth/login")
def login(req: LoginRequest):
    """账号密码登录。"""
    try:
        user = auth_service.login(req.username, req.password)
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
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
            "/chat", "/quiz", "/plan", "/questions/next",
            "/submit", "/profile/{user_id}", "/plan/{user_id}", "/kb/search",
            "/cache/stats", "/health", "/attempts", "/mistakes",
        ],
    }


@app.get("/health")
def health():
    """健康检查。"""
    return {"status": "ok"}


@app.post("/chat")
def chat(req: ChatRequest):
    """路由入口：一句话交给路由 Agent 决定走答疑 / 出题 / 批改 / 规划。"""
    try:
        return route(req.user_id, req.message, req.question_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理失败：{e}")


@app.post("/quiz")
def quiz(req: QuizRequest):
    """直接出题：返回本次新命制并入库的题目（不含答案）。"""
    try:
        before = query_one("SELECT COALESCE(MAX(id), 0) AS m FROM questions")["m"]
        r = generate_quiz(req.user_id, req.knowledge_point)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"出题失败：{e}")
    rows = query_all("SELECT * FROM questions WHERE id > %s ORDER BY id", (before,))
    return {
        "knowledge_point": r["knowledge_point"],
        "saved": r["saved"],
        "questions": [public_question(x) for x in rows],
    }


@app.post("/plan")
def plan(req: PlanRequest):
    """直接生成复习计划。"""
    try:
        r = make_plan(req.user_id, req.days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"规划失败：{e}")
    return {
        "plan_id": r["plan_id"],
        "days": req.days,
        "summary": r["plan"]["summary"],
        "schedule": r["plan"]["days"],
    }


@app.get("/questions/next")
def next_question(user_id: str = "default", question_type: str = ""):
    """取一道该用户没做过的题（不返回答案与解析）。"""
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
    q = query_one(sql + " ORDER BY RAND() LIMIT 1", args)
    if not q:
        raise HTTPException(status_code=404, detail="没有未做过的题目了")
    return public_question(q)


@app.post("/submit")
def submit(req: SubmitRequest, authorization: str | None = Header(default=None)):
    """提交作答：选择题/填空题走精确判分，解答题走批改 Agent。"""
    user_id = _resolve_user(req.user_id, authorization)
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
def cache_stats():
    """缓存后端与命中率。backend 是 memory 就说明 Redis 没连上、已自动降级。"""
    return cache.stats()


@app.get("/kb/search")
def kb_search(q: str, top_k: int = 4):
    """混合检索知识库（向量 + BM25，RRF 融合）。"""
    hits = cached_hybrid_search(q, top_k=top_k)
    return {"query": q, "count": len(hits), "hits": hits}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
