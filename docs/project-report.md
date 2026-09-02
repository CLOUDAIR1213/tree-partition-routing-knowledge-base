# 三分区知识库项目理解与汇报报告

> 用途：个人学习、项目汇报与后续维护时快速建立全局认知。  
> 现状基线：2026-09-02，Git 提交 `61c551f` 加当前未提交工作树快照。  
> 资料依据：`docs/` 现行文档、`app/`、`frontend/`、`contracts/openapi.json` 和测试配置；`docs/archive/` 不作为当前行为依据。

## 1. 项目一句话说明

这是一个本地运行的企业知识库 MVP。它将上传的 PDF、DOCX、TXT、Markdown 文档解析为可检索的 Chunk；经人工审核确认后，写入财务（`finance`）、人事（`hr`）或技术（`tech`）之一的独立 txtai 索引；用户再通过手动选区或 LLM 自动路由进行基于证据的问答。

核心设计不是“把所有文件交给大模型”，而是将职责分开：

```text
文件事实与审核状态 -> SQLite
语义召回              -> 三个独立 txtai 索引
路由与证据组织        -> 可选 OpenAI-compatible LLM
用户交互              -> React 前端
HTTP 数据交换         -> FastAPI + OpenAPI
```

系统的关键约束是分区隔离：一次自动请求最多搜索两个不同分区；手动指定分区时只搜索该分区；即便 txtai 命中结果存在，后端也必须回查 SQLite，只有 `ready` 状态且最终分区一致的 Chunk 才能作为回答证据。

## 2. 建设目标、适用范围和边界

### 2.1 解决的问题

项目针对企业内部知识分散在制度、操作手册和技术文档中的场景，提供如下闭环：

1. 管理者或维护人员上传知识文档，并给出初始业务分区。
2. 系统解析、切分文档，但不立即让其可被问答。
3. 审核人员预览 Chunk，确认或修正最终分区，批准后写入唯一索引。
4. 使用者提问；系统在受控分区内检索，使用本次命中的证据生成回答并返回引用。

### 2.2 当前已覆盖

- 四种文本类文档的上传、校验、解析和 Chunking。
- 文档详情、Chunk 分页预览、批准、拒绝和索引失败补偿。
- 财务、人事、技术三套物理独立的向量索引。
- 手动单分区、自动单分区、自动双分区和要求用户澄清的路由。
- 内部证据回答、引用白名单、Answer LLM 不可用时的抽取式降级。
- 本地秘密值阻断、常见个人信息/私网 IP 脱敏。
- 在用户显式允许、完全没有内部证据且问题属于公开低风险范围时，使用 Tavily 搜索作为受限联网兜底。
- 统一 API 错误体、`X-Request-ID`、健康检查、OpenAPI 快照与前端生成类型。

### 2.3 不应被误解为已具备的能力

项目是可信本地环境下的演示 MVP，不是生产知识平台。当前没有认证、权限、角色审批、多租户、服务端会话、删除/重试 API、后台任务、OCR、数据库迁移、限流、指标、追踪或生产部署方案。

## 3. 总体架构和工程基底

### 3.1 技术栈

| 层 | 采用技术 | 主要职责 |
| --- | --- | --- |
| 浏览器前端 | React、TypeScript、React Router、Vite | 三个页面、输入与展示、本地聊天历史 |
| HTTP 服务 | FastAPI、Pydantic | 路由、校验、响应序列化、OpenAPI |
| 业务层 | Python async services | 接入、审核、检索、路由、回答编排 |
| 元数据 | SQLAlchemy Async、SQLite、aiosqlite | 文档状态、Chunk 正文、审核记录 |
| 向量检索 | txtai `Embeddings` | 每个业务分区的语义召回 |
| 模型调用 | httpx/OpenAI-compatible Chat Completions | Router 和 Answer 可选能力 |
| 契约 | FastAPI OpenAPI、openapi-typescript | Python Schema 与 TypeScript 类型同步 |

后端依赖方向固定为 `api -> services -> models/db/core`。前端不能直接读取 `data/`，只能通过 `frontend/src/api/client.ts` 调用 `/api/v1/*`。

### 3.2 组件与调用方向

