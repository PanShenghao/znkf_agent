# 数码电商智能客服（znkf_agent）

> **作者**：psh　·　个人学习与工程实践项目（LangGraph 多智能体 + RAG + MCP 的电商客服系统）

一个面向数码电商场景的多智能体客服系统，覆盖商品咨询、订单物流、优惠活动、商品推荐、比价对比、售后维修六类业务，并在「搞不定」时转接人工。

---

## 1. 项目目标

本系统解决的是一个典型的电商客服问题：

1. 用自然语言回答商品参数、订单物流、优惠活动、推荐、比价、售后等问题。
2. 通过「总路由 + 专业子 Agent」的分工，让每个场景的提示词与工具精准、可独立优化。
3. 通过 RAG（混合检索 + 知识图谱）保证回答有据可依，而非模型凭空编造。
4. 通过熔断、置信度、反幻觉门，在系统「搞不定」时转接人工，而不是硬答。
5. 补齐鉴权、工单状态机、token 计量、评测，形成可上线的基础骨架。

---

## 2. 当前已完成功能

### 2.1 智能体能力

- 总路由：关键词规则 + LLM 双路路由，含「欺诈/法律/转人工」确定性规则优先
- 4 个专业子 Agent：商品导购（参数咨询 + 推荐 + 比价）/ 订单物流 / 优惠 / 售后
- 寒暄 Agent：处理问候、感谢、闲聊，避免误转人工
- 转人工节点：warm handoff 上下文 + 工单状态机 + Chatwoot 推送（可选）

### 2.2 RAG 能力

- 多格式文档加载：`md / txt / pdf / docx / xlsx`
- 文档清洗 + 父子分块（Parent-Child Chunking）
- 分批向量化 + 增量入库（doc_id 幂等 upsert）+ HNSW 索引
- 混合检索：BM25 + 向量 + RRF 融合，召回放大
- 知识图谱：商品/品牌/品类实体关系，确定性参数与关系查询
- 反幻觉：检索无证据 → 升级转人工，而非编造

### 2.3 工程能力

- 熔断器（closed/open/half-open）+ 统一 LLM 工厂（超时/重试）
- 最小鉴权（签名 token）+ 工具层 UserIdInjector 防越权
- token 用量计量（单价快照）
- 语义缓存（L1 精确 + L2 语义）
- 分层记忆：短期 Redis + 长期 Milvus + LLM 偏好提炼
- 评测门禁：确定性评测 + DeepEval 质量分
- 全容器化：docker-compose 一键启动

---

## 3. 技术栈

| 层次 | 技术 |
|---|---|
| LLM | 通义千问（OpenAI 兼容接口） |
| Agent 框架 | LangChain + LangGraph |
| 向量库 | Milvus（RAG / 长期记忆 / 语义缓存） |
| 图数据库 | Neo4j（知识图谱） |
| 缓存 | Redis（短期记忆 / 失败计数） |
| 业务库 | MySQL（商品/订单/工单/用量） |
| 工具协议 | MCP（stdio） |
| 后端 | FastAPI + SSE |
| 前端 | Vue 3 + Vite + TypeScript + Element Plus |
| 评测 | DeepEval + 自研确定性评测 |
| 部署 | Docker Compose |

---

## 4. 目录结构

