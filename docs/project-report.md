# 三分区知识库项目理解与汇报报告

> 用途：个人学习、项目汇报、架构走查与后续维护。
> 最近核对：2026-09-04。
> 代码基线：`6e5a78c`（核对时工作树干净）。
> 事实依据：现行 `docs/`、实际代码与测试、`contracts/openapi.json`、前端生成类型；`docs/archive/` 仅作历史背景。

## 1. 项目结论

这是一个本地或受信任内网运行的企业知识库 MVP。系统将 PDF、DOCX、TXT 和 Markdown 文档解析为 Chunk，经人工确认后写入财务（`finance`）、人事（`hr`）或技术（`tech`）之一的独立 txtai 索引。用户提问时，系统通过手动选区或 LLM 自动路由访问一个或两个分区，再用已经审核的 Chunk 生成带引用的回答。

它不是“把所有文件直接发给大模型”的系统。项目把事实、召回、生成和展示拆成不同边界：

```text
文件原件与解析快照       -> 文件系统
状态、最终分区、Chunk 正文 -> SQLite（业务权威）
语义召回                 -> 三个独立 txtai 索引
路由与回答生成            -> 可选 OpenAI-compatible LLM
公开信息兜底              -> 可选 Tavily Search
用户界面与本地会话         -> React + localStorage
跨端数据约束              -> FastAPI OpenAPI + TypeScript 生成类型
```

系统最重要的设计原则是：未经审核的知识不能进入问答；txtai 命中不等于证据有效；只有 SQLite 中 `ready` 且最终分区与当前检索分区一致的 Chunk 才能回答用户。

## 2. 当前能力和系统边界

### 2.1 已实现能力

- 文档上传、扩展名与内容签名校验、重复内容检测、四种格式解析和 Chunking。
- 解析质量报告、标题识别率、空白页/表格/Chunk 长度诊断，以及非权威关键词分区建议。
- 知识库目录、状态/有效分区/标题筛选、分页和全状态详情。
- Chunk 按原文 `chunk_index` 顺序完整预览。
- 人工批准、拒绝、已入库文档改分区、退回重新审核和单文档删除。
- 三个物理独立的 txtai 索引，以及跨 SQLite/文件/txtai 操作的状态抢占和补偿。
- 手动单分区、自动单分区、自动双分区和澄清路由。
- 内部证据回答、Citation 白名单、抽取式降级、受限 Markdown 展示和分阶段耗时。
- 用户显式授权后的受限 Tavily 联网兜底。
- 浏览器本地多会话、跨会话并发请求和请求结果归属隔离。
- 统一错误体、Request ID、健康检查、OpenAPI 快照和前端生成类型。
- 开发双端口模式，以及 FastAPI 托管前端构建产物的受信任内网单端口模式。

### 2.2 明确不具备

当前没有登录认证、角色授权、多租户、分区权限、多人审批、不可变审计、后台任务队列、批量管理、失败状态普通重试、重新解析、全库索引重建、数据库迁移、服务端聊天历史、SSE/WebSocket、生产监控或公网部署方案。

因此当前系统适合个人演示和受信任私网验证，不适合直接承载真实敏感企业知识或公开互联网访问。

### 2.3 文档与当前代码的差异

部分现行文档头部仍写 `61c551f` 加工作树快照，测试策略中仍有“OpenAPI 共 7 个 operations”的旧记录；当前 Git HEAD 为 `6e5a78c`，工作树干净，实际 OpenAPI 包含 10 个 HTTP operations。本文以当前代码、测试和生成契约为准，并将旧数字视为待统一更新的文档元数据，而不是当前系统事实。

## 3. 总体架构

### 3.1 技术栈

| 层 | 技术 | 主要入口 | 边界 |
| --- | --- | --- | --- |
| 前端 | React、TypeScript、React Router、Vite | `frontend/src/main.tsx`、`App.tsx` | 只通过 API Client 访问后端 |
| HTTP | FastAPI、Pydantic | `app/main.py`、`app/api/` | 请求校验、路由、响应与 OpenAPI |
| 业务服务 | Python async services | `app/services/` | 流程编排，不负责页面展示 |
| 元数据 | SQLAlchemy Async、SQLite、aiosqlite | `app/db/` | 文档与 Chunk 的业务权威 |
| 检索 | txtai `Embeddings` | `index_registry.py` | 只做分区语义召回 |
| 模型 | httpx + OpenAI-compatible API | `llm.py` | Router/Answer 可替换 Provider |
| 搜索 | httpx + Tavily API | `web_search.py` | 仅零内部证据的受限兜底 |
| 契约 | OpenAPI、openapi-typescript | `contracts/openapi.json` | Python 与 TypeScript 字段同步 |

后端依赖方向是 `api -> services -> models/db/core`。页面不直接使用 SQLAlchemy、txtai 或文件目录；API 路由不直接承担复杂跨存储业务，而是调用服务层。

### 3.2 端到端调用方向

```text
Browser
  -> React Router
  -> Page（页面编排和局部状态）
  -> shared component（展示/输入）
  -> frontend/src/api/client.ts
  -> /api/v1/*
  -> FastAPI route + Pydantic request
  -> service orchestration
       -> AsyncSession / SQLite
       -> FileStorage
       -> IndexRegistry / txtai
       -> LLMProvider
       -> WebSearchProvider
  -> Pydantic response + X-Request-ID
  -> API Client 错误与运行时契约检查
  -> 页面状态和组件展示
```

