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

---

## Step 8 — 第一轮金融 Agent 安全化（只读受控版）

### 本轮目标

把当前项目从“能回答、能检索的投研助手”推进到“**最基础可控的只读型金融研究助手**”。

这一轮不做交易、不做申请、不做个性化推荐自动执行，优先补齐最关键的控制面：

1. **请求身份上下文**：每个受保护接口都要有 `user_id / tenant_id`，不再允许匿名共享会话。
2. **文档归属隔离**：上传、查询、删除、检索都必须绑定文档所有者，避免跨用户串文档。
3. **检索前权限收口**：RAG 不再全库搜索，而是按调用者上下文过滤。
4. **合规从提示升级为阻断**：不再把违规回答先流给用户再提示，而是在输出前拦截。
5. **离线可测性修复**：解决 `tiktoken` 在无网环境导入即下载导致测试失败的问题。

### 详细方案

#### 1. 请求上下文与会话隔离

- 新增 `app/core/request_context.py`
- 通过请求头读取：
  - `X-User-Id`
  - `X-Tenant-Id`
  - `X-Request-Id`
  - `X-Channel`
- `chat` / `documents` 路由统一依赖该上下文
- 会话不再直接使用前端传入的 `session_id`，而是内部拼接为：

```text
tenant_id:user_id:session_id
```

这样可以防止不同用户碰撞同一个 `session_id`。

#### 2. 文档 ownership 落库

- 为 `documents` 表增加：
  - `tenant_id`
  - `owner_user_id`
- 新增 Alembic migration：`0d5c9c8a3b10_add_document_ownership.py`
- 上传文档时写入归属信息
- 文档查询 / 列表 / 删除时按归属过滤

#### 3. Qdrant 检索隔离

- 文档入向量库时，把以下字段写入 payload：
  - `tenant_id`
  - `owner_user_id`
- `search_documents` 检索时增加 Qdrant filter，只查当前用户自己的文档

这一步把 RAG 从“全局知识库检索”收紧到“当前调用者授权范围内检索”。

#### 4. 合规阻断模式

- 之前链路：
  - LLM 流式产出文本
  - 文本已发给前端
  - 最后再做 regex 合规扫描

- 改造后链路：
  - 先缓冲 LLM 文本
  - 结束后执行 `check_compliance`
  - 合规通过：再把文本返回给用户
  - 合规失败：不返回原始回答，改为安全阻断文案

这意味着当前实现更接近一个真正的 `guardrail`，虽然仍然是规则版，不是完整策略服务。

#### 5. Tool 调用收口

- `run_agent` 不再“裸执行工具”
- 工具执行时显式接收 `RequestContext`
- `top_k` 做服务端 clamp（1~10）

虽然还不是完整的 `policy service + tool gateway`，但已经开始把“工具执行是否合法”从纯 prompt 逻辑收回到后端。

#### 6. 离线环境稳定性

- `app/doc_pipeline/chunker.py` 中把 `tiktoken.get_encoding("cl100k_base")` 从 import 时执行改为惰性加载
- 如果离线拿不到 encoding 文件，则退化为本地字符切分

这样项目在无网环境下依然能完成测试和大部分本地开发。

### 本轮实际改动

**新增文件**

- `app/core/request_context.py`
- `migrations/versions/0d5c9c8a3b10_add_document_ownership.py`

**修改主链路**

- `app/api/v1/chat.py`
- `app/api/v1/documents.py`
- `app/agent/agent_loop.py`
- `app/agent/tools.py`
- `app/agent/retriever.py`
- `app/tasks/doc_tasks.py`
- `app/doc_pipeline/chunker.py`
- `app/db/document_repo.py`
- `app/db/models.py`
- `app/models/chat.py`
- `app/models/document.py`

**测试同步**

- `tests/conftest.py`
- `tests/test_chat.py`
- `tests/test_compliance.py`
- `tests/test_documents.py`
- `tests/test_memory.py`
- `tests/test_rag.py`

### 验证结果

本地执行：

```bash
pytest
```

结果：

```text
59 passed in 0.64s
```

### 这一轮完成后的项目状态

当前项目已经从“投研问答 + RAG Demo”提升到：

