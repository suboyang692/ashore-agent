# 研岸 Ashore · 考研多智能体问答与学情评测系统

考研多智能体备考助手：6 类 Agent 协作完成资料问答、变式出题、作答批改与复习规划，
回答强制引用原文出处，以 MySQL + 向量检索支撑「学-练-测-评」闭环。

## 目标 Agent（规划）
路由 Router -> 检索 Retriever -> 答疑 QA -> 出题 QuizGen -> 批改 Grader -> 规划 Planner

## D1 已完成
- [x] 目录骨架
- [x] MySQL 建库建表（题库/答题记录/学情画像/评测标注）
- [x] LLM 客户端封装 + 第一个 Agent（Function Calling demo）

## 快速开始（D1）
```bash
# 1. 配置
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # 填入 DASHSCOPE_API_KEY 和 MYSQL_PASSWORD

# 2. 建库
python db/init_db.py

# 3. 跑通第一个 Agent
python -m app.agent_demo
```