```text
浏览器
  -> React 页面 / 组件
  -> API Client（超时、错误适配、聊天响应运行时校验）
  -> FastAPI 路由
  -> 业务服务编排
       -> SQLite：状态、正文、引用元数据
       -> 文件目录：原文件、解析快照
       -> txtai：指定分区的语义召回
       -> 可选 LLM：路由或基于证据生成
       -> 可选 Tavily：受限联网搜索
  -> Pydantic 响应 + X-Request-ID
  -> React 状态、引用展示和 localStorage 会话快照
```

### 3.3 前端页面和实际入口

| 浏览器路由 | 页面 | 用户动作 | 后端依赖 |
| --- | --- | --- | --- |
| `/` | `ChatPage` | 选择自动/手动分区、提问、查看引用、管理本地会话 | `POST /api/v1/chat` |
| `/knowledge/upload` | `UploadPage` | 选择文件、初始分区、可选标题并上传 | `POST /api/v1/documents` |
| `/knowledge/review/:documentId` | `ReviewPage` | 读取详情和预览、批准或拒绝 | 文档 GET 与 review POST |
| `/404`、`*` | `NotFoundPage` | 无效地址提示 | 无 |

`AppShell` 提供侧栏和顶部栏。聊天会话只保存在当前浏览器的 `localStorage` 键 `partitioned-kb.chat-session` 中，刷新后恢复；这不是服务端会话，也不能跨设备同步。

### 3.4 应用启动与关闭

`app/main.py` 的 `create_app()` 创建 FastAPI，并通过 lifespan 完成：

1. 按 `Settings` 创建 `data/`、raw、staging、fixtures、indexes、metadata 目录和三个分区索引目录。
2. 初始化 SQLite 表；发现上次启动中断而遗留的 `indexing` 文档时，标记为 `failed` 并写入 `INDEX_RECOVERY_REQUIRED`。
3. 加载三个 txtai 索引实例。
4. 根据环境变量装配可选 LLM Provider 与 Web Search Provider。
5. 关闭时释放 txtai 索引和数据库连接。

中间件为每个请求写入 `X-Request-ID`。客户端传入的 ID 仅在匹配 `[A-Za-z0-9_-]{1,100}` 时沿用，否则服务端生成新的 `req_...` 值。

## 4. 业务流程一：文档接入

### 4.1 目标和原则

接入阶段的目标是把上传文件转成“可审核的候选知识”，而不是直接变成可回答知识。未经审核的内容不得进入 txtai 索引，也不能被聊天检索到。

### 4.2 端到端流程

```text
UploadPage
  -> 前端预检：扩展名、非空、25 MB
  -> POST /api/v1/documents（multipart）
  -> FileStorage：文件名清理、大小/扩展名/签名/编码校验
  -> SHA-256 重复内容检查
  -> data/raw/<document_id>/ 保存原文件
  -> documents: uploaded -> parsing
  -> Parser 按格式提取 Section
  -> Chunker 生成稳定 Chunk ID 与 embedding_text
  -> SQLite 写入 chunk_candidates
  -> documents: pending_review
  -> data/staging/<document_id>/parse.json
  -> 前端跳转 ReviewPage
```

### 4.3 输入、处理和输出

- 前端提交字段：`file`、`partition`、可选 `title`。
- 可接受扩展名：`pdf`、`docx`、`txt`、`md`；默认最大 25 MB。
- 服务端再次校验，不能仅依赖前端。PDF/DOCX 校验内容签名；TXT/Markdown 必须可用 UTF-8 BOM 兼容方式解析。
- PDF 按页、DOCX 按 Heading 层级并附加表格、Markdown 按标题层级并保留代码围栏、TXT 按单个 Section 解析。
- Chunker 用中日韩字符、英文词和其他非空字符近似计算 Token，按窗口与 overlap 切分；每个 Chunk 同时有展示正文 `text` 和供 Embedding 的增强文本 `embedding_text`。
- 成功响应为 HTTP 201 `UploadDocumentResponse`，状态应为 `pending_review`，并返回 `document_id`、初选分区和 Chunk 数。

### 4.4 接入失败和恢复原则

不支持的类型为 415，过大文件为 413，空文档或解析失败为 422，重复有效内容为 409。解析失败的数据库记录会变为 `failed`；已保存的 raw/staging 文件当前不会自动清理。上传是同步请求，前端等待 120 秒，超时后应该先查询文档而非直接重复上传。