内网单端口模式只在最前面多一层：FastAPI 读取 `frontend/dist` 并提供 SPA 与 `/assets`；页面仍通过同源 `/api/v1/*` 访问相同 API，不会绕开 API Client 或业务服务。

## 4. 每个界面的职责和边界

### 4.1 全局壳层 `AppShell`

| 项目 | 说明 |
| --- | --- |
| 负责 | 侧栏、顶部栏、主内容 Outlet、移动端侧栏开关、路由切换时关闭侧栏 |
| 复用 | `AppSidebar`、`TopBar`、`ChatSessionProvider`、React Router `Outlet` |
| 状态 | 只拥有布局级侧栏状态；聊天业务状态由 Provider 管理 |
| 不负责 | 文档请求、聊天路由、审核、索引、数据库状态 |

侧栏提供聊天会话导航和知识库入口。顶部栏根据当前页面提供导航动作。它们属于共享导航层，修改时必须同时检查聊天、知识库、上传、详情和移动端。

### 4.2 问答界面 `/`

主要文件是 `ChatPage.tsx`、`ChatComposer.tsx`、`MessageList.tsx`、`PartitionSelector.tsx` 和 `ChatSessionContext.tsx`。

| 负责 | 不负责 |
| --- | --- |
| 选择自动或手动分区、输入问题、控制联网授权 | 不在前端判断实际业务分区 |
| 固定本次请求所属的 conversation/message ID | 不把 conversation ID 发送给后端 |
| 调用 `knowledgeApi.chat()` 并把结果写回原会话 | 不直接调用 Router、txtai 或模型 |
| 展示回答、引用、warning、澄清按钮和耗时 | 不自行生成答案或伪造 Citation |
| 在浏览器保存历史会话 | 不向 SQLite 保存聊天历史 |

单个会话有请求时不能再次提交，但不同会话可以并发请求。用户切换会话不会改变已发请求的归属；完成、失败和重试输入都写回请求创建时固定的会话。后端只处理一次独立问答，没有跨轮上下文。

助手回答可渲染标题、段落、列表、粗体、行内代码和链接；原始 HTML 与图片被跳过。用户问题和 warning 始终按纯文本展示，Citation 使用独立组件，模型 Markdown 不能伪造引用区。

### 4.3 知识库目录 `/knowledge`

主要文件是 `KnowledgeLibraryPage.tsx`、`KnowledgeFilters.tsx` 和 `KnowledgeDocumentTable.tsx`。

| 负责 | 不负责 |
| --- | --- |
| 展示文档目录、总数、分页和空态 | 不读取 txtai 文件或展示向量 |
| 按状态、有效分区、标题/原文件名筛选 | 不搜索 Chunk 正文 |
| 把 `q/status/partition/page` 保存在 URL | 不创建全局状态库 |
| 300ms 搜索防抖、请求序号防竞态、错误重试 | 不修改文档或索引 |
| 点击文档进入统一详情页 | 不通过列表响应判断索引实际文件状态 |

“有效分区”采用 `confirmed_partition` 优先，否则使用 `selected_partition`。列表的可检索展示由 `status === ready` 推导，事实来源是 SQLite 返回的文档元数据。

### 4.4 上传界面 `/knowledge/upload`

主要文件是 `UploadPage.tsx`、`UploadDropzone.tsx` 和 `PartitionSelector.tsx`。

| 负责 | 不负责 |
| --- | --- |
| 单文件选择、拖放、标题和初始分区输入 | 不支持批量上传 |
| 前端扩展名、非空、25 MB 预检 | 不替代服务端安全校验 |
| 调用 `documentsApi.upload()` | 不直接解析文件或生成 Chunk |
| 保留表单错误、提供重复文档入口 | 不自动批准或写入索引 |
| 成功后跳转统一详情页 | 不决定最终分区 |

前端 `partition` 是上传初选，审核时仍必须显式确认最终分区。未填写标题时，后端用安全化文件名去扩展名作为默认标题。

### 4.5 文档详情与审核 `/knowledge/documents/:documentId`

该页面由 `ReviewPage.tsx` 统一承担，不再只是审核页。旧地址 `/knowledge/review/:documentId` 只做重定向兼容。

| 状态 | 页面展示 | 允许的业务动作 |
| --- | --- | --- |
| `uploaded`、`parsing` | 元数据和处理状态 | 刷新、返回目录 |
| `pending_review` | 完整 Chunk、质量报告、建议分区 | 批准或拒绝 |
| `indexing`、`reindexing`、`deleting` | 进行中状态 | 刷新、返回目录 |
| `ready` | 可检索状态、完整 Chunk | 改分区、退回重新审核、删除、按分区返回问答 |
| `rejected`、`failed` | 原因和已有 Chunk | 删除 |

页面把详情与 Chunk 预览作为两个独立请求：详情成功但预览失败时，仍保留元数据，只在 Chunk 区报错；完整预览不可用时禁止批准。解析质量和关键词建议只辅助人工判断，不会自动选择最终分区。

删除、改分区、退回重新审核均通过确认对话框触发。页面只表达用户意图，跨 SQLite、文件与 txtai 的一致性由后端 `DocumentManagementService` 负责。

