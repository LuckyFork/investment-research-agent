# 智能投研助手 Agent — 开发过程记录

---

## 项目概况

**目标**：构建一个面向证券研究场景的智能投研助手，核心能力：文档上传 → 向量化 → RAG 检索 → Agent 工具调用 → 流式对话。

**技术栈**：FastAPI · PostgreSQL · Redis · Qdrant · Celery · Deepseek（OpenAI 兼容接口）· OpenAI Embedding

---

## Step 1 — 项目骨架

**完成内容**

- FastAPI 应用工厂（`create_app`）+ async lifespan 管理基础设施连接
- 核心模块：`config.py`（pydantic-settings）、`db.py`（SQLAlchemy asyncpg）、`redis_client.py`（aioredis）、`qdrant_client.py`（AsyncQdrantClient）、`celery_app.py`
- OpenTelemetry 链路追踪接入点
- 健康检查接口 `GET /api/v1/health/ping` 与 `GET /api/v1/health/readiness`
- 测试：4 个健康检查测试，全部通过

**关键决策**

| 决策 | 原因 |
|------|------|
| pydantic-settings 读取 `.env` | 强类型配置，天然支持环境变量覆盖 |
| asyncpg driver | 纯 async，性能比 psycopg2 高 |
| `@lru_cache` 包裹 `get_settings()` | 全局单例，避免重复读文件 |

---

## Step 2 — LLM 对话接口（后改为 Step 4 入口）

**完成内容**

- `app/models/chat.py`：`ChatMessage`、`ChatRequest`（Pydantic v2 validator 拒绝空消息）、`ChatStreamEvent`、`SessionHistoryResponse`
- `app/agent/llm_client.py`：基于 Anthropic SDK 的 `stream_chat` / `complete_chat`（**Step 4 中已替换为 OpenAI SDK**）
- `app/memory/session.py`：Redis LIST 存储会话历史，TTL 24h，`MAX_TURNS=20` 自动截断
- `app/api/v1/chat.py`：SSE 流式端点 + 非流式端点 + 会话查询 / 删除
- 投研场景 System Prompt（客观引用数据、标注不确定信息、风险提示）
- 测试：7 个对话测试，全部通过

**关键决策**

| 决策 | 原因 |
|------|------|
| SSE（`text/event-stream`）而非 WebSocket | 单向推送足够，HTTP 原生支持，无需额外握手 |
| Redis LIST + RPUSH/LRANGE | 天然有序，LTRIM 截断开销 O(1) |
| 只存 user/assistant 消息 | tool_use/tool_result 是单次对话内部状态，不需要跨轮持久化 |

---

## Step 3 — 文档处理 Pipeline

**完成内容**

**新增依赖**：pdfplumber · openpyxl · beautifulsoup4 · lxml · tiktoken · openai · aiofiles

**数据库**

- `app/db/models.py`：`Document` ORM 模型（UUID 主键，状态机：pending → processing → ready/failed）
- `app/db/document_repo.py`：create / get / list / update_status / delete CRUD
- `migrations/env.py`：Alembic async 环境（`async_engine_from_config` + `asyncio.run()`）

**解析层**（`app/doc_pipeline/parsers/`）

| 文件类型 | 解析器 | 特殊处理 |
|---------|--------|---------|
| PDF | pdfplumber | 先提取表格，再提取文本，避免重复 |
| Excel | openpyxl | 每个 Sheet → 一个 table ParsedBlock |
| HTML | BeautifulSoup4+lxml | h1/h2/h3→title，`<table>`→table，`<p>`→paragraph |
| TXT | 内置 | 双换行分段 |

**分块**（`app/doc_pipeline/chunker.py`）

- tiktoken `cl100k_base` 计 token，`CHUNK_SIZE=512`，`CHUNK_OVERLAP=50`
- table / title 类型整体保留，不切分

**Embedding**（`app/doc_pipeline/embedder.py`）

