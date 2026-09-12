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
| 缓存 | `app/cache.py` | 检索结果缓存 + 多轮会话记忆放 Redis，连不上自动降级为进程内实现；检索缓存用知识库版本号失效，不用会阻塞的 `KEYS` 扫删 |
| 界面 | `app/api.py` + `web/index.html` | 单页操作台：答疑、出题、练习、规划、学情五个面板，纯静态无构建；数学公式用 KaTeX 渲染，加载失败自动退回原文 |

## 技术栈

Python 3.10 · FastAPI · LangGraph · LangChain · Qwen（DashScope OpenAI 兼容模式）·
ChromaDB + BM25（RRF 混合检索）· Redis · MySQL · pdfplumber · pytest + Node 测试

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
│   ├── cache.py           # Redis 缓存层：检索缓存 + 会话记忆（连不上自动降级）
│   ├── inspect_db.py      # 数据自检：查看 MySQL 各表真实内容
│   ├── inspect_kb.py      # 知识库自检：切片概况 + 三种检索方式对比
│   └── inspect_cache.py   # 缓存自检：后端 / 命中率 / 键分布 / 冷热检索对比
├── db/
│   ├── schema.sql         # 5 张核心表
│   ├── init_db.py         # 建库建表
│   ├── seed_questions.py  # 客观题种子数据
│   └── seed_subjective.py # 主观题种子数据
├── eval/
│   ├── dataset.json       # 评测集（检索 + 批改）
│   ├── labeling_rubric.md # 错因标注规范
│   └── run_eval.py        # 召回率 / 错因准确率 / 通过判定准确率
├── web/
│   └── index.html         # 单页操作界面（静态，挂载在 /ui；公式由 KaTeX 渲染）
├── tests/                 # pytest 用例（纯函数 + 打桩，不依赖真实大模型与数据库）
│   └── js/                # 前端渲染的 Node 用例（node tests/js/test_render.js）
├── docker-compose.yml     # 本地 Redis 7（可选，起不来会自动降级）
├── pytest.ini             # 测试配置（testpaths / pythonpath / markers）
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

docker compose up -d redis    # 起 Redis（可选：不起也能跑，会自动降级为进程内缓存）
python -m app.inspect_cache demo   # 冷热检索对比 + 缓存失效演示
python -m app.inspect_cache        # 当前后端 / 命中率 / 键数量

pytest                        # 跑单元测试（不消耗 API 额度、不依赖 MySQL / Redis）