### 4.6 404 与运行状态界面

`NotFoundPage` 只处理无效前端路由。系统没有独立健康状态页面；`systemApi.health()` 已存在，但当前 UI 未调用。API 故障由各业务页面的错误状态显示，运维人员通过 `/api/v1/health` 或 Swagger 检查服务。

## 5. 前端模块边界

| 模块 | 对外接口 | 复用者 | 边界 |
| --- | --- | --- | --- |
| `frontend/src/api/client.ts` | `apiFetch`、`knowledgeApi`、`documentsApi`、`systemApi` | 所有页面 | 统一 URL、JSON/FormData、超时、错误体与聊天运行时校验 |
| `frontend/src/api/generated.ts` | OpenAPI 生成类型 | `types.ts` | 生成文件，不承载手写业务逻辑 |
| `frontend/src/api/types.ts` | 生成类型别名和前端适配类型 | 页面、组件、会话 | 不复制后端字段定义 |
| `ChatSessionContext` | 会话 CRUD、消息写入、按会话运行态 | ChatPage、Sidebar | 只保存浏览器会话，不代表服务端会话 |
| `PartitionSelector` | `Partition | null` 选择 | Chat、Upload、Review | 聊天允许自动，上传/审核只允许明确分区 |
| `DocumentStatusBadge` | 状态到标签映射 | 目录、详情 | 只展示，不推进状态机 |
| `ChunkPreviewList` | 顺序 Chunk 分页展示 | 详情/审核 | 不进行相关度排序或全文检索 |
| `ParseQualitySummary` | 质量指标和建议展示 | 详情/审核 | 建议必须标为非权威 |

前端页面可以复用组件和 API，但不能复用后端内部对象。例如 `IndexRegistry`、`AsyncSession` 和 `FileStorage` 永远不应出现在浏览器代码中。

## 6. 后端模块边界

### 6.1 API 层

| 模块 | 职责 | 不负责 |
| --- | --- | --- |
| `app/api/chat.py` | 接收 ChatRequest、按 Settings 装配 Router/Answer/Search、调用 ChatService | 不直接查询 SQLite 或 txtai |
| `app/api/documents.py` | 文档端点、Query/Path/Form 参数、响应模型转换 | 不直接实现跨存储补偿 |
| `app/api/health.py` | SQLite、索引、Provider 配置状态 | 不主动调用外部模型探活 |
| `app/api/dependencies.py` | 从 `app.state` 提供 session/registry/provider | 不创建业务全局单例 |

API 层负责协议适配。复杂状态转换必须在服务层，否则同一规则容易在不同端点间重复或漂移。

### 6.2 文档服务

| 服务 | 输入/输出 | 主要复用接口 | 责任边界 |
| --- | --- | --- | --- |
| `IngestionService` | 上传字节 -> pending_review 文档与 Chunk | FileStorage、DocumentParser、SectionChunker、PartitionSuggester、AsyncSession | 不写正式索引 |
| `ReviewService` | ReviewRequest -> rejected 或 ready | AsyncSession、IndexRegistry | 只处理 pending_review 的批准/拒绝 |
| `DocumentManagementService` | ready/稳定状态管理请求 -> 新状态或删除 | AsyncSession、FileStorage、IndexRegistry | 处理删除、改分区、重新审核和补偿 |
| `FileStorage` | 原文件、parse.json | pathlib/文件系统 | 不决定文档状态和分区 |
| `StandardDocumentParser` | 文件路径+MIME -> Section+诊断 | pypdf、python-docx | 不写数据库、不切 Chunk |
| `SectionChunker` | Section -> ChunkCandidateData | 本地 Token 近似和 SHA-256 | 不生成向量、不保存索引 |
| `KeywordPartitionSuggester` | 解析正文 -> 建议+置信度+原因 | 固定关键词表 | 不改变 selected/confirmed partition |

### 6.3 问答服务

| 服务 | 输入/输出 | 主要复用接口 | 责任边界 |
| --- | --- | --- | --- |
| `ChatService` | ChatRequest -> ChatResponse | Safety、Router、Retriever、Answerer、Search | 总编排和降级，不直接实现传输 |
| `InputSafetyGuard` | 原问题 -> safe/redacted/blocked | 本地规则 | 不是完整 DLP 系统 |
| `LLMRouter` | 安全问题 -> LLMRoutePlan | `LLMProvider.complete()` | 只决定子查询，不搜索索引 |
| `Retriever` | 分区子查询 -> RetrievalGroup | `IndexRegistry.search()`、AsyncSession | 召回后必须回查 SQLite |
| `LLMAnswerer` | 问题+内部证据 -> answer+Chunk IDs | `LLMProvider.complete()` | 只能引用本轮白名单 Chunk |
| `LLMWebAnswerer` | 问题+搜索结果 -> answer+URLs | `LLMProvider.complete()` | 与内部证据回答隔离 |
| `TavilySearchProvider` | 合规问题 -> WebSearchResult | Tavily HTTP API | 不抓取结果网页正文 |

### 6.4 基础设施模块