- `AsyncOpenAI` + `text-embedding-3-small`（1536 维，COSINE 距离）
- 批量 100 条/次

**Celery 任务**（`app/tasks/doc_tasks.py`）

- `process_document`：同步 Celery task 包装 `asyncio.run(_run_pipeline(...))`
- 幂等 Qdrant point ID：`uuid5(NAMESPACE_OID, f"{doc_id}:{chunk_index}")`
- 删除用 `FilterSelector`（按 `document_id` payload 过滤），不依赖 point ID

**API**（`app/api/v1/documents.py`）

- `POST /upload`（202）→ 校验类型 → 存文件 → 写 DB → 分发 Celery 任务
- `GET /{doc_id}` / `GET /`（分页）/ `DELETE /{doc_id}`

**测试**：9 个文档测试，全部通过

**踩坑记录**

1. **`session.begin()` 返回协程而非 async context manager**
   - 原因：`AsyncMock(spec=AsyncSession)` 会让 `session.begin` 成为 AsyncMock，调用后得到 coroutine，不能 `async with`
   - 修复：改用 `mock_session = MagicMock()`，手动 `mock_session.begin = MagicMock(return_value=AsyncMock())`

2. **`mock_update.call_args_list` 在 `with` 块外为空**
   - 原因：patch 退出后 mock 对象恢复原函数，`call_args_list` 归零
   - 修复：把断言移入 `with patch(...)` 块内

---

## Step 4 — RAG 检索 + Agent Tool Calling（本次开发）

### 背景与动机

Step 2 建立了直接 LLM 对话链路。Step 4 的目标是让模型**能主动检索已上传文档**，而不是只凭训练知识回答。采用 **Agent Tool Use** 架构：模型自己决定是否调用 `search_documents` 工具。

### LLM 提供商切换：Anthropic → Deepseek

**原因**：Deepseek API 与 OpenAI 接口完全兼容，成本极低，且 Function Calling 支持完整。切换只需改两个地方：

| 配置项 | 旧值 | 新值 |
|--------|------|------|
| `anthropic_api_key` | Anthropic key | _已废弃_ |
| `llm_api_key` | — | Deepseek key |
| `llm_base_url` | — | `https://api.deepseek.com` |
| `llm_model` | `claude-sonnet-4-6` | `deepseek-chat` |

`.env` 示例：

```dotenv
LLM_API_KEY=sk-xxxxxxxx          # Deepseek key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
OPENAI_API_KEY=sk-xxxxxxxx       # 仍用 OpenAI text-embedding-3-small
```

如需切回 OpenAI 或接入其他 OpenAI 兼容提供商，只改 `.env`，代码零修改。

### 新增 / 修改文件一览

```
新增：
  app/agent/retriever.py     — Qdrant 向量检索
  app/agent/tools.py         — 工具 Schema + 执行器
  app/agent/agent_loop.py    — 流式 Agent 主循环
  tests/test_rag.py          — RAG 相关单元测试

修改：
  app/core/config.py         — LLM 配置字段
  app/agent/llm_client.py    — Anthropic SDK → OpenAI SDK
  app/models/chat.py         — 新增 tool_start / tool_done 事件类型
  app/api/v1/chat.py         — 路由改为调用 run_agent
  tests/test_chat.py         — mock 目标改为 run_agent
```

### 核心设计：Agent Loop（`agent_loop.py`）

```
用户消息
  │
  ▼
load_messages (Redis) → 追加 user 消息 → 构建 OpenAI 格式消息列表
  │
  ▼
循环（最多 MAX_TOOL_ROUNDS=3 轮）：
  │
  ├─ stream LLM（tools=TOOLS, tool_choice="auto"）
  │    ├─ finish_reason == "stop"
  │    │    → 收集文本 chunks，SSE yield text*
  │    │    → 保存 assistant 消息到 Redis
  │    │    → yield done，退出
  │    │
  │    └─ finish_reason == "tool_calls"
  │         → yield tool_start（前端可显示"正在搜索文档..."）
  │         → execute_tool（embed query → Qdrant search → format results）
  │         → yield tool_done（前端可显示搜索摘要）
  │         → 追加 tool result 消息，继续下一轮
  │
  └─ 超出轮数 → yield error
```