**带有基础身份上下文、会话隔离、文档归属过滤、输出阻断式合规检查的只读投研助手。**

但仍然没有完成这些金融 Agent 关键能力：

- 真实登录鉴权 / token 校验
- 规则版本化 policy service
- 审计日志落库（trace_id / rule_version / tool_request / tool_response）
- 用户风险等级 / 产品风险等级 / 适当性校验
- 人工复核队列
- 多级工具权限（只读 / 草稿 / 写入 / 高风险动作）

### 下一步建议（Step 9）

优先进入“**策略层与审计层**”：

1. 新增 `policy service`
   - 统一做工具权限、场景约束、参数白名单、适用边界判断
2. 新增 `audit service`
   - 记录请求上下文、工具调用、命中规则、最终输出
3. 让 LLM 输出从自由文本升级为结构化：
   - `intent`
   - `action_proposal`
   - `citations`
4. 为高风险场景预留：
   - 人工复核
   - badcase 回放
   - 降级策略

---

## Step 9 — 策略层与审计层（第二步开发）

### 本轮目标

在 Step 8 的“身份隔离 + 文档隔离 + 合规阻断”基础上，继续把项目往金融 Agent 的控制面推进，核心是两件事：

1. **Policy Service**：把“能不能调工具、参数能不能过”从 prompt 内部决策收回后端。
2. **Audit Service**：把一次对话里的关键动作落成可追溯审计事件。

本轮仍然保持项目定位为**只读型受控投研助手**，不开放写入动作。

### 详细方案

#### 1. Policy Service 的职责

新增 `app/policy/` 模块，专门负责在工具执行前给出一个结构化决策：

- `allowed`
- `reason_code`
- `reason`
- `user_message`
- `sanitized_args`

对当前唯一工具 `search_documents`，策略层负责：

- 工具是否在 allowlist 中
- 当前请求是否具备身份上下文
- `query` 是否为空
- `top_k` 是否为整数
- `top_k` 是否超界（服务端收口）
- 只保留允许的参数字段，过滤杂项参数

这样 `LLM -> tool` 之间第一次有了真正的后端规则闸门。

#### 2. Audit Service 的职责

新增 `app/audit/` 模块，采用“best effort”策略：

- 正常情况下落库
- 审计系统异常时只记日志，不阻断主业务

本轮设计成**事件流式审计**，而不是一次请求只存一条。这样后续做复盘、badcase、人工复核会更自然。

本轮落库字段包括：

- `trace_id`
- `session_id`
- `tenant_id`
- `user_id`
- `channel`
- `event_type`
- `model_version`
- `prompt_version`
- `rule_version`
- `tool_name`
- `tool_args`
- `tool_result_preview`
- `policy_decision`
- `compliance_passed`
- `compliance_issues`
- `message_preview`
- `error_message`

#### 3. 数据库设计

新增 `audit_events` 表，对应：

- ORM：`app/db/models.py` 中新增 `AuditEvent`
- Repo：`app/db/audit_repo.py`
- Migration：`5f8b2c6e9a71_add_audit_events.py`

当前是 append-only 设计，后续适合做：

- trace 查询
- 对话回放
- 规则命中分析
- 工具使用审计

#### 4. Agent Loop 集成点

在 `app/agent/agent_loop.py` 中插入两个新层次：

**进入对话时**

- 记录 `user_message` 审计事件

**工具调用前**

- 先走 `evaluate_tool_call`
- 审计 `tool_call`
- 如果策略通过：
  - 发 `tool_start`
  - 真正执行工具
- 如果策略拦截：
  - 不执行工具
  - 直接给模型一个“被策略层阻止”的 tool result
  - 让模型继续生成安全回复

**工具完成后**

- 审计 `tool_result`

**最终回答时**

- 继续跑 `compliance`
- 审计 `final_response`

**异常时**

- 审计 `error`

#### 5. 版本化元数据

为了让审计记录更可复盘，本轮补了两个版本号常量：

- `PROMPT_VERSION = "research-agent-v2"`
- `RULESET_VERSION = "2026-05-23"`

这样后续出了 badcase，至少能知道：

