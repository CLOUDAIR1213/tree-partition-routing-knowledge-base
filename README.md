# 三分区知识库

本地运行的企业知识库 MVP。系统把 PDF、DOCX、TXT 和 Markdown 文档解析为 Chunk，经人工确认最终分区后写入财务、人事或技术的 `document -> section -> chunk` 三层 txtai 树索，并支持手动单分区或 LLM 自动单/双分区证据问答。

## 开发前先读文档

编码 Agent 和开发者从 [`docs/README.md`](docs/README.md) 开始，根据任务选择端到端功能文档，再检查代码。不要直接从历史规格书开始写代码。

| 要修改的能力 | 首要文档 |
| --- | --- |
| 聊天、路由、检索、LLM、引用 | [`docs/features/chat-and-routing.md`](docs/features/chat-and-routing.md)、[`docs/features/tree-index-retrieval.md`](docs/features/tree-index-retrieval.md) |
| 上传、解析、Chunking | [`docs/features/document-ingestion.md`](docs/features/document-ingestion.md) |
| 预览、审核、索引写入 | [`docs/features/document-review-indexing.md`](docs/features/document-review-indexing.md) |
| 启动、健康、错误、Request ID | [`docs/features/system-runtime.md`](docs/features/system-runtime.md) |
| SQLite、文件目录、txtai | [`docs/architecture/data-and-storage.md`](docs/architecture/data-and-storage.md) |
| OpenAPI 和前端生成类型 | [`docs/contracts/api-conventions.md`](docs/contracts/api-conventions.md) |

## 当前能力

- 文档内容与签名校验、重复检测、正文解析和可配置 Chunking。
- 文档详情、分页 Chunk 预览、批准/拒绝和唯一最终分区。
- 三个分区各自独立的 document、section、chunk 树索，以及 SQLite `ready + confirmed_partition` 二次校验。
- 本地敏感输入阻断和邮箱、手机号、私网 IP 脱敏。
- 用户手动单分区路由优先。
- Router LLM 自动 single/composite/clarify，复合路由最多两个分区。
- Answer LLM 证据回答、Citation 白名单和抽取式降级。
- 统一错误体、Request ID、健康检查和 OpenAPI 生成契约。

当前没有认证、审核授权、多租户、异步任务、OCR、通用失败重试 API 或生产级可观测性，只适合可信本地演示环境。tree-only 代码已完成，但真实业务数据迁移和旧 Flat 运行数据清理仍需按迁移文档在停服、备份和观察期条件下执行。

## 快速启动

环境要求：Python 3.11/3.12、uv、Node.js 20+、npm 10+。

首次安装：

```powershell
uv sync --group dev
Copy-Item .env.example .env
Set-Location frontend
npm install
```

启动后端：

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload --reload-dir app
```

启动前端：

```powershell
Set-Location frontend
npm run dev
```

| 服务 | 地址 |
| --- | --- |
| 树状版本前端 | `http://127.0.0.1:5174` |
| Swagger | `http://127.0.0.1:8001/docs` |
| OpenAPI | `http://127.0.0.1:8001/openapi.json` |
| 健康检查 | `http://127.0.0.1:8001/api/v1/health` |

配置、模型 API、前端代理和故障排查见 [`docs/operations/local-development.md`](docs/operations/local-development.md)。不要提交 `.env` 或把真实密钥写入文档。

## 页面

| 路径 | 功能 |
| --- | --- |
| `/` | 自动/手动分区聊天和引用 |
| `/knowledge/upload` | 文档上传和初始分区 |
| `/knowledge/review/:documentId` | 文档状态、Chunk 预览和审核 |

## 代码健康

后端：

```powershell
uv run pytest -q
```

前端：

```powershell
Set-Location frontend
npm run build
npm test
```

API 变化后按 [`docs/contracts/api-conventions.md`](docs/contracts/api-conventions.md) 导出 OpenAPI 并生成前端类型。测试范围、隔离规则和最近一次验证结果见 [`docs/testing/strategy.md`](docs/testing/strategy.md)。

## 目录

```text
app/             FastAPI、服务、模型和数据库
contracts/       生成的 OpenAPI 审查快照
data/            运行期数据目录和演示源数据
docs/            现行功能文档、共享专题和历史归档
frontend/        React 前端、生成类型和前端测试
scripts/         OpenAPI 导出和显式 seed 脚本
tests/           临时 SQLite/Fake 驱动的后端测试
```

`docs/archive/` 只保存历史规格和开发计划，不代表当前实现。