**为什么用流式检测 tool_calls，而不是先非流式再流式？**

- 流式调用时，若第一个 delta 就是 tool_call（无文本内容），text chunks 为空 → 前端不会看到任何多余文字
- 若是直接文本回答，chunks 立即转发给前端，无额外延迟
- 避免两次 API 调用（非流式检测 + 流式输出），节省 token 消耗

### SSE 事件协议（前端参考）

| 事件类型 | 含义 | 关键字段 |
|---------|------|---------|
| `text` | 流式文本片段 | `content` |
| `tool_start` | 开始调用工具 | `tool_name`, `content`（query 内容）|
| `tool_done` | 工具返回结果 | `tool_name`, `content`（结果摘要） |
| `done` | 本轮对话结束 | `session_id` |
| `error` | 异常 | `content`（错误信息）|

示例 SSE 流（带 RAG 的查询）：

```
data: {"type":"tool_start","tool_name":"search_documents","content":"茅台2024年营收"}

data: {"type":"tool_done","tool_name":"search_documents","content":"[1] 文档:xxx..."}

data: {"type":"text","content":"根据已上传的研究报告，"}

data: {"type":"text","content":"茅台2024年营收约1700亿元…"}

data: {"type":"done","session_id":"abc-123"}
```

### 工具定义（`tools.py`）

当前注册一个工具：`search_documents`

```json
{
  "name": "search_documents",
  "description": "在已上传的研究报告、财报、公告等文档中搜索相关内容...",
  "parameters": {
    "query": "string (required)",
    "top_k": "integer, 1-10, default 5"
  }
}
```

Qdrant 搜索：`SCORE_THRESHOLD=0.4`（余弦相似度），返回 `text / document_id / score / page_num / section_title`。

### Mock 技巧总结（测试经验）

**问题**：OpenAI streaming 返回的是异步生成器，`AsyncMock(return_value=...)` 无法直接模拟。

**解法**：

```python
async def fake_create(**kwargs):
    async def _gen():
        for chunk in chunks:
            yield chunk
    return _gen()

mock_client.return_value.chat.completions.create = fake_create
```

**问题**：`patch("app.memory.session.load_messages")` 不影响 `chat.py`，因为 `chat.py` 在导入时已绑定了 `load_messages` 这个名字。

**解法**：在每个**实际使用该名字的模块**处打 patch：

```python
patch("app.agent.agent_loop.load_messages", ...)  # agent_loop 使用
patch("app.api.v1.chat.load_messages", ...)       # chat.py 使用
```

### 测试覆盖（新增 test_rag.py，8 个测试）

| 测试类 | 测试用例 | 验证点 |
|--------|---------|--------|
| TestRetriever | test_search_embeds_and_queries_qdrant | embed → Qdrant search 调用链 |
| TestRetriever | test_search_returns_empty_when_no_hits | 无命中返回空列表 |
| TestToolsExecutor | test_search_documents_formats_results | 结果格式化包含关键字段 |
| TestToolsExecutor | test_no_results_returns_not_found_message | 无结果提示语 |
| TestToolsExecutor | test_unknown_tool_raises | 未知工具抛 ValueError |
| TestAgentLoop | test_direct_answer_no_tool | 无工具调用，text* + done |
| TestAgentLoop | test_tool_call_then_final_answer | tool_start + tool_done + text + done |
| TestAgentLoop | test_error_event_on_exception | LLM 异常 → error event，不抛出 |

### 测试结果

```
29 passed in 0.30s   (Step 1-4 全部测试)
```

---

## Step 5 — 长对话记忆压缩（本次开发）

### 背景与动机