| 模块 | 作用 | 被谁复用 |
| --- | --- | --- |
| `Database` | Async engine、session factory、建表、启动恢复 | 全部需要 SQLite 的 API/服务 |
| `DocumentTable` | 文档生命周期与审核事实 | 接入、审核、管理、检索、目录 |
| `ChunkCandidateTable` | 正文、Embedding 文本与引用定位 | 接入、审核、管理、预览、检索 |
| `IndexRegistry` | 三索引加载、写入、删除、验证、查询、健康 | 审核、管理、聊天、健康检查 |
| `Settings` | 目录、模型、检索、上传、联网、内网托管配置 | app lifespan 和各 API 装配 |
| Pydantic schemas/enums | 请求、响应、内部结构和不变量 | API、服务、OpenAPI、前端生成类型 |

## 7. “知识库复用了什么接口”

这里的“接口”需要分成四类理解。

### 7.1 复用的前端业务接口

前端所有知识库页面复用同一个 `documentsApi`，底层再复用 `apiFetch<T>()`：

| 前端方法 | HTTP | 使用页面 |
| --- | --- | --- |
| `documentsApi.list()` | `GET /documents` | 知识库目录 |
| `documentsApi.upload()` | `POST /documents` | 上传页 |
| `documentsApi.get()` | `GET /documents/{id}` | 详情页 |
| `documentsApi.preview()` | `GET /documents/{id}/preview` | 详情/审核页 |
| `documentsApi.review()` | `POST /documents/{id}/review` | 审核页 |
| `documentsApi.changePartition()` | `POST /documents/{id}/partition` | ready 详情页 |
| `documentsApi.reopenReview()` | `POST /documents/{id}/reopen-review` | ready 详情页 |
| `documentsApi.delete()` | `DELETE /documents/{id}` | 稳定状态详情页 |

目录、上传和详情不是各写一套 fetch。它们复用同一个请求封装、ApiError/ApiTimeoutError、Request ID 展示规则、超时策略和 OpenAPI 类型。

聊天页复用 `knowledgeApi.chat()`，健康接口通过 `systemApi.health()` 暴露。三组对象都使用 `apiFetch`，因此 API Base URL、Abort 超时、JSON 错误解析和 FormData boundary 行为保持一致。

### 7.2 复用的后端内部接口

这些不是 HTTP，而是模块之间的稳定调用面：

| 内部接口 | 方法 | 复用位置 |
| --- | --- | --- |
| `IndexRegistry` | `load_all/get/upsert_and_save/delete_and_save/verify/verify_absent/search/health` | Review、DocumentManagement、Retriever、health、lifespan |
| `FileStorage` | `validate_and_store/write_parse_snapshot/read_parse_snapshot/remove_document` | Ingestion、详情质量读取、DocumentManagement |
| `AsyncSession` | `select/update/delete/commit/rollback` | 全部文档流程和 Retriever 二次校验 |
| `LLMProvider` Protocol | `complete(model, system_prompt, user_prompt)` | LLMRouter、LLMAnswerer、LLMWebAnswerer；具体 Provider 固定请求 JSON 输出 |
| `WebSearchProvider` Protocol | `search(query, max_results)` | ChatService |
| `DocumentParser` Protocol | `parse(path, mime_type)` | 标准解析抽象；当前 Ingestion 直接使用具体解析器的 `parse_with_diagnostics()` 获取附加质量指标 |

`ReviewService` 与 `DocumentManagementService` 复用相同 `IndexRegistry`，因此批准、改分区、重新审核和删除使用相同的索引写入/删除/验证语义。`Retriever` 也复用同一 Registry 的查询接口，但它只有只读权限，并在结果后增加 SQLite 权威校验。

### 7.3 复用的第三方库接口

| 能力 | 第三方接口 | 项目封装 | 说明 |
| --- | --- | --- | --- |
| 向量索引 | txtai Python `Embeddings` | `IndexRegistry` | 进程内库接口，不是独立 HTTP 服务 |
| 元数据 | SQLAlchemy Async ORM | `Database`、tables、services | SQLite 是默认数据库实现 |
| PDF | pypdf | `StandardDocumentParser` | 按页提取文本和空白页诊断 |
| DOCX | python-docx | `StandardDocumentParser` | 按 Heading 与原始块顺序提取 |
| HTTP 服务 | FastAPI/Pydantic | `app/main.py`、`app/api`、schemas | 同时生成 OpenAPI |
| 外部 HTTP | httpx | LLM/Search Provider | 统一异步请求和超时 |
| Markdown | react-markdown + remark-gfm | `MessageList` | 只用于 assistant 受限内容 |

### 7.4 复用的外部服务接口

| 外部服务 | 实际调用 | 用途 | 是否必须 |
| --- | --- | --- | --- |
| OpenAI-compatible | `POST <LLM_BASE_URL>/chat/completions` | Router、内部 Answer、Web Answer | 可选；手动路由和抽取式回答可继续工作 |
| Tavily | `POST WEB_SEARCH_BASE_URL`，默认 Search API | 零内部证据且用户授权后的公开搜索 | 可选，默认关闭 |

项目复用的是 OpenAI-compatible Chat Completions 协议，不绑定某一个模型厂商。Router 和 Answer 可以配置不同模型名，但共享同一传输 Provider。Tavily Key 与 LLM Key 完全独立。

### 7.5 复用的跨端契约接口

```text
FastAPI routes + Pydantic schemas
  -> scripts/export_openapi.py
  -> contracts/openapi.json
  -> openapi-typescript
  -> frontend/src/api/generated.ts
  -> frontend/src/api/types.ts
  -> frontend/src/api/client.ts
```