```text
znkf_agent
├── agent                     # 智能体核心
│   ├── agents                # 路由 + 4 子 Agent + 寒暄
│   ├── core
│   │   ├── workflow          # LangGraph 编排、状态
│   │   ├── policy            # 升级策略（规则门 + 执行门）
│   │   ├── tickets           # 工单状态机
│   │   ├── resilience        # 熔断器、失败计数、LLM 工厂
│   │   ├── rag               # 文档加载、清洗、父子分块、入库
│   │   ├── memory            # 短期/长期/偏好提炼
│   │   ├── mcp               # MCP 客户端 + 安全拦截器
│   │   └── grounding         # 检索证据记录器（反幻觉）
│   ├── tools                 # 向量检索、图谱查询工具
│   ├── mcp_servers           # MCP 服务端（查订单/物流/优惠/商品/售后）
│   ├── database              # MySQL 初始化 SQL
│   ├── config                # 配置中心
│   └── main.py               # CLI 入口
├── app                       # 服务层
│   ├── router                # REST API 路由
│   ├── service               # 聊天服务（缓存/记忆/图执行/转人工）
│   ├── security              # 鉴权
│   ├── schemas               # Pydantic 请求响应模型
│   └── infra                 # 语义缓存
├── front                     # 前端（Vue3 聊天界面）
├── scripts                   # 入库、图谱、评测脚本
├── demo_data                 # 演示用虚构数据（详见 demo_data/README.md）
├── docker-compose.yml        # 一键部署
├── Dockerfile.backend        # 后端镜像
├── Dockerfile.frontend       # 前端镜像
├── .env.example              # 环境变量示例（.env 不入库）
└── requirements.txt
```

---

## 5. 系统整体架构

### 5.1 架构分层

系统分为 5 层：

1. 展示层：Vue 前端聊天界面（SSE 流式）
2. API 层：FastAPI 路由（鉴权 / 对话 / 工单 / 健康检查）
3. 智能体层：LangGraph 状态图（路由 → 子 Agent → 转人工）
4. 能力层：RAG（向量+图谱）、MCP、记忆、熔断、反幻觉
5. 数据层：Milvus（向量）、Neo4j（图谱）、Redis（缓存/计数）、MySQL（业务/工单/用量）

### 5.2 一次请求的完整链路

```
POST /api/chat（Bearer token）
  → 解出 user_id → 语义缓存检查
  → 熔断短路（打开则直接转人工）
  → 提取记忆上下文（短期历史 + 长期偏好）
  → 路由门：欺诈/法律/转人工（正则）→ 关键词 → LLM
  → 子 Agent（ReAct：RAG 检索 + 工具调用）
  → 执行门：空回复 / RAG 无证据 / 连续失败 → 转人工
  → 建工单（状态机）+ 推送 Chatwoot
  → token 用量落库
  → SSE 流式返回
```

---

## 6. 后端模块说明

### 6.1 配置中心（`agent/config/settings.py`）

由 `BaseSettings` 统一管理，集中维护 LLM、Milvus、Neo4j、MySQL、Redis、鉴权、熔断阈值等配置。所有依赖统一入口，不在业务代码里散落；`.env` 与字段一一对应。

### 6.2 API 路由

| 方法 | 路径 | 说明 | 鉴权 |
|---|---|---|---|
| POST | `/api/auth/token` | 用 user_id 换签名 token | 无 |
| POST | `/api/chat` | 客服对话（SSE 流式） | Bearer |
| POST | `/api/session/end` | 结束会话、提炼长期偏好 | Bearer |
| GET | `/api/session/history` | 会话历史（后端恢复） | Bearer |
| POST | `/api/tickets/takeover` | 坐席接管工单 | 内部 token |
| POST | `/api/tickets/close` | 关闭工单（回流 AI） | 内部 token |
| POST | `/api/tickets/cancel` | 取消转接 | 内部 token |
| GET | `/healthz` / `/readyz` | 存活 / 就绪探针 | 无 |

### 6.3 升级策略（`agent/core/policy.py`）

所有「何时转人工」的阈值集中在一个 `EscalationPolicy`，两条门：

- **路由门**：欺诈 > 法律 > 转人工（正则，LLM 之前命中）
- **执行门**：熔断打开 > 连续失败达阈值 > 空/过短回复 > RAG 无证据

### 6.4 工单状态机（`agent/core/tickets.py`）

```
待处理(0) ──接管──► 接管中(1) ──关闭──► 已关闭(3)
    └────取消──► 已取消(2)
```

每次状态变更写 `ticket_logs` 审计。转接话术带工单号（`工单号：TK-xxxxxxxx`）。

---

## 7. 数据库设计（MySQL）

核心表 8 张：