## 5. 业务流程二：审核、分区确认与索引

### 5.1 审核为何是系统边界

上传时的 `selected_partition` 只是初选；审核时的 `confirmed_partition` 才是最终决定。文档只会进入一个分区索引，审核通过后状态为 `ready`，这两个条件共同决定聊天是否可使用该文档。

### 5.2 端到端流程

```text
ReviewPage
  -> GET /documents/{id} + GET /documents/{id}/preview
  -> 用户确认分区、填写审核备注
  -> POST /documents/{id}/review
  -> 条件更新声明 pending_review -> indexing
  -> 在线程中写入对应 txtai 索引并保存
  -> verify
  -> 所有 Chunk 写 indexed_at
  -> documents: ready

拒绝路径：pending_review -> rejected，不写 txtai
失败路径：indexing -> failed，并按本次 Chunk ID 删除索引数据补偿
```

### 5.3 并发和一致性设计

批准或拒绝都以 `WHERE status = pending_review` 的条件更新抢占状态，因此多个审核请求中最多一个成功。批准采用“先 SQLite 声明 `indexing`，再写 txtai”的顺序，避免重复写入，但 SQLite 与 txtai 不共享事务。

因此索引写入失败时，服务会尝试 `delete_and_save` 删除这次的 Chunk ID，并将文档标为 `failed`，错误为 `INDEX_WRITE_FAILED`，详情包含补偿是否成功。进程在 `indexing` 阶段崩溃时，下一次应用启动会将该文档设为 `failed`，要求人工处理。

### 5.4 重要现有限制

生产 `IndexRegistry.verify` 目前只验证传入 Chunk ID 的第一条是否存在；测试用 Fake 会验证全部 Chunk。因此存在“部分 Chunk 未持久化但文档被标记 ready”的已知完整性缺口，报告和验收中应明确说明。

## 6. 业务流程三：聊天、路由、检索与回答

### 6.1 整体流程

```text
ChatPage -> POST /api/v1/chat
  -> InputSafetyGuard：阻断秘密值；脱敏邮箱、手机号、私网 IP
  -> partition_hint 存在？
       是：manual，只创建该分区子查询
       否：Router LLM 产生 single / composite / clarify
  -> Retriever 逐个查询计划中的 txtai 索引
  -> 低分过滤 + SQLite ready/confirmed_partition 二次校验
  -> 有内部证据？
       是：Answer LLM 基于本次证据回答；失败则抽取式降级
       否：满足显式联网条件时才调用 Tavily + Web Answer LLM
  -> Citation 或 URL 白名单校验
  -> ChatResponse -> 前端按内部/网页来源展示
```

### 6.2 路由规则

| 情况 | 路由结果 | 可访问索引 |
| --- | --- | --- |
| 用户指定 `partition_hint` | `manual` | 仅用户指定的一个分区；跳过 Router LLM |
| 自动单主题问题 | `single` | 一个分区 |
| 自动双主题问题 | `composite` | 两个不同分区，严格最多两个 |
| 表意不完整、歧义或涉及三个分区 | `clarify` | 不访问任何索引，返回建议分区 |
| Router 未配置、超时或输出不合法 | `clarify` | 不访问任何索引，带 warning |

Router 需返回严格 JSON；若结构不合法，最多执行一次修复调用。复合路由的子查询依次串行执行，且不同索引间的相似度分数不做横向比较。

### 6.3 检索链路为何要“双重校验”

txtai 是召回器，不是业务事实权威。Retriever 得到 `(chunk_id, score)` 后执行以下过滤：

1. 低于 `RETRIEVAL_MIN_SCORE` 的命中丢弃，当前默认值为 `0.5`。
2. 用 Chunk ID 回查 SQLite 的 `chunk_candidates` 和 `documents`。
3. 仅保留文档状态为 `ready` 且 `confirmed_partition` 等于当前检索分区的结果。
4. 从 SQLite 正文和定位信息构造 `RetrievalHit`，而不直接相信索引元数据。