这条链是前后端真正共享的“字段接口”。后端 Schema 是源，OpenAPI 是导出审查快照，TypeScript 是生成消费者。两个生成文件都不能手工修改。

## 8. 业务流程一：文档接入

```text
UploadPage
  -> documentsApi.upload(FormData)
  -> POST /api/v1/documents
  -> FileStorage 校验并保存 raw
  -> documents: uploaded -> parsing
  -> Parser: Section + diagnostics
  -> Chunker: stable chunks + embedding_text
  -> KeywordPartitionSuggester
  -> SQLite chunk_candidates
  -> staging parse.json
  -> documents: pending_review
  -> UploadDocumentResponse
  -> /knowledge/documents/{id}
```

服务端重新检查大小、扩展名、内容签名和 UTF-8，前端预检只是体验优化。重复判断使用文件内容 SHA-256；非 rejected/failed 的相同内容会返回 `DUPLICATE_DOCUMENT`。

PDF 按页生成 Section；DOCX 按 Heading 层级并保持段落/表格原始交错顺序；Markdown 按标题层级且保留代码围栏；TXT 先作为单 Section。Chunker 生成稳定 ID、正文和包含文档/章节上下文的 `embedding_text`。质量报告和建议写进 `parse.json`，并通过上传、详情和预览响应展示。

接入完成只能是 `pending_review`，不能直接 `ready`，也不能写 txtai。

## 9. 业务流程二：审核与首次索引

```text
ReviewPage
  -> get + preview
  -> 人工检查完整 Chunk 和质量报告
  -> review(approve/reject)

approve:
  pending_review --条件更新--> indexing
  -> IndexRegistry.upsert_and_save(confirmed_partition)
  -> IndexRegistry.verify(全部 Chunk)
  -> chunk_candidates.indexed_at
  -> ready

reject:
  pending_review --条件更新--> rejected
  -> 不写索引
```

批准时 `confirmed_partition` 必填。关键词建议不会自动填充最终分区。条件更新保证并发审核最多一个请求取得状态。

SQLite 与 txtai 没有共同事务。写索引或验证失败时，服务尝试删除本次全部 Chunk ID，并把文档设为 `failed`；补偿结果进入安全错误信息。当前生产 Registry 已逐个验证全部 Chunk，不再只抽查第一条。

## 10. 业务流程三：知识文档管理

### 10.1 更改分区

```text
ready -> reindexing
-> 把全部 Chunk 写入并验证新分区
-> 清理另外两个分区并 verify_absent
-> 更新 confirmed_partition / indexed_at / 审核字段
-> ready
```

若失败，服务尝试删除新分区内容并恢复旧分区唯一索引；补偿成功时保持旧分区，补偿失败时标记 `failed`。页面不能直接改 SQLite 分区字段，因为那会造成索引与元数据不一致。

### 10.2 退回重新审核

```text
ready -> reindexing
-> 从三个索引删除全部 Chunk
-> verify_absent
-> confirmed_partition = null
-> indexed_at = null
-> pending_review
```

回到待审核后，下一次批准仍复用 `ReviewService` 的标准首次索引流程。

### 10.3 删除文档

允许从 `pending_review`、`ready`、`rejected`、`failed` 删除：

```text
stable state -> deleting
-> 清理三个索引
-> 删除 raw/<document_id> 和 staging/<document_id>
-> 删除 documents
-> 外键级联删除 chunk_candidates
```

索引清理失败时保留文件和 SQLite，并标记 failed；索引已清理但文件/数据库删除失败时，也保留可再次删除的 failed 记录。失败状态不保证索引绝对无残留，但聊天会因为状态不是 ready 而忽略该文档。

## 11. 业务流程四：聊天问答

```text
ChatPage -> knowledgeApi.chat()
  -> InputSafetyGuard
  -> partition_hint?
       yes: manual 单分区，跳过 Router
       no: LLMRouter -> single/composite/clarify
  -> Retriever.search_groups_with_timings()
  -> txtai score threshold
  -> SQLite ready + confirmed_partition 校验
  -> 有内部证据？
       yes: LLMAnswerer；失败时抽取式回答
       no: 满足严格条件时 Tavily + LLMWebAnswerer
  -> Chunk ID 或 URL 白名单
  -> ChatResponse + timing
```

### 11.1 路由边界

| 路由 | 规则 | 索引访问 |
| --- | --- | --- |
| manual | `partition_hint` 有值，用户决定优先 | 一个指定分区 |
| single | Router 判断单一业务主题 | 一个分区 |
| composite | 两个可独立检索的业务事项 | 恰好两个不同分区 |
| clarify | 信息不足、歧义或三分区问题 | 不访问索引 |

公司简介、组织、主营业务、使命愿景、办公地点和联系渠道默认属于 HR；同时包含独立财务/技术事项时才允许复合路由。Router 严格解析 JSON，错误时最多修复一次；不可用时降级为 clarify，而不是猜测分区。

### 11.2 检索边界

Retriever 从 txtai 得到 Chunk ID 和分数后，先过滤低于默认 `0.5` 的命中，再回查 SQLite。只有 `documents.status=ready` 且 `confirmed_partition` 等于当前分区的 Chunk 可进入 RetrievalHit。正文、标题、章节和页码以 SQLite 为准，不信任索引中的副本。