| 表 | 用途 |
|---|---|
| `products` | 商品目录（名称/品牌/品类/价格/规格 JSON） |
| `orders` | 订单（用户/商品/金额/状态） |
| `logistics` | 物流（运单/订单/快递/状态） |
| `coupons` | 优惠券（满减/折扣） |
| `after_sales` | 售后单（退货/换货/维修） |
| `tickets` | 人工转接工单（状态机） |
| `ticket_logs` | 工单操作日志（审计） |
| `token_usage` | token 用量计费（单价快照） |

---

## 8. Milvus 向量库设计

| 集合 | 用途 | 索引 |
|---|---|---|
| `product_docs` | RAG 知识库（父子分块：`content` 检索、`parent_text` 生成） | HNSW / COSINE |
| `shop_qa_semantic_cache` | 语义缓存（L1 精确 + L2 语义） | IVF_FLAT / COSINE |
| `long_term_memory` | 长期偏好记忆（按 user_id 隔离） | IVF_FLAT / COSINE |

`product_docs` 字段：`chunk_id`（主键，doc_id+parent+content 的 md5）、`doc_id`、`source`、`content`（child）、`parent_text`（parent）、`embedding`。

增量入库：按 `doc_id` 幂等删除旧向量 + upsert 新向量，改一份文档只动一份。

---

## 9. RAG 知识管理方式

按「文档 → 清洗 → 父子分块 → 向量」管理：

1. **加载**：按扩展名路由到解析器（pdf/docx/xlsx/md/txt）。
2. **清洗**：去空白、归一化、保留段落结构。
3. **父子分块**：大 parent（~600 字符）用于生成上下文，小 child（~200 字符，带 overlap）用于检索。
4. **向量化**：分批 embed（每批 100）防 OOM。
5. **入库**：Milvus HNSW，doc_id 幂等 upsert。

检索命中 child 后返回其 parent 全文，兼顾「检索精度」与「生成上下文」。

---

## 10. 检索逻辑

### 10.1 混合检索（`agent/tools/vector_tool.py`）

1. 向量召回（Milvus HNSW）+ BM25 关键词召回（jieba 分词）。
2. RRF 融合（`1/(60+rank)`）。
3. 映射到 parent 去重，返回 top-k。
4. 置信度（COSINE 相似度）低于阈值 → 返回「[无检索证据]」。

### 10.2 知识图谱查询（`agent/tools/graph_tool.py`）

1. 商品名精确匹配 → 直接 `MATCH` 该商品属性。
2. 品牌/品类关系查询（如「小米有哪些手机」）→ 确定性 Cypher。
3. 复杂多跳关系 → GraphCypherQAChain 兜底。

---

## 11. Agent 设计

### 11.1 编排

```
orchestrator → {product / order / promotion / after_sales / concierge / human_handoff}
```

子 Agent 使用 `create_react_agent`（ReAct），返回前由 `run_react_agent` 重建「干净最终回答」（去除工具调用前的推理文字）。

### 11.2 转人工闭环

「转人工」不是 prompt 里的一句话，而是一条完整链路：

1. 触发：显式「转人工」/ 欺诈法律规则 / 熔断 / 连续失败 / 空回复 / 无证据。
2. warm handoff：打包「最近消息 + 失败原因 + 已尝试 Agent」上下文。
3. 建工单：写 `tickets` + `ticket_logs`，返回带工单号的转接话术。
4. 推送：可选推送到 Chatwoot 真人工作台。
5. 回流：坐席关闭工单后会话回到 AI。

### 11.3 反幻觉

- 检索证据记录器（`core/grounding.py`）：RAG 工具记录「是否找到证据 + 置信度」。
- 无证据 → 升级转人工，而非编造。
- 检索结果优先于模型内部知识（`core/context.py` 注入当前日期 + grounding 说明）。

---

## 12. 前端

单页客服聊天界面（Vue 3 + Element Plus）：

