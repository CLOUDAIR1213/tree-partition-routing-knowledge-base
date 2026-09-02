# 系统总览

> 最近核对：2026-09-02  
> 代码基线：`61c551f` 加当前工作树快照

## 1. 系统目标

本项目是本地运行的三分区企业知识库 MVP。它把上传文档经过解析、Chunking 和人工审核后写入财务、人事或技术索引，再通过手动或 LLM 路由执行受分区约束的检索问答。

当前是本地演示系统，不具备身份认证、角色授权、多租户、后台任务队列或生产级可观测性。

## 2. 技术栈

| 层 | 技术 | 入口 |
| --- | --- | --- |
| 前端 | React、TypeScript、React Router、Vite | `frontend/src/main.tsx`、`frontend/src/App.tsx` |
| HTTP API | FastAPI、Pydantic | `app/main.py`、`app/api/` |
| 业务服务 | Python async 服务层 | `app/services/` |
| 元数据 | SQLAlchemy Async、SQLite、aiosqlite | `app/db/` |
| 检索索引 | 三个独立 txtai Embeddings 实例 | `app/services/index_registry.py` |
| 外部模型 | OpenAI-compatible Chat Completions | `app/services/llm.py` |
| API 契约 | FastAPI OpenAPI、openapi-typescript | `contracts/openapi.json`、`frontend/src/api/generated.ts` |

## 3. 组件关系

```text
Browser
  -> React pages and feature components
  -> frontend/src/api/client.ts
  -> /api/v1/*
  -> FastAPI route
  -> service orchestration
       -> SQLite metadata and Chunk text
       -> raw/staging files
       -> one or two partition-specific txtai indexes
       -> optional OpenAI-compatible Router/Answer model
  -> Pydantic response + X-Request-ID
  -> React state and UI
```

依赖方向保持为 `api -> services -> models/db/core`。前端只通过 API Client 访问后端，不直接读取业务数据目录。跨端字段以 OpenAPI 为契约，不在页面中手写重复接口类型。

## 4. 前端页面

| 路由 | 页面 | 主要能力 |
| --- | --- | --- |
| `/` | `ChatPage` | 自动或手动分区问答、引用展示、本地持久会话 |
| `/knowledge/upload` | `UploadPage` | 文件选择、初始分区、标题和上传 |
| `/knowledge/review/:documentId` | `ReviewPage` | 状态读取、Chunk 分页预览、批准或拒绝 |
| `/404`、`*` | `NotFoundPage` | 无效路由处理 |

`AppShell` 提供侧栏、顶部栏和 `ChatSessionProvider`。会话运行状态位于 React，版本化快照写入浏览器 `localStorage`；刷新后恢复，用户可以确认删除单条会话或清空全部本地历史。

## 5. 后端模块

| 模块 | 职责 |
| --- | --- |
| `app/main.py` | 应用工厂、生命周期、CORS、Request ID 和异常处理 |
| `app/api/chat.py` | 构造 Router、Answerer 和 ChatService，暴露聊天端点 |
| `app/api/documents.py` | 文档上传、列表、详情、预览和审核端点 |
| `app/api/health.py` | SQLite、索引、Router 和 Answer 配置状态 |
| `app/services/ingestion.py` | 文档接入编排 |
| `app/services/review.py` | 审核和索引写入编排 |
| `app/services/chat.py` | 安全、路由、检索、回答和降级编排 |
| `app/services/retriever.py` | txtai 召回后使用 SQLite 校验 Chunk 和分区 |
| `app/services/index_registry.py` | 三个独立索引的加载、查询、写入和保存 |

## 6. 三条核心数据流

### 文档接入

```text
UploadPage -> POST /documents -> FileStorage
-> DocumentTable(uploaded -> parsing)
-> Parser -> SectionChunker
-> ChunkCandidateTable
-> DocumentTable(pending_review)
-> staging parse.json
```

上传阶段不会写入任何 txtai 索引。

### 文档审核与索引

```text
ReviewPage -> GET detail + preview
-> POST review
-> pending_review optimistic claim
-> reject: rejected, no index write
-> approve: indexing -> selected txtai index -> verify
-> ready, or failed + index compensation
```

### 聊天问答

```text
ChatPage -> POST /chat -> InputSafetyGuard
-> partition_hint? user single route : Router LLM
-> single | composite(max 2) | clarify
-> partition-specific txtai search
-> SQLite ready + confirmed_partition validation
-> Answer LLM with retrieved evidence, or extractive fallback
-> citation whitelist
-> grouped citations in frontend
```

## 7. 关键边界

- 用户显式选择分区时跳过 Router LLM，只检索一个索引。
- 自动复合路由最多访问两个不同分区，不访问第三个索引。
- txtai 只负责召回；文档是否 `ready`、最终分区和展示正文以 SQLite 为准。
- `pending_review` 文档对聊天不可见。
- Answer LLM 只能引用本次召回的 Chunk ID。
- 上传原文件、解析快照、SQLite 和 txtai 索引是不同持久化边界，不应当作一个事务。
- 所有 HTTP 响应携带 `X-Request-ID`；非 2xx 使用统一错误体。

## 8. 配置与生命周期

应用启动时创建所需目录、初始化 SQLite、将遗留 `indexing` 状态标记为 `failed`、加载三个索引，并按环境变量构造可选 LLM Provider。应用关闭时清空索引注册表并释放数据库连接。

配置详情和启动命令见[本地开发](../operations/local-development.md)。

## 9. 变更入口

修改前先从[文档导航](../README.md)选择功能文档。共享 Schema、配置、API Client、公共组件、数据库表和 IndexRegistry 可能影响多个功能，必须按功能文档中的 `shared` 规则检查消费者。

## 10. 已知架构限制

- 没有认证和审核授权，只适合可信本地环境。
- 上传、解析和索引写入是同步请求，较大文档可能长时间占用请求。
- SQLite 没有迁移工具，当前使用 `create_all`，Schema 演进能力有限。
- 前端会话只在当前浏览器本地持久化，没有账号隔离、服务端存储或跨设备同步。
- 未实现删除、重新审核、失败重试和索引重建 API。
- 真实 Router/Answer 模型质量和超时表现尚未验证。