详情页 Chunk 顺序是原文顺序；聊天命中顺序是语义相关度顺序。两者用途不同，页面必须避免混淆。

### 11.3 回答与引用边界

Answer LLM 只能看安全问题和本轮命中证据，只能返回白名单内 Chunk ID。Provider 不可用时，每个分区抽取第一条有效 Chunk 组成降级回答；内部 Answer 失败不会转向联网。若回答引用为空或越界，系统丢弃草稿并返回不可回答。

### 11.4 联网边界

必须同时满足 `allow_web_fallback=true`、全部内部组为空、问题未脱敏且公开低风险、非 clarify、Provider 和 Web Answer 均配置。Tavily 只返回结构化搜索摘要，不抓取网页正文。

系统只接受公开 HTTPS URL，拒绝本机、私网、保留地址、带凭据 URL 和 `.local`，移除跟踪参数、片段、重复项和同域第三条以后结果。内部证据与网络证据不能混合。真实 Tavily 成功路径仍未验证，一次冒烟曾返回 HTTP 401。

## 12. 数据库和存储底座

### 12.1 存储职责

| 存储 | 默认位置 | 权威内容 | 不能承担的职责 |
| --- | --- | --- | --- |
| SQLite | `data/metadata/knowledge.db` | 状态、最终分区、Chunk 正文、审核字段 | 不存原始文件和向量索引 |
| Raw | `data/raw/<document_id>/` | 上传原始字节 | 不直接对前端开放 |
| Staging | `data/staging/<document_id>/parse.json` | Section、Chunk ID、质量报告 | 不是 HTTP 契约权威 |
| txtai | `data/indexes/<partition>/` | 分区语义召回结构 | 不决定 ready、最终分区或展示正文 |
| localStorage | `partitioned-kb.chat-session` | 当前浏览器历史和回答计时 | 不属于企业知识库数据库 |

### 12.2 `documents` 表

| 字段组 | 字段 | 语义 |
| --- | --- | --- |
| 标识 | `id` | `doc_` 加 24 位十六进制随机值 |
| 文件 | `original_filename`、`stored_path`、`mime_type`、`size_bytes`、`checksum_sha256` | 原文件与重复检测信息 |
| 分区 | `selected_partition`、`confirmed_partition` | 上传初选和审核终选 |
| 状态 | `status`、`error_code`、`error_message` | 生命周期与恢复信息 |
| 展示 | `title`、`chunk_count` | 文档标题和 Chunk 数 |
| 审核 | `reviewed_by`、`review_note`、`reviewed_at` | 最后一次审核/管理记录 |
| 时间 | `created_at`、`updated_at` | UTC 创建和更新时间 |

API 不返回 `stored_path` 或 checksum。`reviewed_by` 当前来自请求，没有身份认证保证，也不是不可抵赖审计。

### 12.3 `chunk_candidates` 表

| 字段组 | 字段 | 语义 |
| --- | --- | --- |
| 标识 | `id`、`document_id`、`chunk_index` | 稳定 ID、文档外键、原文顺序 |
| 内容 | `text`、`embedding_text` | 回答正文与索引增强文本 |
| 引用 | `title`、`section_path`、`page_start`、`page_end` | 引用定位 |
| 完整性 | `checksum_sha256`、`indexed_at` | 内容校验和与索引时间 |

`(document_id, chunk_index)` 唯一，文档删除时外键级联删除 Chunk。API 不返回 `embedding_text` 和 checksum。

### 12.4 当前状态机

```text
uploaded -> parsing -> pending_review -> indexing -> ready
                    |                 |          |
                    -> failed         -> failed  -> reindexing -> ready
                        ^                           |       |
pending_review -> rejected                          |       -> pending_review
                                                    -> failed

pending_review / ready / rejected / failed -> deleting -> deleted
                                                     |
                                                     -> failed

startup finds indexing/reindexing/deleting -> failed + recovery code
```

管理操作期间状态不是 ready，因此聊天天然忽略正在迁移或删除的文档。

## 13. HTTP API 如何传递

### 13.1 通用协议

- 业务前缀为 `/api/v1`，JSON 字段使用 snake_case。
- 上传使用 multipart/form-data，浏览器负责 boundary。
- 请求模型默认禁止额外字段并去除字符串首尾空白。
- 时间为 ISO 8601；SQLite 无时区值在 API 层补为 UTC。
- 分页使用 `limit/offset/total`。
- 每个响应头包含 `X-Request-ID`；统一错误体包含同一 ID。
- 普通请求默认 30 秒，聊天 100 秒，上传和审核/管理写操作 120 秒；有副作用 POST 不自动重试。

### 13.2 当前 10 个 operations