- 用的是哪个 prompt 版本
- 命中的是哪套规则版本
- 跑的是哪个模型版本

### 本轮实际改动

**新增模块**

- `app/policy/__init__.py`
- `app/policy/models.py`
- `app/policy/service.py`
- `app/audit/__init__.py`
- `app/audit/service.py`
- `app/db/audit_repo.py`

**新增迁移**

- `migrations/versions/5f8b2c6e9a71_add_audit_events.py`

**修改主链路**

- `app/agent/agent_loop.py`
- `app/agent/llm_client.py`
- `app/compliance/rules.py`
- `app/core/request_context.py`
- `app/db/models.py`

**测试新增**

- `tests/test_policy.py`

**测试辅助更新**

- `tests/conftest.py`

### 验证结果

本地执行：

```bash
pytest
```

结果：

```text
65 passed in 0.61s
```

### 当前项目状态

做到这一步后，项目已经不只是“带合规扫描的 RAG 助手”，而是具备了更明确的控制结构：

1. 请求有身份上下文
2. 文档与检索有所有权边界
3. 输出有阻断式合规检查
4. 工具执行前有策略判断
5. 对话关键节点有审计事件

换句话说，项目已经开始接近：

**“有控制平面的只读型金融研究 Agent”**

但还没进入这些更强的金融能力：

- 结构化 `intent / action_proposal / citations`
- 用户风险等级 / 产品风险等级 / 适当性校验
- 人工复核工作流
- 风险分级工具权限
- 审计查询接口 / badcase 后台
- 真正的身份认证和 RBAC

### 下一步建议（Step 10）

我建议第三步优先做“**结构化 Agent 决策 + 更完整的 policy contract**”：

1. 让模型显式产出：
   - `intent`
   - `action_proposal`
   - `citations`
   - `confidence`
2. 把 policy 从“工具参数校验”升级成：
   - 场景分类
   - 是否允许个性化建议
   - 是否必须转人工
   - 是否只能输出解释，不允许结论
3. 增加审计查询与 badcase 回放接口
4. 预留人工复核队列的数据模型

---

## Step 10 — 结构化决策层与场景级 Policy（第三步开发）

### 本轮目标

把项目从“有策略层和审计层的只读研究助手”继续推进到：

**模型先给结构化决策对象，后端再按场景审批执行的受控研究 Agent。**

这一轮的关键不是再加工具，而是把系统从“自由文本驱动”切换成“结构化决策驱动”。

### 设计思路

前两步已经解决了：

1. 谁能访问什么
2. 工具执行前有没有最基本的 policy
3. 关键动作有没有审计留痕

但系统仍然缺一层最关键的中间语义：

- 模型把用户请求理解成什么？
- 模型下一步准备做什么？
- 模型有没有足够证据？
- 这是不是一个建议/高风险请求？

如果没有这层结构化决策，policy 只能看字符串、看工具名，很难做真正的场景级判断。

所以第三步先引入一个 `AgentDecision` schema，让模型明确输出：

- `intent`
- `action`
- `evidence`
- `response`

然后后端根据这个对象做：

- 场景识别
- 策略审批
- 工具放行/拦截
- 最终答复降级
- 审计增强

### Schema 设计

新增文件：

- `app/models/decision.py`

包含四层结构：

1. `intent`
   - `intent_type`
   - `user_goal`
   - `reasoning`
   - `confidence`

2. `action`
   - `action_type`
   - `requires_tool`
   - `tool_name`
   - `tool_args`
   - `fallback_action`
   - `fallback_reason`

3. `evidence`
   - `citations`
   - `has_sufficient_evidence`
   - `evidence_gap`

4. `response`
   - `answer_draft`
   - `includes_risk_note`
   - `is_personalized`
   - `needs_human_review`

当前先覆盖这些意图类型：

- `fact_lookup`
- `document_summary`
- `research_analysis`
- `investment_opinion`
- `personalized_advice_request`
- `high_risk_request`
- `unknown`

以及这些动作类型：

- `answer_directly`
- `search_documents`
- `summarize_with_citations`
- `ask_clarifying_question`
- `safe_refusal`
- `handoff_to_human`

### 主链路改造