这使得 pending_review、rejected、failed 文档，即便因为索引残留而可被 txtai 命中，也不能成为回答证据。阈值为当前模型和演示数据的默认值，替换 Embedding 模型或知识数据后应通过少量只读问题重新校准。

### 6.4 回答、引用与降级

内部证据存在时，Answer LLM 只获得安全处理后的问题和本轮 `RetrievalGroup` 命中。它不能引用未命中的 Chunk；服务端会核验其输出的 Chunk ID，只把白名单内 ID 转换为 Citation。若 LLM 未配置、超时或传输失败，服务采用每个检索组第一条 Chunk 组成抽取式回答，并给出 warning；不会因为内部 Answer 失败而转向联网。

若 LLM 的引用为空或越界，则丢弃回答和全部引用，返回不可回答结果，避免“有答案无证据”。

### 6.5 受限联网兜底

联网不是常规路径，必须同时满足：

1. 当前请求 `allow_web_fallback=true`。
2. 全部内部检索组都没有有效 Chunk。
3. 问题没有经过敏感脱敏，且通过本地公开、低风险资格判断。
4. 当前不是 `clarify` 或 Router 故障。
5. Tavily Provider 与 Web Answer LLM 都已配置。

Tavily 只搜索，不抓取网页正文。服务仅保留公开 HTTPS URL，拒绝含凭据、`.local`、本机、私网和保留地址，移除常见跟踪参数、片段和重复 URL；最多保留 5 条结果、每域名最多 2 条，最终网页回答最多引用 3 条。内部和网页证据不会混合，`answer_source=web` 时内部 citations 必须为空。

当前 Fake 测试覆盖该链路，但一次真实 Tavily 冒烟返回 HTTP 401，因此不能将真实网页成功回答视为已验证能力。

## 7. 数据库与存储底座

### 7.1 四类持久化边界

| 边界 | 默认位置 | 权威信息 | 典型读写者 |
| --- | --- | --- | --- |
| SQLite | `data/metadata/knowledge.db` | 文档状态、最终分区、Chunk 正文、审核信息 | 接入、审核、检索、详情 API |
| 原文件 | `data/raw/<document_id>/document.<ext>` | 上传原始字节 | FileStorage 写入 |
| 解析快照 | `data/staging/<document_id>/parse.json` | Section 与 Chunk ID 调试快照 | 接入写入 |
| txtai 索引 | `data/indexes/finance|hr|tech/` | 指定分区的 Embedding 召回结构 | 审核写入、Retriever 查询 |
| 浏览器会话 | `localStorage` | 当前浏览器聊天历史 | `ChatSessionContext` |

SQLite 是业务元数据与可展示正文的权威来源；txtai 只负责快速语义召回。文件原件和解析快照不是 API 直接输出。

### 7.2 `documents` 表

| 字段组 | 字段 | 作用 |
| --- | --- | --- |
| 标识 | `id` | `doc_` 加 24 位十六进制随机值，主键 |
| 文件 | `original_filename`、`stored_path`、`mime_type`、`size_bytes`、`checksum_sha256` | 文件来源与重复检查；路径和校验和不通过 API 返回 |
| 分区 | `selected_partition`、`confirmed_partition` | 上传初选与审核终选 |
| 生命周期 | `status`、`error_code`、`error_message` | 状态机与故障原因 |
| 展示 | `title`、`chunk_count` | UI 文档信息 |
| 审核 | `reviewed_by`、`review_note`、`reviewed_at` | 审核记录；当前未认证 |
| 时间 | `created_at`、`updated_at` | UTC 时间 |

`checksum_sha256` 有索引但没有数据库唯一约束；接入服务在应用层拒绝非 `rejected`、非 `failed` 的同内容文档。

### 7.3 `chunk_candidates` 表

| 字段组 | 字段 | 作用 |
| --- | --- | --- |
| 标识 | `id`、`document_id`、`chunk_index` | 稳定 Chunk 标识、所属文档和顺序 |
| 内容 | `text`、`embedding_text` | 面向展示/回答的正文与面向 Embedding 的增强文本 |
| 定位 | `title`、`section_path`、`page_start`、`page_end` | 引用标题、章节和页码 |
| 完整性 | `checksum_sha256`、`indexed_at` | 内容校验和、成功索引时间 |