Step 2 采用简单 LTRIM 策略：超过 40 条消息直接丢弃最旧的。对于投研场景，用户可能在会话开始时说"我在分析贵州茅台2024年财报"，但经过 20 多轮问答后，这条关键背景就被丢弃，模型后续回答就失去了分析对象的上下文。

### 解决方案：Summary Buffer Memory（摘要缓冲）

超出阈值时，不丢弃旧消息，而是让 LLM 将其压缩成一段摘要，存入独立的 Redis key，下一轮对话时注入到 system prompt。

```
旧策略（简单截断）：
  [消息1 … 消息40] 超出 → 直接丢弃消息1~20

新策略（摘要压缩）：
  [消息1 … 消息31] 超出 SUMMARY_THRESHOLD(30) →
    LLM 将消息1~11 压缩为摘要 → 存 Redis summary key
    保留消息12~31（最近 KEEP_RECENT=20 条）
    下次对话：system_prompt += "[历史对话背景]\n{summary}"
```

### 新增 / 修改文件

```
新增：
  app/memory/compressor.py   — LLM 摘要压缩逻辑
  tests/test_memory.py       — 13 个新测试

修改：
  app/memory/session.py      — append_message 集成压缩，新增 load_summary，clear_session 同时删除摘要 key
  app/agent/agent_loop.py    — 读取摘要并注入 system prompt
```

### 关键参数

| 常量 | 值 | 含义 |
|------|-----|------|
| `SUMMARY_THRESHOLD` | 30 | 消息数超过此值时触发压缩（约15轮对话） |
| `KEEP_RECENT` | 20 | 压缩后保留最新的消息条数 |
| `MAX_TURNS` | 20 | 降级兜底截断上限（压缩失败时使用） |
| `SESSION_TTL` | 86400 | 24h，消息和摘要 key 均使用相同 TTL |

### Redis Key 设计

```
chat:session:{id}:messages  — 最近 N 条完整消息（list）  [已有]
chat:session:{id}:summary   — 被压缩的历史摘要（string）  [新增]
```

`clear_session` 同时删除两个 key，确保会话彻底清空。

### 压缩提示词设计（compressor.py）

LLM 使用独立的 system prompt（与主对话完全隔离）：

```
你是对话历史压缩助手。
请将用户提供的投研对话历史提炼为一段简洁摘要（200字以内）。
重点保留：分析目标（公司/行业）、关键数据与结论、用户明确的偏好或约束。
忽略：重复内容、寒暄客套。
直接输出摘要正文，不要加任何前缀标签。
```

增量压缩：若已有旧摘要，新摘要提示词同时包含 `[已有摘要]` 和 `[待压缩的对话]`，让 LLM 合并输出，避免信息丢失。

### 摘要注入方式（agent_loop.py）

摘要追加到 system prompt 末尾，不污染对话轮次列表：

```python
system = SYSTEM_PROMPT
if summary:
    system = f"{SYSTEM_PROMPT}\n\n[历史对话背景]\n{summary}"
oai_messages = [{"role": "system", "content": system}, ...]
```

相比将摘要插入为伪 user/assistant 消息，此方式不增加 token 消耗，模型对 system 角色的指令遵循也更稳定。

### 错误处理

`append_message` 中的压缩步骤包裹在 `try/except` 里：

- 压缩成功：写摘要 → LTRIM 到 KEEP_RECENT 条
- 压缩失败（LLM 超时/异常）：记录 error 日志 → 降级为简单 LTRIM（会话继续正常运行，只是损失部分旧上下文）

### 测试覆盖（test_memory.py，13 个测试）