# 启动 HTTP 服务
python -m app.api
#   操作界面  http://127.0.0.1:8000/ui/
#   接口文档  http://127.0.0.1:8000/docs
```

## 缓存与会话（Redis）

`app/cache.py` 把检索结果缓存与多轮会话记忆放到 Redis；连不上时自动降级为进程内实现，
业务不中断（`GET /cache/stats` 的 `backend` 字段会显示 `memory`，一眼看出跑在哪个后端）。

| 键 | 类型 | 作用 |
|---|---|---|
| `ashore:kb:version` | String | 知识库版本号，`app/ingest.py` 入库成功后 +1 |
| `ashore:ret:{版本}:{查询指纹}` | String(JSON) | 混合检索结果缓存，TTL 1 小时 |
| `ashore:sess:{user_id}` | List | 多轮会话记忆，只留最近 20 条，TTL 1 天 |

两个设计点：

- **检索缓存用版本号失效，而不是删键。** re-ingest 之后旧切片就作废了，如果只按 query 缓存，
  用户会拿到已经不存在的内容。常见写法是入库后删掉 `ashore:ret:*`，但 `KEYS` 会阻塞整个 Redis、
  `SCAN` 又要全量遍历。这里把版本号编进 key：入库后 `INCR` 一次，旧 key 再也命中不到，剩下的
  交给 TTL 回收，失效动作是 O(1) 且不阻塞。空结果不写缓存，避免「知识库还没入库」被固化一小时。
- **会话记忆外置。** 原来是 `router_agent` 里的进程内 dict，uvicorn 起多 worker 时同一用户会被
  轮询到不同进程，上下文直接丢；进程重启也全清。另外持久化的只有「提问 + 最终回答」，
  工具调用的中间消息一律丢弃：它们带着整段检索原文、体积是对话本身的十倍量级，而且
  `tool_calls` 与 `tool_call_id` 必须成对，一旦按条数截断就会出现半截配对，下一轮请求会被接口拒绝。

## 评测

`eval/run_eval.py` 覆盖两类任务：

- **检索**：Top-5 是否召回期望内容，当前 7/8 = 87.5%
- **批改**：错因判定准确率 17/18 = 94.4%，通过 / 不通过判定准确率 17/18 = 94.4%

标注口径见 `eval/labeling_rubric.md`：先判对错，再判错因，错因不影响通过判定。

## 测试

```bash
pytest                          # 后端用例：78 条（另有 3 条真 Redis 联调，Redis 没起时自动 skip）
pytest -m integration           # 只跑真 Redis 联调（需先 docker compose up -d redis）
node tests/js/test_render.js    # 前端渲染用例：14 条（需 Node 18+）
```

后端用例（`tests/`，共 78 条）：

| 文件 | 覆盖内容 |
|---|---|
| `test_practice.py` | 客观题判分边界：大小写、多余文字、数学撇号 ′、空作答 |
| `test_quiz_normalize.py` | 出题答案规范化：`math:` 前缀、LaTeX 包裹、选项内容反查字母、填空题重复左端、解析自我纠错清理 |
| `test_planner_clean.py` | 规划依据里的自我校验痕迹清理 |
| `test_retriever_rrf.py` | RRF 融合：两路结果都保留、双路命中的片段排名更高、top_k 截断 |
| `test_grader.py` | 批改 Agent（假 LLM 打桩）：错因枚举兜底、提示词组装 |
| `test_router.py` | 路由确定性规则：带 `question_id` 不过意图分类、意图分发、多轮会话记忆的上限与跨轮传递、工具中间态不落盘 |
| `test_cache.py` | 缓存层：Redis 不可用时降级、探测只做一次、脏缓存清理、检索缓存的命中与「版本号 +1 后失效」、空结果不缓存、会话 TTL 与只留最近 N 条 |
| `test_api.py` | FastAPI 接口：参数校验、异常转 500、题库与计划接口、`/ui` 页面挂载 |
| `test_eval_dataset.py` | 评测集自检：字段完整、错因取值合法 |
| `test_cache_integration.py` | 真 Redis 联调（Redis 没起时自动 skip）：后端判定、键类型是 List、TTL、版本号 |

单元测试统一用 `tests/stubs.py` 里的假模型打桩，因此跑测试不消耗 API 额度、不依赖 MySQL。

前端用例（`tests/js/test_render.js`，14 条）覆盖答案里 Markdown 与 LaTeX 的混合渲染：
跨行 `$$` 块、`\begin{cases}` 环境、货币符号不误判成公式、加粗跨公式片段不露出星号、
KaTeX 不可用时降级显示原文。该脚本从 `web/index.html` 的 `mathify` 标记段**抽取真实代码**执行，
不是复制一份逻辑，所以测的就是页面实际运行的实现。

## 进度

- [x] D1 项目骨架 + MySQL 四表 + Function Calling Agent
- [x] D2 客观题练习闭环 + RAG 知识库（向量 + BM25 混合检索）
- [x] D3 答疑 Agent 用 LangGraph 状态图重构
- [x] D4 批改 Agent（7 类错因结构化输出）
- [x] D5 评测框架 + 标注规范 + 三轮迭代（错因准确率 66.7% → 94.4%）
- [x] D6 出题 Agent（薄弱知识点驱动 + 答案规范化）
- [x] D7 规划 Agent（学情画像驱动复习计划，新增 `review_plans` 表）
- [x] D8 路由 Agent + FastAPI 服务（/chat 统一入口 + 7 个接口）
- [x] D9 pytest 自动化测试（54 条用例，LLM 打桩、免数据库）
- [x] D10 单页操作界面（答疑 / 出题 / 练习 / 规划 / 学情五面板）
- [x] D11 Redis 缓存层（检索结果缓存 + 多轮会话外置，不可用时自动降级）
- [ ] 二期：扫描件 OCR、界面组件化、会话记忆压缩
