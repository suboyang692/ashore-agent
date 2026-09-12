# 研岸 Ashore · 考研数学多智能体备考助手

面向考研数学的 Agent 应用：答疑、出题、批改、规划由独立 Agent 承担，共享同一套题库与学情数据。
知识来自教材讲义切片，回答强制附引用出处；每次作答都会回写学情画像，驱动后续的薄弱点出题与
复习计划，形成「学 - 练 - 测 - 评 - 规」闭环。

## 核心能力

| 能力 | 实现 | 说明 |
|---|---|---|
| 答疑 | `app/graph_agent.py` | LangGraph 状态图编排的 ReAct 循环，自主调用知识库检索工具，基于讲义片段作答并标注来源；检索不到时明确回答「讲义中未涵盖」，不硬编 |
| 出题 | `app/quiz_agent.py` | 依据学情画像定位最薄弱知识点，命制变式题（结构化输出），入库前对答案做规范化与校验，避免答案格式导致判分失效 |
| 批改 | `app/grader_agent.py` | 主观题按 7 类错因（方法误用 / 审题错误 / 知识点不熟 / 计算错误 / 结论跳跃 / 表述不规范 / 无错误）结构化评分，输出错因、评语与改进建议并落库 |
| 规划 | `app/planner_agent.py` | 读取学情画像与题库缺口，生成 N 天复习计划（逐日知识点、题量、依据）并落库 |
| 检索 | `app/retriever.py` | ChromaDB 向量召回 + BM25 关键词召回，RRF 按排名融合（早期版本直接拼接导致 BM25 结果被截断，故改为 RRF） |
| 练习 | `app/practice.py` | 客观题抽题、判分、落库、学情掌握度更新 |

## 技术栈

Python 3.10 · LangGraph · LangChain · Qwen（DashScope OpenAI 兼容模式）· ChromaDB ·
rank-bm25 + jieba · MySQL · pdfplumber · pytest

## 目录结构

```
ashore/
├── app/
│   ├── config.py          # 从 .env 集中读取配置
│   ├── llm.py             # OpenAI 兼容客户端封装（原生 SDK + Function Calling 演示）
│   ├── db.py              # MySQL 连接与查询封装
│   ├── embedding.py       # DashScope Embedding 封装
│   ├── ingest.py          # 讲义切片 + 向量化入库（ChromaDB）
│   ├── retriever.py       # 向量检索 / BM25 检索 / RRF 混合检索
│   ├── practice.py        # 客观题练习闭环：抽题 - 判分 - 落库 - 学情画像
│   ├── graph_agent.py     # 答疑 Agent（LangGraph 状态图 + 检索工具）
│   ├── quiz_agent.py      # 出题 Agent（薄弱知识点 -> 变式题 -> 入库）
│   ├── grader_agent.py    # 批改 Agent（错因分类 + 评分 + 落库）
│   ├── planner_agent.py   # 规划 Agent（学情画像 -> 复习计划 -> 落库）
│   ├── qa_agent.py        # 答疑 Agent 的手写循环版本（保留用于对照）
│   ├── agent_demo.py      # 最小 Function Calling 演示
│   ├── inspect_db.py      # 数据自检：查看 MySQL 各表真实内容
│   └── inspect_kb.py      # 知识库自检：切片概况 + 三种检索方式对比
├── db/
│   ├── schema.sql         # 5 张核心表
│   ├── init_db.py         # 建库建表
│   ├── seed_questions.py  # 客观题种子数据
│   └── seed_subjective.py # 主观题种子数据
├── eval/
│   ├── dataset.json       # 评测集（检索 + 批改）
│   ├── labeling_rubric.md # 错因标注规范
│   └── run_eval.py        # 召回率 / 错因准确率 / 通过判定准确率
├── knowledge/             # 讲义源文件（切片后写入 ChromaDB）
└── data/                  # 本地持久化（ChromaDB），不纳入版本管理
```

## 数据模型（5 张表）

| 表 | 作用 |
|---|---|
| `questions` | 题库：题干、答案、解析、知识点、难度、来源 |
| `answer_records` | 答题记录：作答原文、对错、得分、错因 |
| `user_mastery` | 学情画像：用户 × 知识点的练习次数、错误次数、掌握度 |
| `eval_annotations` | 评测标注与 badcase |
| `review_plans` | 复习计划（规划 Agent 产出） |

## 快速开始

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env        # 填入 DASHSCOPE_API_KEY 与 MYSQL_PASSWORD

python db/init_db.py          # 建库建表
python db/seed_questions.py   # 客观题种子数据
python db/seed_subjective.py  # 主观题种子数据

python -m app.ingest          # 讲义切片入向量库
python -m app.graph_agent     # 答疑（自主检索 + 引用出处）
python -m app.practice        # 客观题练习（判分 + 学情画像）
python -m app.grader_agent    # 主观题批改（错因 + 评语）
python -m app.quiz_agent      # 薄弱点驱动出题
python -m app.planner_agent   # 生成复习计划
python eval/run_eval.py       # 跑评测
python -m app.inspect_db      # 查看数据库真实内容
python -m app.inspect_kb      # 对比三种检索效果
```

## 评测

`eval/run_eval.py` 覆盖两类任务：

- **检索**：Top-5 是否召回期望内容，当前 7/8 = 87.5%
- **批改**：错因判定准确率 17/18 = 94.4%，通过 / 不通过判定准确率 17/18 = 94.4%

标注口径见 `eval/labeling_rubric.md`：先判对错，再判错因，错因不影响通过判定。

## 进度

- [x] D1 项目骨架 + MySQL 四表 + Function Calling Agent
- [x] D2 客观题练习闭环 + RAG 知识库（向量 + BM25 混合检索）
- [x] D3 答疑 Agent 用 LangGraph 状态图重构
- [x] D4 批改 Agent（7 类错因结构化输出）
- [x] D5 评测框架 + 标注规范 + 三轮迭代（错因准确率 66.7% → 94.4%）
- [x] D6 出题 Agent（薄弱知识点驱动 + 答案规范化）
- [x] D7 规划 Agent（学情画像驱动复习计划，新增 `review_plans` 表）
- [ ] D8 路由 Agent + FastAPI 服务
- [ ] D9 pytest 自动化测试
- [ ] D10 前端界面 / 扫描件 OCR