| 类 | 测试用例 | 验证点 |
|----|---------|--------|
| TestCompressor | test_returns_llm_response_as_summary | 返回值等于 LLM 输出 |
| TestCompressor | test_includes_existing_summary_in_prompt | 已有摘要出现在压缩请求中 |
| TestCompressor | test_empty_input_returns_empty_string | 无内容时不调用 LLM |
| TestCompressor | test_skips_malformed_raw_messages | 非 JSON 消息被跳过，不崩溃 |
| TestSessionCompression | test_no_compression_below_threshold | ≤30 条时不触发 LLM |
| TestSessionCompression | test_compression_triggered_above_threshold | >30 条时调用 compress_old_messages |
| TestSessionCompression | test_summary_stored_and_messages_trimmed | 摘要写 Redis，消息被 LTRIM |
| TestSessionCompression | test_compression_failure_falls_back_to_ltrim | LLM 报错时降级截断，不抛异常 |
| TestSessionCompression | test_load_summary_returns_empty_when_missing | 无摘要 key 时返回空字符串 |
| TestSessionCompression | test_load_summary_decodes_bytes | bytes 正确解码 |
| TestSessionCompression | test_clear_session_deletes_both_keys | delete 同时删除消息和摘要 key |
| TestAgentLoopSummaryInjection | test_summary_injected_into_system_prompt | system 消息包含摘要文本 |
| TestAgentLoopSummaryInjection | test_no_summary_section_when_empty | 无摘要时 system 消息不含标头 |

### 测试结果

```
42 passed in 0.32s   (Steps 1-5 全部测试)
```

---

## Step 6 — 合规预检模块（本次开发）

### 背景与动机

投研场景受《证券分析师执业行为准则》等法规约束：不得承诺收益、不得使用绝对化预测、不得引用非公开信息。Step 1-5 完成的 Agent 对生成内容没有任何过滤，存在监管风险。Step 6 在每条 Agent 回答发出前自动进行合规预检，将结果通过新 SSE 事件告知前端。

### 设计：纯规则引擎，同步执行，不阻断

| 特性 | 说明 |
|------|------|
| 零延迟 | 正则匹配，纯 CPU，微秒级，不发起任何 I/O |
| 不阻断 | 违规内容仍然发送给用户，但附带合规标注，保留人工判断权 |
| 可扩展 | 规则集独立在 `rules.py`，合规人员直接增减规则，无需改业务代码 |
| 两档严重度 | `error`（硬违规，`passed=False`）/ `warning`（需附加风险提示，`passed=True`）|

### 新增文件

```
app/compliance/
├── __init__.py
├── models.py    — ComplianceIssue / ComplianceResult Pydantic 模型
├── rules.py     — 9 条规则（6 error + 3 warning）
└── checker.py   — check_compliance(text) 主函数

tests/test_compliance.py  — 16 个测试
```

### 规则集（rules.py）

| 规则编号 | 严重度 | 描述 |
|---------|--------|------|
| PRO_001 | error | 禁止承诺或暗示投资收益 |
| PRO_002 | error | 禁止使用绝对化预测表述（必涨/零风险/100%）|
| PRO_003 | error | 禁止引用或暗示非公开信息 |
| PRO_004 | error | 禁止否认亏损可能性 |
| PRO_005 | error | 禁止对研究报告准确性或投资结果作出担保 |
| PRO_006 | error | 禁止诱导性收益表述 |
| PRW_001 | warning | 紧迫性投资操作建议须附风险提示 |
| PRW_002 | warning | 强烈程度措辞的投资建议须附风险提示 |
| PRW_003 | warning | 给出具体目标价须说明分析依据及风险 |

### SSE 事件变更

新增第 6 种事件类型 `compliance`，在 `done` 之前发出：

```
text*  →  [tool_start → tool_done]*  →  compliance  →  done
```

`compliance` 事件结构：

```json
{
  "type": "compliance",
  "compliance_passed": false,
  "compliance_issues": [
    {
      "level": "error",
      "rule": "PRO_001",
      "description": "禁止承诺或暗示投资收益",
      "snippet": "…保证您的投资一定盈利…"
    }
  ]
}
```

- `compliance_passed=true` + `issues=[]`：完全合规，前端绿色通过标注
- `compliance_passed=true` + `issues=[{level:warning}]`：有警告，前端黄色提示
- `compliance_passed=false`：存在 error 级违规，前端红色标注，提醒人工复核

