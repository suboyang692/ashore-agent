"""研岸 D8：FastAPI 服务 —— 把各 Agent 暴露成 HTTP 接口。

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

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import cache
from app.db import query_all, query_one
from app.grader_agent import grade_subjective
from app.planner_agent import DEFAULT_DAYS, make_plan
from app.practice import submit as submit_objective
from app.quiz_agent import generate_quiz
from app.retriever import cached_hybrid_search
from app.router_agent import public_question, route

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


class SubmitRequest(BaseModel):
    user_id: str = Field(default="default")
    question_id: int
    answer: str


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
            "/cache/stats", "/health",
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
        sql += " AND q.question_type = %s"
        args.append(question_type)
    q = query_one(sql + " ORDER BY RAND() LIMIT 1", args)
    if not q:
        raise HTTPException(status_code=404, detail="没有未做过的题目了")
    return public_question(q)


@app.post("/submit")
def submit(req: SubmitRequest):
    """提交作答：选择题/填空题走精确判分，解答题走批改 Agent。"""
    q = query_one("SELECT * FROM questions WHERE id=%s", (req.question_id,))
    if not q:
        raise HTTPException(status_code=404, detail=f"题目 {req.question_id} 不存在")

    if q["question_type"] == "解答":
        g = grade_subjective(req.user_id, q, req.answer)
        return {
            "type": "subjective",
            "score": g["score"],
            "mistake_type": g["mistake_type"],
            "comment": g["comment"],
            "suggestion": g["suggestion"],
            "standard_answer": q["answer"],
            "analysis": q["analysis"],
        }

    r = submit_objective(req.user_id, q, req.answer)
    return {
        "type": "objective",
        "correct": bool(r["correct"]),
        "mastery": r["mastery"],
        "standard_answer": q["answer"],
        "analysis": q["analysis"],
    }


@app.get("/profile/{user_id}")
def profile(user_id: str):
    """学情画像：各知识点的练习次数、错误次数与掌握度。"""
    rows = query_all(
        """SELECT knowledge_point, subject, total_count, wrong_count, mastery
           FROM user_mastery WHERE user_id = %s
           ORDER BY mastery ASC, wrong_count DESC""",
        (user_id,),
    )
    weak = [r["knowledge_point"] for r in rows if float(r["mastery"]) < 0.6]
    return {"user_id": user_id, "items": rows, "weak_points": weak}


@app.get("/plan/{user_id}")
def latest_plan(user_id: str):
    """最近一份复习计划。"""
    row = query_one(
        "SELECT * FROM review_plans WHERE user_id = %s ORDER BY id DESC LIMIT 1", (user_id,)
    )
    if not row:
        raise HTTPException(status_code=404, detail="该用户还没有复习计划")
    return {
        "plan_id": row["id"],
        "days": row["days"],
        "summary": row["summary"],
        "schedule": json.loads(row["content"]),
        "created_at": row["created_at"],
    }


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