#### 1. 新增 decisioning 模块

新增：

- `app/agent/decisioning.py`

作用：

1. `plan_next_step`
   - 让模型先输出严格 JSON 决策对象
   - 解析成 `AgentDecision`

2. `generate_answer_from_tool`
   - 当决策需要检索时，用结构化决策 + 工具返回结果生成最终答复

#### 2. agent_loop 切换为两阶段

`app/agent/agent_loop.py` 从原来的：

```text
用户输入 -> 模型直接决定是否调工具 -> 工具 -> 最终回答
```

改成：

```text
用户输入
  -> 结构化决策（AgentDecision）
  -> 场景级 Policy 审批
  -> 可选工具调用
  -> 最终答复生成
  -> 合规检查
```

这一步是第三步开发的核心。

### Policy 升级

原来 `policy` 只校验：

- 工具是否允许
- 参数是否合法

现在新增：

- `evaluate_agent_decision`

并新增 `ScenePolicyResult`。

新的 policy 开始看“场景”，而不只是“工具参数”。

当前规则包括：

1. `investment_opinion / personalized_advice_request / high_risk_request`
   - 一律降级
   - 不允许直接给投资建议
   - 转为 `handoff_to_human`

2. `unknown`
   - 不直接回答
   - 转为 `ask_clarifying_question`

3. `fact_lookup / research_analysis / document_summary`
   - 允许只读研究链路

4. `document_summary` 且 `has_sufficient_evidence=False`
   - 不允许直接总结
   - 要求先补证据或澄清

5. `response.is_personalized=True`
   - 即便不是 advice intent，也要降级，避免系统悄悄滑向个性化建议

### Audit 增强

为了让第三步的结构化决策可以复盘，本轮为 `audit_events` 增加字段：

- `decision_payload`
- `intent_type`
- `action_type`
- `confidence`
- `citations`
- `fallback_reason`

对应修改：

- ORM：`app/db/models.py`
- Repo：`app/db/audit_repo.py`
- Service：`app/audit/service.py`
- Migration：`0f2141d6f4a2_add_decision_fields_to_audit.py`

这样现在审计不再只知道“调了什么工具”，还知道：

- 模型把场景理解成什么
- 原本想做什么动作
- 置信度是多少
- 证据是否充分
- 为什么被降级

### 本轮实际改动

**新增模块**

- `app/models/decision.py`
- `app/agent/decisioning.py`

**Policy 扩展**

- `app/policy/models.py`
- `app/policy/service.py`
- `app/policy/__init__.py`

**主循环改造**

- `app/agent/agent_loop.py`

**审计字段扩展**

- `app/db/models.py`
- `app/db/audit_repo.py`
- `app/audit/service.py`
- `migrations/versions/0f2141d6f4a2_add_decision_fields_to_audit.py`

**新增测试**

- `tests/test_decision.py`

**更新测试**

- `tests/test_rag.py`
- `tests/test_compliance.py`
- `tests/test_memory.py`
- `tests/test_policy.py`

### 验证结果

执行：

```bash
pytest
```

结果：

```text
69 passed in 0.94s
```

### 当前项目状态

做到这一步后，项目已经具备三层控制能力：

1. **隔离层**
   - 请求身份上下文
   - 会话隔离
   - 文档 ownership
   - 检索范围过滤

2. **执行控制层**
   - 结构化决策 schema
   - 场景级 policy
   - 工具级 policy
   - 输出前合规阻断

3. **可追溯层**
   - user message
   - decision
   - scene policy
   - tool call
   - tool result
   - final response
   - error

换句话说，当前系统已经从“RAG 投研助手”进化到：

**一个具备结构化决策、场景审批、只读工具受控执行和审计留痕的研究型金融 Agent 雏形。**

### 下一步建议（Step 11）

下一步我建议优先做两件事：

1. **审计查询与 badcase 回放接口**
   - 按 `trace_id / session_id` 查询整条链路
   - 为复盘、人工复核和运营监控提供入口

2. **人工复核与高风险降级工作流**
   - 把 `handoff_to_human` 变成真正的队列或待办项
   - 为未来接适当性、风险等级、人工审批留出主流程位置