### 修改文件

| 文件 | 变更 |
|------|------|
| `app/models/chat.py` | `ChatStreamEvent.type` 加入 `"compliance"`，新增 `compliance_passed` / `compliance_issues` 字段 |
| `app/agent/agent_loop.py` | `finish_reason=="stop"` 后调用 `check_compliance(full_reply)`，yield compliance 事件，再 yield done |

### 测试覆盖（test_compliance.py，16 个测试）

| 类 | 测试用例 | 验证点 |
|----|---------|--------|
| TestRuleEngine | test_clean_text_passes_with_no_issues | 正常文本零 issue |
| TestRuleEngine | test_empty_text_passes | 空字符串通过 |
| TestRuleEngine | test_承诺收益_triggers_PRO001_error | PRO_001 命中 |
| TestRuleEngine | test_绝对化表述_triggers_PRO002_error | PRO_002 命中 |
| TestRuleEngine | test_内幕信息_triggers_PRO003_error | PRO_003 命中 |
| TestRuleEngine | test_否认亏损_triggers_PRO004_error | PRO_004 命中 |
| TestRuleEngine | test_强烈推荐_triggers_PRW002_warning | warning 级，passed 仍 True |
| TestRuleEngine | test_目标价_triggers_PRW003_warning | PRW_003 命中 |
| TestRuleEngine | test_multiple_violations_all_collected | 多规则同时命中 |
| TestRuleEngine | test_snippet_contains_matched_text | snippet 包含触发词 |
| TestComplianceResult | test_passed_false_when_error_exists | error → passed=False |
| TestComplianceResult | test_passed_true_with_only_warnings | warning only → passed=True |
| TestComplianceResult | test_issues_are_complianceissue_instances | 返回值类型正确 |
| TestAgentLoopCompliance | test_compliance_event_emitted_for_clean_response | 干净回答也有 compliance 事件 |
| TestAgentLoopCompliance | test_compliance_event_flags_violation | 违规内容被标注 |
| TestAgentLoopCompliance | test_event_order_is_text_compliance_done | 严格顺序：text* → compliance → done |

### 测试结果

```
58 passed in 0.41s   (Steps 1-6 全部测试)
```

---

## 当前进度总览

```
Step 1 ✅  项目骨架（FastAPI + DB + Redis + Qdrant + Celery + 健康检查）
Step 2 ✅  LLM 对话接口（SSE 流式 + 多轮会话 + Redis 记忆）
Step 3 ✅  文档处理 Pipeline（解析 → 分块 → Embedding → Qdrant 存储）
Step 4 ✅  RAG 检索 + Agent Tool Calling（Deepseek + 工具调用 + 流式输出）
Step 5 ✅  长对话记忆压缩（LLM 摘要缓冲 + system prompt 注入）
Step 6 ✅  合规预检模块（规则引擎 + SSE compliance 事件）
Step 7 ⬜  前端 UI
```

## 如何启动本地开发环境

```bash
# 1. 启动基础设施（需要 Docker）
docker compose up -d          # PostgreSQL + Redis + Qdrant

# 2. 数据库迁移
alembic upgrade head

# 3. 启动 Celery worker
celery -A app.core.celery_app worker --loglevel=info

# 4. 启动 FastAPI
uvicorn app.main:app --reload

# 5. 测试 RAG 对话（需先上传文档）
curl -N -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test-001","message":"分析一下已上传文档中的营收数据","stream":true}'
```

## .env 配置参考

```dotenv
# LLM（Deepseek，OpenAI 兼容）
LLM_API_KEY=sk-xxxxxxxx
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat

# Embedding（OpenAI）
OPENAI_API_KEY=sk-xxxxxxxx
EMBEDDING_MODEL=text-embedding-3-small

# 数据库
POSTGRES_HOST=localhost
POSTGRES_PASSWORD=postgres

# Redis
REDIS_HOST=localhost

# Qdrant
QDRANT_HOST=localhost
```