| 方法 | 路径 | 请求 | 响应 | 调用方 |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/chat` | `ChatRequest` | `ChatResponse` | ChatPage |
| GET | `/api/v1/documents` | status/partition/q/limit/offset | `DocumentListResponse` | KnowledgeLibraryPage |
| POST | `/api/v1/documents` | multipart | `UploadDocumentResponse` | UploadPage |
| GET | `/api/v1/documents/{id}` | path | `DocumentDetailResponse` | ReviewPage |
| DELETE | `/api/v1/documents/{id}` | path | `DeleteDocumentResponse` | ReviewPage |
| GET | `/api/v1/documents/{id}/preview` | limit/offset | `ChunkPreviewResponse` | ReviewPage |
| POST | `/api/v1/documents/{id}/review` | `ReviewRequest` | `ReviewResponse` | ReviewPage |
| POST | `/api/v1/documents/{id}/partition` | `ChangeDocumentPartitionRequest` | `ChangeDocumentPartitionResponse` | ReviewPage |
| POST | `/api/v1/documents/{id}/reopen-review` | `ReopenDocumentReviewRequest` | `ReopenDocumentReviewResponse` | ReviewPage |
| GET | `/api/v1/health` | 无 | `HealthResponse` 或 503 | 运维/预留 Client |

文档 ID 必须匹配 `doc_[0-9a-f]{24}`。列表 `q` 最长 200；列表和预览 `limit` 为 1 到 100，offset 不得为负数。

### 13.3 聊天关键模型

```json
{
  "question": "新员工如何申请 ForgeGit 权限？",
  "partition_hint": null,
  "allow_web_fallback": false
}
```

`ChatResponse` 返回业务 code、answer、route、decision_source、answerable、answer_source、实际搜索分区、内部/网络引用、澄清建议、warning、request_id 和 timing。clarify、无证据和敏感阻断属于 HTTP 200 业务结果，不使用异常响应。

`timing.retrieval` 与实际搜索分区顺序一致；`router_llm_ms` 和 `answer_llm_ms` 只有对应模型实际调用时才有值。检索与模型耗时分开，不能把完整请求耗时误认为索引性能。

### 13.4 文档关键模型

- `UploadDocumentResponse` 包含文档 ID、初选/最终分区、状态、Chunk 数、warnings、`parse_quality` 和 request ID。
- `DocumentDetailResponse` 包含元数据、审核/错误信息和可选质量报告，不暴露服务器路径。
- `ChunkPreviewResponse` 返回完整 `text` 与显示用 `preview`，严格按 `chunk_index` 排序。
- approve 必须提供最终分区；reject 必须没有最终分区。
- 改分区只接收新 `confirmed_partition` 和可选最后操作信息。
- 退回审核清空最终分区和 indexed_at；删除成功返回被移除 Chunk 数。

### 13.5 统一错误体

```json
{
  "code": "STABLE_ERROR_CODE",
  "message": "可安全展示的信息",
  "request_id": "req_xxx",
  "details": null
}
```

前端按 `code` 分支，不解析中文 message。常见错误包括 `VALIDATION_ERROR`、`INVALID_PARTITION`、`DOCUMENT_NOT_FOUND`、`DUPLICATE_DOCUMENT`、`INVALID_DOCUMENT_STATE`、`INDEX_WRITE_FAILED`、`PARTITION_CHANGE_FAILED`、`REOPEN_REVIEW_FAILED`、`DOCUMENT_DELETE_FAILED`、`INDEX_NOT_READY`、`PARTITION_ISOLATION_VIOLATION` 和 `INTERNAL_ERROR`。

## 14. 一致性、并发和恢复

| 场景 | 并发控制 | 成功条件 | 失败恢复 |
| --- | --- | --- | --- |
| 审核 | pending_review 条件更新 | 全 Chunk 在唯一分区可验证 | 删除本次 Chunk，文档 failed |
| 改分区 | ready -> reindexing 条件更新 | 新区全存在、其他区全不存在 | 恢复旧分区或 failed |
| 重新审核 | ready -> reindexing | 三索引全不存在，分区/时间清空 | 恢复旧分区或 failed |
| 删除 | 稳定状态 -> deleting | 三索引、文件、SQLite 均移除 | 保留可重试 failed 记录 |
| 进程中断 | 启动扫描中间状态 | 无 | 标记对应 recovery error |

SQLite、文件系统和 txtai 不可能参加同一个本地事务，因此“条件状态 + 有序操作 + 验证 + 补偿 + 启动恢复”是当前一致性方案。它降低风险，但不能提供严格的跨存储原子性。

## 15. 配置、启动和健康检查

### 15.1 开发模式

后端通常在 `127.0.0.1:8000`，Vite 在 `127.0.0.1:5173`。前端 `VITE_API_BASE_URL` 留空，经 Vite `/api` proxy 访问后端。保存前端源码触发 HMR；后端用 `--reload-dir app` 重启。

### 15.2 受信任内网模式

`SERVE_FRONTEND=true` 时，FastAPI 校验 `frontend/dist/index.html` 与 `assets` 后提供 SPA。`scripts/start_intranet.ps1` 构建前端、监听 `0.0.0.0:8000`，并要求管理员权限创建仅允许指定私网 CIDR 的临时 Windows 防火墙规则。服务停止后移除自身规则。

该模式没有认证。普通 `0.0.0.0` 启动只证明网络连通，不证明来源受限；不能通过端口转发、反向代理或公网 DNS 暴露。

### 15.3 关键配置

| 配置组 | 变量 |
| --- | --- |
| 应用/内网 | `APP_HOST`、`APP_PORT`、`CORS_ORIGINS`、`SERVE_FRONTEND`、`FRONTEND_DIST_DIR` |
| 数据 | `RAW_ROOT`、`STAGING_ROOT`、`INDEX_ROOT`、`METADATA_DATABASE_URL` |
| 接入 | `MAX_UPLOAD_SIZE_MB`、`ALLOWED_FILE_TYPES`、`CHUNK_*` |
| 检索 | `EMBEDDING_MODEL`、`RETRIEVAL_TOP_K`、`RETRIEVAL_MIN_SCORE`、`COMPOSITE_TOP_K_PER_PARTITION` |
| LLM | `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`、`ROUTER_LLM_MODEL`、`ANSWER_LLM_MODEL` |
| 联网 | `WEB_SEARCH_ENABLED`、`WEB_SEARCH_BASE_URL`、`WEB_SEARCH_API_KEY`、`WEB_SEARCH_TIMEOUT_SECONDS` |

健康检查主动执行 SQLite `SELECT 1` 并读取三个索引的加载状态。Router、Answer 和 Search 的 configured 只表示配置完整，不会主动调用外部端点。未配置 LLM 时，手动路由与抽取式回答仍可工作。

## 16. 安全边界

- 未审核文档不进入正式索引；非 ready 文档不进入聊天证据。
- 上传文件名不能控制服务器路径；PDF/DOCX 校验签名，文本校验 UTF-8。
- API 不返回 stored path、checksum、embedding_text、索引目录或异常堆栈。
- 秘密值不发送给索引或模型；常见邮箱、手机号和私网 IP 先脱敏。
- Answer 输入只包含安全问题和本轮命中证据；引用必须通过白名单。
- Web URL 必须为公开 HTTPS；网页文本被当作不可信数据。
- `.env`、原文件、SQLite、staging 和索引不得提交。
- 当前无身份和分区授权，受信任内网也不能视为安全生产环境。

## 17. 测试和验证现状

现行记录表明：2026-09-03 后端测试最高记录为 48/48、前端 Vitest 38/38、前端生产构建、Ruff 和 OpenAPI 对比通过；知识库目录与管理功能记录过后端 45/45、前端 37/37 的专项实现验证。真实 Router/Answer 完成一条单分区和一条双分区冒烟；完整 Playwright E2E 未运行。

测试使用临时 SQLite、临时文件和 FakeIndexRegistry/FakeLLM，不写 `data/raw`、`data/staging`、`data/indexes` 或 `data/metadata`。本文只更新文档，没有重新执行代码测试或写入运行数据。

仿真知识上传包已生成 10 个业务文件并完成 Parser/Chunker 静态检查，合计 71 个 Chunk，但状态仍是“待用户上传”。旧 `data/fixtures` 和问题清单存在内容质量及章节引用失配，不能当作黄金业务验收集。

## 18. 当前主要风险和下一阶段

1. 没有认证、权限和审计，是从演示走向共享使用的首要缺口。
2. 同步上传、解析和索引写入会长时间占用 HTTP 请求，应评估后台任务与可观察进度。
3. SQLite/txtai/文件系统没有共同事务，补偿失败和进程中断仍需人工恢复工具。
4. 没有普通失败重试、重新解析、批量操作和全库索引重建。
5. 检索阈值 `0.5` 依赖当前 Embedding 模型与数据，换模型或真实知识后需要重新校准。
6. 真实模型只做协议级少量冒烟，没有批量路由与回答质量评估。
7. Tavily 真实成功链路未验证，已有请求曾返回 HTTP 401。
8. 健康状态不主动探测外部 Provider，configured 不等于真实可用。
9. 未分类异常尚未形成完善的 Request ID 关联日志，缺少指标和 Tracing。
10. 部分现行文档的 commit、日期和 operation 数需要统一更新到当前基线。

## 19. 汇报建议

建议按以下顺序讲解：

1. 目标：做有审核边界、可追溯引用的分区知识库，而不是通用聊天机器人。
2. 页面：问答、目录、上传、统一详情各自只承担用户交互和 API 编排。
3. 数据闭环：文件 -> 解析质量/Chunk -> 人工审核 -> 唯一分区索引 -> ready 证据问答。
4. 接口复用：前端统一 API Client，后端统一 Registry/Provider/Session，跨端统一 OpenAPI。
5. 可靠性：状态抢占、全 Chunk 验证、失败补偿、启动恢复和引用白名单。
6. 边界：无认证、无跨存储事务、同步长请求、真实知识与模型质量尚未完整验收。

## 20. 代码阅读顺序

| 顺序 | 主题 | 文件 |
| --- | --- | --- |
| 1 | 路由和界面入口 | `frontend/src/App.tsx`、`pages/` |
| 2 | 前端接口复用 | `frontend/src/api/client.ts`、`types.ts` |
| 3 | HTTP 路由 | `app/api/chat.py`、`documents.py`、`health.py` |
| 4 | Schema 和状态 | `app/models/schemas.py`、`enums.py` |
| 5 | 文档闭环 | `ingestion.py`、`review.py`、`document_management.py` |
| 6 | 问答闭环 | `chat.py`、`routing.py`、`retriever.py`、`answering.py` |
| 7 | 基础接口 | `index_registry.py`、`file_storage.py`、`llm.py`、`web_search.py` |
| 8 | 数据底座 | `app/db/tables.py`、`session.py` |
| 9 | 跨端契约 | `contracts/openapi.json`、`frontend/src/api/generated.ts` |
| 10 | 测试事实 | `tests/`、`frontend/src/*.test.tsx`、`docs/testing/strategy.md` |