- SSE 流式消息渲染 + Markdown（表格/代码块）
- 快捷提问、转人工按钮、工单号高亮
- 会话历史（后端恢复 + 本地兜底）、结束会话、切换测试用户

---

## 13. 环境变量

| 变量名 | 说明 |
|---|---|
| `DASHSCOPE_API_KEY` | 通义千问 API Key |
| `MODEL` | 对话模型名（默认 qwen-plus） |
| `BASE_URL` | OpenAI 兼容接口地址 |
| `REDIS_URL` | Redis 连接地址 |
| `MILVUS_HOST` / `MILVUS_PORT` | Milvus 连接 |
| `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` | Neo4j 连接 |
| `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | MySQL 连接 |
| `AUTH_SECRET` | 鉴权签名密钥 |
| `CB_FAILURE_THRESHOLD` / `CB_RESET_TIMEOUT` | 熔断阈值 / 冷却时间 |
| `HUMAN_ESCALATION_THRESHOLD` | 连续失败转人工阈值 |
| `LLM_INPUT_PRICE_PER_1M` / `LLM_OUTPUT_PRICE_PER_1M` | token 单价（元/百万） |
| `CHATWOOT_URL` / `CHATWOOT_ACCESS_TOKEN` / `CHATWOOT_ACCOUNT_ID` / `CHATWOOT_API_INBOX_ID` | Chatwoot（可选） |

注意：`.env` 不入库，真实配置见 `.env.example`。

---

## 14. 启动方式

### 14.1 全容器化（推荐）

```bash
cp .env.example .env   # 填入 DASHSCOPE_API_KEY 与 AUTH_SECRET
docker compose up -d --build
```

默认地址：

- 前端：`http://localhost:8080`
- 后端：`http://localhost:5000`（`/healthz` `/readyz`）
- Neo4j：`http://localhost:7474`（neo4j/cloudagent123）
- Milvus：`localhost:19530`

### 14.2 本地开发

```bash
# 起基础设施
docker compose up -d mysql redis milvus neo4j

# 后端
cd app && ../.venv/Scripts/python.exe -m uvicorn app_main:app --port 5000

# 前端
cd front && npm run dev
```

### 14.3 数据入库

```bash
.venv/Scripts/python.exe scripts/ingest_vector.py          # 向量入库（增量）
.venv/Scripts/python.exe scripts/ingest_graph.py           # 图谱入库
```

演示数据在 `demo_data/`（虚构数据，详见 `demo_data/README.md`）。

---

## 15. 评测

```bash
.venv/Scripts/python.exe scripts/eval_test.py        # 确定性门禁：越权/转人工/幻觉/报错
.venv/Scripts/python.exe scripts/eval_deepeval.py    # DeepEval 质量分：相关性/忠实度
```

---

## 16. 当前实现特点与边界

### 已具备的优势

- 业务闭环完整：路由 → 子 Agent → 转人工 → 工单 → 回流
- 反幻觉有确定性兜底（无证据升级），而非纯 prompt 约束
- 图谱参数/关系查询用确定性 Cypher，不依赖 LLM 生成
- 向量、图谱、业务库三者职责分离
- 全容器化，一条命令复现

### 当前边界

- 重排序（cross-encoder）未接入，RRF 融合为第一版
- 会话持久化依赖 Redis 短期记忆，无正式迁移体系
- 演示数据为虚构（`demo_data/`），模型对「未来产品型号」会保持警惕
- 知识图谱需随商品目录手动维护

---

## 17. 后续可扩展方向

- 检索层：cross-encoder 重排、query rewrite、metadata filter
- Agent 层：更严格的工具调用策略、多跳业务决策链
- 权限层：用户级 / 知识库级隔离
- 前端层：Chunk 可视化、检索调试台、来源高亮定位
- 运维层：CI/CD、监控告警、Alembic 迁移

---

## 18. 一句话总结

这不是一个只会「检索然后问答」的简化 Demo，而是一个已具备多智能体分工、混合检索、知识图谱、熔断转人工、工单状态机、反幻觉、鉴权与评测的电商客服系统。
