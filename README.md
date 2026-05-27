# Investment Research Agent

一个面向证券研究与投研问答场景的后端 AI Agent 服务。项目支持文档上传、异步解析、向量检索、受控工具调用、流式对话、合规拦截，以及基于租户和用户的访问隔离。

## What It Does

- 上传 PDF、Excel、HTML、TXT 等研究资料并异步入库
- 解析文档、切块、Embedding，并写入 Qdrant
- 基于 RAG 的文档问答与流式 SSE 输出
- 通过结构化决策层控制是否直答、追问或检索
- 通过 policy 层限制工具调用和场景行为
- 通过 audit 链路记录用户请求、决策、工具调用和最终响应
- 通过 `tenant_id + user_id` 做文档归属隔离和会话隔离

## Tech Stack

- FastAPI
- PostgreSQL
- Redis
- Qdrant
- Celery
- OpenAI-compatible LLM provider such as DeepSeek
- OpenAI `text-embedding-3-small`

## Architecture

```text
Client
  -> FastAPI API
  -> Request Context (tenant/user/request)
  -> Agent Decision Layer
  -> Policy Layer
  -> Optional Tool Call (search_documents)
  -> Compliance Check
  -> SSE / JSON Response

Document Upload
  -> PostgreSQL metadata
  -> Celery async pipeline
  -> Parser + Chunker + Embedder
  -> Qdrant vector store
```

核心目录：

- `app/api/v1/`：HTTP 接口
- `app/agent/`：Agent 决策、工具调用、主循环
- `app/policy/`：场景和工具策略控制
- `app/audit/`：审计事件记录
- `app/doc_pipeline/`：解析、切块、向量化
- `app/db/`：ORM 与仓储
- `app/memory/`：Redis 会话与摘要压缩
- `app/tasks/`：Celery 异步任务
- `tests/`：测试用例

## Key Features

### 1. Controlled Agent Flow

对话不是简单的“用户提问 -> LLM 回答”，而是：

```text
user message
-> structured decision
-> scene policy
-> optional tool policy
-> retrieval
-> final response
-> compliance gate
-> audit event
```

### 2. Scoped Access

所有受保护接口都要求请求头：

- `X-User-Id`
- `X-Tenant-Id`

系统会基于这两个值做：

- 文档访问隔离
- 会话命名空间隔离
- 审计归因

### 3. Asynchronous Document Pipeline

文档上传后会进入 Celery 任务，完成：

1. 文件解析
2. 文本/表格切块
3. Embedding 生成
4. Qdrant 写入
5. 文档状态更新

## Quick Start

### 1. Prepare env

复制配置文件：

```bash
cp .env.example .env
```

至少补齐这两个密钥：

- `LLM_API_KEY`
- `OPENAI_API_KEY`

### 2. Start infra with Docker Compose

```bash
docker compose -f docker/docker-compose.yml up --build
```

默认会启动：

- `app` on `:8000`
- `celery_worker`
- `postgres` on `:5432`
- `redis` on `:6379`
- `qdrant` on `:6333`

### 3. Open API docs

开发环境可访问：

- [http://localhost:8000/docs](http://localhost:8000/docs)
- [http://localhost:8000/redoc](http://localhost:8000/redoc)

## Local Development

如果你希望本地单独运行应用而不是用整套 Compose：

```bash
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Celery worker 可单独启动：

```bash
celery -A app.core.celery_app worker --loglevel=info --concurrency=2
```

## API Overview

### Health

- `GET /api/v1/health/ping`
- `GET /api/v1/health/readiness`

### Documents

- `POST /api/v1/documents/upload`
- `GET /api/v1/documents`
- `GET /api/v1/documents/{doc_id}`
- `DELETE /api/v1/documents/{doc_id}`

### Chat

- `POST /api/v1/chat/completions`
- `GET /api/v1/chat/sessions/{session_id}`
- `DELETE /api/v1/chat/sessions/{session_id}`

## Example Requests

### Upload a document

```bash
curl -X POST "http://localhost:8000/api/v1/documents/upload" \
  -H "X-User-Id: user-1" \
  -H "X-Tenant-Id: tenant-1" \
  -F "file=@/absolute/path/report.pdf"
```

### Ask a question

```bash
curl -X POST "http://localhost:8000/api/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user-1" \
  -H "X-Tenant-Id: tenant-1" \
  -d '{
    "session_id": "demo-session",
    "message": "总结这份研报里对营收增长的判断",
    "stream": false
  }'
```

### Stream SSE response

```bash
curl -N -X POST "http://localhost:8000/api/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user-1" \
  -H "X-Tenant-Id: tenant-1" \
  -d '{
    "session_id": "demo-session",
    "message": "根据已上传文档分析贵州茅台营收趋势",
    "stream": true
  }'
```

可能返回的 SSE 事件类型：

- `tool_start`
- `tool_done`
- `text`
- `compliance`
- `done`
- `error`

## Testing

运行测试：

```bash
pytest -q
```

当前主测试集覆盖了：

- 健康检查
- 聊天接口
- 文档接口
- RAG 检索
- 决策层
- policy 层
- 内存压缩
- 合规规则

## Current Status

当前版本已经包含：

- 结构化决策 `decisioning`
- 场景与工具策略控制 `policy`
- 审计事件链路 `audit`
- 文档 owner 字段与查询过滤
- 会话 scoped session id
- 与之配套的 Alembic migration 和测试

## Notes

- 当前项目仍是后端服务，没有前端页面。
- 请求身份目前通过 Header 显式传入，尚未接入正式认证系统。
- GitHub 仓库首页是否展示 `README`，取决于 `README.md` 是否已经提交并推送到远端默认分支。