`(document_id, chunk_index)` 唯一，`document_id` 是启用 SQLite 外键约束的级联外键。系统没有暴露直接删除文档的 API。

### 7.4 文档状态机

```text
uploaded -> parsing -> pending_review -> indexing -> ready
                    \                    \-> failed
                     \-> rejected
uploaded / parsing -> failed
应用启动发现 indexing -> failed(INDEX_RECOVERY_REQUIRED)
```

只有 `pending_review` 可以审核；只有 `ready` 且 `confirmed_partition` 与查询分区相同的 Chunk 可以进入聊天证据。

### 7.5 数据安全与运行数据边界

普通验证不得写入 `data/raw`、`data/staging`、`data/indexes`、`data/metadata`。测试使用临时 SQLite、临时目录和 FakeIndexRegistry。`data/fixtures/*.jsonl` 是可审查的演示源数据，但也不等于真实业务知识或黄金回答数据。

## 8. API 如何传递数据

### 8.1 契约生成链

```text
Pydantic 请求/响应模型 + FastAPI 路由
  -> scripts/export_openapi.py
  -> contracts/openapi.json（导出快照）
  -> openapi-typescript
  -> frontend/src/api/generated.ts（生成类型）
  -> frontend/src/api/types.ts / client.ts（前端适配）
```

因此 API 字段变更的正确顺序是：修改 Schema 和服务生产者，补充定向测试，导出 OpenAPI，再生成前端类型和调整 Client/UI。`contracts/openapi.json` 与 `frontend/src/api/generated.ts` 是生成文件，不能手改。

### 8.2 通用传递约定

- API 前缀固定为 `/api/v1`。
- JSON 字段采用 snake_case；上传使用 `multipart/form-data`，浏览器自行生成 boundary。
- 请求模型默认禁止未知字段并去除字符串首尾空白。
- 日期以带时区 ISO 8601 返回；SQLite 的无时区值在 API 层适配为 UTC。
- 分页一律用 `limit`、`offset`，响应回显两者并返回 `total`。
- Client 默认 30 秒；聊天 100 秒；上传和审核 120 秒；有副作用的 POST 不自动重试。

### 8.3 端点清单

| 方法 | 路径 | 主要请求 | 成功响应 | 作用 |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/chat` | `ChatRequest` JSON | `ChatResponse`，200 | 路由、检索、回答 |
| POST | `/api/v1/documents` | `file`、`partition`、`title?` multipart | `UploadDocumentResponse`，201 | 上传、解析、Chunking |
| GET | `/api/v1/documents` | `status?`、`limit`、`offset` | `DocumentListResponse` | 文档列表 |
| GET | `/api/v1/documents/{document_id}` | 路径 ID | `DocumentDetailResponse` | 文档详情 |
| GET | `/api/v1/documents/{document_id}/preview` | `limit`、`offset` | `ChunkPreviewResponse` | Chunk 分页预览 |
| POST | `/api/v1/documents/{document_id}/review` | `ReviewRequest` JSON | `ReviewResponse` | 批准或拒绝 |
| GET | `/api/v1/health` | 无 | `HealthResponse` 或 503 错误体 | 组件状态 |

文档 ID 的路由格式必须为 `doc_[0-9a-f]{24}`；预览和列表的 `limit` 范围为 1 到 100，`offset` 不得为负。

### 8.4 三个关键请求/响应模型

`ChatRequest`：

```json
{
  "question": "新员工如何申请 GitLab 项目权限？",
  "partition_hint": null,
  "allow_web_fallback": false
}
```

- `question` 必填，长度 1 到 2000。
- `partition_hint` 为 `finance`、`hr`、`tech` 或 `null`；有值时代表手动路由。
- `allow_web_fallback` 默认 `false`，仅表示用户授权在严格条件下联网。

`ChatResponse` 的主要字段：

| 字段 | 含义 |
| --- | --- |
| `code` | `OK`、`ROUTE_CLARIFICATION_REQUIRED`、`NO_INTERNAL_EVIDENCE` 或 `SENSITIVE_INPUT_BLOCKED`；这些均可能是 HTTP 200 业务结果 |
| `answer`、`answerable` | 面向用户的文本和是否可基于合规证据回答 |
| `route`、`decision_source` | manual/single/composite/clarify 与人为选择或模型决定来源 |
| `searched_partitions` | 实际访问过的内部索引分区 |
| `citations` | 内部引用：分区、Chunk、文档、标题、章节、页码 |
| `answer_source`、`web_citations` | `internal`、`web`、`none` 与网页标题、URL、域名 |
| `suggested_partitions`、`warning`、`request_id` | 澄清建议、可安全展示的降级说明、问题追踪 ID |

`ReviewRequest`：

```json
{
  "action": "approve",
  "confirmed_partition": "tech",
  "reviewer_name": "审核人",
  "note": "文档内容与技术分区一致"
}
```

- `action` 为 `approve` 或 `reject`。
- approve 必须有 `confirmed_partition`；reject 必须传 `null` 或不传该字段。
- `reviewer_name` 最长 100，`note` 最长 500；二者是记录字段，当前不代表身份认证。

### 8.5 响应结构不变量

- `route=clarify` 时 `searched_partitions` 必须为空。
- `route=composite` 时必须恰好有两个不同的 `searched_partitions`。
- 单分区 route 必须对应唯一搜索分区。
- 内部 Citation 的分区必须在 `searched_partitions` 内。
- `answer_source=internal` 时只能有 `citations`；`web` 时只能有 `web_citations`；`none` 时两类均为空。

后端 Pydantic 和前端 `assertChatContract` 都检查这些结构，防止服务端模型输出或跨端类型漂移直接进入 UI。

### 8.6 错误传递

所有非 2xx 都统一为：

```json
{
  "code": "STABLE_ERROR_CODE",
  "message": "可安全展示的信息",
  "request_id": "req_xxx",
  "details": null
}
```

前端应根据稳定的 `code` 分支，不应通过解析中文 `message` 判断业务状态。主要分类包括 `INVALID_PARTITION`、`VALIDATION_ERROR`、`DOCUMENT_NOT_FOUND`、`DUPLICATE_DOCUMENT`、`INDEX_WRITE_FAILED`、`INDEX_NOT_READY`、`NOT_FOUND`、`METHOD_NOT_ALLOWED`、`INTERNAL_ERROR`。异常响应不应暴露服务器路径、堆栈、密钥、原文或模型响应。

## 9. 配置、部署形态和健康检查

### 9.1 本地运行形态

Windows PowerShell 下，后端通常运行在 `127.0.0.1:8000`，Vite 前端在 `127.0.0.1:5173`。前端本地开发默认通过 Vite `/api` proxy 转发；分别部署时才配置 `VITE_API_BASE_URL` 和后端 `CORS_ORIGINS`。

常用地址：前端 `/`，Swagger `/docs`，实时 OpenAPI `/openapi.json`，健康检查 `/api/v1/health`。

### 9.2 关键配置组

| 配置组 | 典型变量 | 影响 |
| --- | --- | --- |
| 数据目录 | `DATA_ROOT`、`RAW_ROOT`、`STAGING_ROOT`、`INDEX_ROOT`、`METADATA_DATABASE_URL` | 文件、索引与 SQLite 位置 |
| 上传与 Chunk | `MAX_UPLOAD_SIZE_MB`、`ALLOWED_FILE_TYPES`、`CHUNK_*` | 接入规模和切分方式 |
| 检索 | `EMBEDDING_MODEL`、`RETRIEVAL_TOP_K`、`RETRIEVAL_MIN_SCORE`、`COMPOSITE_TOP_K_PER_PARTITION` | 召回模型、阈值和预算 |
| LLM | `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`、`ROUTER_LLM_MODEL`、`ANSWER_LLM_MODEL` | 自动路由与回答能力 |
| 联网 | `WEB_SEARCH_ENABLED`、`WEB_SEARCH_API_KEY`、`WEB_SEARCH_TIMEOUT_SECONDS` | Tavily 兜底；默认关闭 |
| 跨域 | `CORS_ORIGINS` | 前端 Origin 访问范围 |

密钥只能存在于本地环境变量或 `.env`，不得进入 Git、测试 fixture、日志、API 响应或本报告。

### 9.3 健康检查应如何理解

`GET /api/v1/health` 汇报 SQLite、三个索引、Router、Answer 和 Web Search 的状态。模型/搜索为 `configured` 仅代表配置完整，不代表服务端已主动探活或真实调用成功。汇报时应避免把健康检查的 configured 等同于外部模型可用性。

## 10. 安全、可靠性和当前验证结论

### 10.1 已实现的主要防线

- 上传侧有扩展名、签名、编码、大小、路径清理和重复内容校验。
- `pending_review` 文档不入索引、不进入聊天证据。
- 检索后回查 SQLite，保证 ready 状态和最终分区一致。
- 手动选区优先；自动复合检索最多两个分区。
- 秘密值不会送给索引或模型；常见个人信息和私网 IP 先脱敏。
- LLM 引用和 Web URL 均必须属于本次受控证据集合。
- HTTP 异常隐藏内部细节，所有响应带 Request ID。

### 10.2 最近记录的验证

2026-09-02 的文档记录：后端隔离测试 32/32、前端 Vitest 22/22、前端生产构建、OpenAPI 内存比较和 Ruff 均通过；真实 Router/Answer 完成一条单分区和一条双分区只读冒烟。测试使用 Fake LLM/Fake IndexRegistry 与临时 SQLite，不写入现有运行数据。

### 10.3 汇报时应主动说明的风险

1. 真实 Tavily 请求曾返回 HTTP 401，网页回答成功链路尚未完成真实验证。
2. 现有 fixture 的结构数量已准备，但内容质量、预期证据对齐和自动化接线未完成，不能作为业务答案质量验收依据。
3. `RETRIEVAL_MIN_SCORE=0.5` 只针对当前演示模型/数据作了有限观察，换模型或换数据应重新校准。
4. 生产索引 verify 只抽查第一条 Chunk，存在部分写入漏检风险。
5. SQLite、文件系统和 txtai 无跨存储事务；失败补偿存在，但补偿失败仍需人工处理。
6. 上传、解析、索引写入都在同步 HTTP 请求中，大文档或慢模型会占用请求时间。
7. 没有身份认证、权限隔离和审计，不能用于共享或生产敏感知识库。

## 11. 建议的汇报表达顺序

1. 先讲目标：建立有审核边界、可追溯引用的三分区知识库，而不是通用聊天机器人。
2. 再讲数据闭环：文件上传 -> 候选 Chunk -> 人工审核 -> 唯一分区索引 -> `ready` 证据问答。
3. 说明分区隔离：手动优先、自动最多两区、txtai 召回后再由 SQLite 复核。
4. 说明 API 闭环：React -> API Client -> FastAPI/Pydantic -> 服务层 -> 存储/LLM -> OpenAPI/生成 TypeScript 类型返回前端。
5. 说明可靠性措施：状态机、条件更新、索引补偿、启动恢复、引用白名单、Request ID。
6. 最后说明 MVP 边界与下一阶段重点：认证授权、索引完整性验证、异步任务、真实数据/模型评测、失败重试与可观测性。

## 12. 代码阅读索引

| 主题 | 首要文件 |
| --- | --- |
| 应用工厂、异常、Request ID | `app/main.py` |
| 配置 | `app/core/config.py`、`.env.example` |
| ORM 和启动恢复 | `app/db/tables.py`、`app/db/session.py` |
| 文档 HTTP API | `app/api/documents.py` |
| 聊天 HTTP API | `app/api/chat.py` |
| 接入 | `app/services/ingestion.py`、`file_storage.py`、`parser.py`、`chunker.py` |
| 审核和索引 | `app/services/review.py`、`index_registry.py` |
| 路由、检索和回答 | `app/services/chat.py`、`routing.py`、`retriever.py`、`answering.py` |
| 联网限制 | `app/services/web_search.py` |
| API 模型 | `app/models/schemas.py`、`app/models/enums.py` |
| 前端请求适配 | `frontend/src/api/client.ts`、`frontend/src/api/types.ts` |
| 聊天会话 | `frontend/src/features/chat/ChatSessionContext.tsx` |
| 权威 HTTP 快照 | `contracts/openapi.json` |

相关现行设计文档：`docs/architecture/system-overview.md`、`docs/architecture/data-and-storage.md`、`docs/features/`、`docs/contracts/api-conventions.md`、`docs/operations/local-development.md` 和 `docs/testing/strategy.md`。
