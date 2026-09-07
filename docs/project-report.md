# 三分区知识库项目理解与汇报报告

> 用途：个人学习、项目汇报与后续维护时快速建立全局认知。  
> 现状基线：2026-09-04，当前目录的工作树快照（本目录不是 Git 仓库）。  
> 资料依据：`docs/` 现行文档、`app/`、`frontend/`、`contracts/openapi.json` 与测试配置；`docs/archive/` 仅作历史背景，不代表当前实现。

## 1. 项目一句话说明

这是一个本地运行的企业知识库 MVP。系统将上传的 PDF、DOCX、TXT、Markdown 文档解析为可检索的 Chunk；经人工审核确认后，写入财务（`finance`）、人事（`hr`）或技术（`tech`）的独立三层树状索引；用户再通过手动选区或 LLM 自动路由，在受控分区内完成基于证据的问答。

当前版本的核心是 tree-only 检索：每个分区维护 `document -> section -> chunk` 三层 txtai 索引。文档与章节节点只用于逐层收窄候选，最终回答和引用只能来自通过 SQLite 校验的叶子 Chunk；运行时不存在旧 Flat Chunk 索引或 Flat fallback。

```text
文件、状态、Chunk 正文、节点元数据 -> SQLite
语义导航与召回                     -> 三分区、每区三层 txtai 索引
路由与基于证据的回答                 -> 可选 OpenAI-compatible LLM
用户交互                             -> React 前端
HTTP 数据交换                        -> FastAPI + OpenAPI
```

关键隔离约束如下：手动指定分区时只访问该分区；自动复合路由最多访问两个不同分区；父节点不能成为回答证据；txtai 命中仍必须回查 SQLite，只有状态为 `ready` 且最终分区一致的 Chunk 才能进入回答。

## 2. 建设目标、适用范围和边界

### 2.1 解决的问题

项目面向企业制度、操作手册和技术资料分散的场景，形成以下闭环：

1. 维护人员上传知识文档并选择初始业务分区。
2. 系统解析、切分并生成质量报告，但不立即让文档进入问答。
3. 审核人员完整预览 Chunk，明确确认最终分区，批准后写入并验证三层树索。
4. 使用者提问，系统在受控分区内逐层检索，使用本轮有效证据生成回答与结构化引用。
5. 维护人员可在统一知识库目录查看所有状态，调整已入库分区、退回重新审核或删除文档。

### 2.2 当前已覆盖

- PDF、DOCX、TXT、Markdown 的上传、校验、解析、Chunking、质量报告和非权威分区建议。
- 文档目录、筛选、全状态详情、原文顺序 Chunk 预览、审核、删除、改分区和重新审核。
- 财务、人事、技术三个隔离分区，每区 document、section、chunk 三层独立持久化索引。
- 手动单分区、自动单分区、自动双分区和要求用户澄清的路由。
- 三层 Beam Search、精确文档/章节范围约束、SQLite 权威校验、证据引用白名单和抽取式回答降级。
- 本地秘密值阻断、常见个人信息和私网 IP 脱敏；用户显式授权且内部无证据时的 Tavily 受限联网兜底。
- 统一错误体、`X-Request-ID`、健康检查、OpenAPI 快照、前端生成类型和可选受信任内网单端口托管。

### 2.3 不应被误解为已具备的能力

项目是可信本地环境下的演示 MVP，不是生产知识平台。当前没有身份认证、权限和审核角色、多租户、服务端会话、普通失败重试、后台任务、OCR、数据库迁移、限流、指标、追踪或生产部署体系。

tree-only 代码和离线迁移工具已经完成，但真实业务 SQLite 的离线迁移、树索目录切换、观察期验证和旧 `data/indexes/` Flat 数据清理尚未由本项目 Agent 执行。旧目录仍为只读运行数据，不参与当前请求，也不能被日常验证删除。

## 3. 总体架构和工程基底

### 3.1 技术栈

| 层 | 采用技术 | 主要职责 |
| --- | --- | --- |
| 浏览器前端 | React、TypeScript、React Router、Vite | 聊天、知识库目录、上传、详情与审核管理、本地会话 |
| HTTP 服务 | FastAPI、Pydantic | 路由、校验、响应序列化、OpenAPI |
| 业务层 | Python async services | 接入、审核、文档管理、检索、路由与回答编排 |
| 元数据 | SQLAlchemy Async、SQLite、aiosqlite | 文档状态、Chunk 正文、审核记录和节点元数据 |
| 向量检索 | txtai `Embeddings` | 每分区 document、section、chunk 三层索引 |
| 模型调用 | httpx/OpenAI-compatible Chat Completions | Router 与 Answer 的可选能力 |
| 契约 | FastAPI OpenAPI、openapi-typescript | Python Schema 与 TypeScript 类型同步 |

后端依赖方向固定为 `api -> services -> models/db/core`。前端不能直接读取 `data/`，只能通过 `frontend/src/api/client.ts` 调用 `/api/v1/*`。

### 3.2 组件与调用方向

```text
浏览器
  -> React 页面 / 组件
  -> API Client（超时、错误适配、聊天响应运行时校验）
  -> FastAPI 路由
  -> 业务服务编排
       -> SQLite：状态、正文、引用与树节点元数据
       -> 文件目录：原文件、解析快照
       -> txtai：分区内 document -> section -> chunk 三层索引
       -> 可选 LLM：路由和基于证据的回答
       -> 可选 Tavily：严格条件下的公开搜索
  -> Pydantic 响应 + X-Request-ID
  -> React 状态、结构化引用和 localStorage 会话快照
```

### 3.3 前端页面和实际入口

| 浏览器路由 | 页面 | 用户动作 | 后端依赖 |
| --- | --- | --- | --- |
| `/` | `ChatPage` | 自动或手动分区问答、查看引用、管理本地会话 | `POST /api/v1/chat` |
| `/knowledge` | `KnowledgeLibraryPage` | 目录、筛选、分页与详情入口 | `GET /api/v1/documents` |
| `/knowledge/upload` | `UploadPage` | 选择文件、初始分区、可选标题并上传 | `POST /api/v1/documents` |
| `/knowledge/documents/:documentId` | `ReviewPage` | 全状态详情、Chunk 预览、审核、改分区、重审与删除 | 文档详情及管理 API |
| `/knowledge/review/:documentId` | 重定向 | 兼容旧审核链接 | 跳转统一详情页 |

`AppShell` 提供侧栏、顶部栏和 `ChatSessionProvider`。会话运行状态位于 React；版本化聊天历史写入当前浏览器 `localStorage`，刷新后可恢复。聊天会话不存入服务端，也不会修改知识库数据。

### 3.4 应用启动与关闭

启动时，应用创建目录、初始化 SQLite、恢复遗留的 `indexing`、`reindexing`、`deleting` 状态，并加载财务、人事、技术共九个树索实例。随后启动同步会校验所有 `ready` 文档的三层节点和 Chunk，补齐缺失条目并清除已知 Chunk 的跨分区残留；不一致会阻止完整服务启动。

启动还会装配可选 Router、Answer 和 Web Search Provider。关闭时释放树索与 SQLite 连接。启用 `SERVE_FRONTEND=true` 时，应用会检查并托管 `frontend/dist`，以同源方式提供页面和 API。

## 4. 业务流程一：文档接入

### 4.1 端到端流程

```text
UploadPage
  -> POST /documents
  -> 文件名、类型、大小、签名、编码与重复内容校验
  -> raw 文件保存
  -> documents: uploaded -> parsing
  -> Parser：Section、页码、表格和诊断
  -> Chunker：稳定 Chunk ID、展示正文、Embedding 文本
  -> 质量报告 + 非权威分区建议
  -> SQLite 写入 Chunk + staging parse.json
  -> documents: pending_review
  -> 跳转 /knowledge/documents/:documentId
```

接入阶段不写入任一 txtai 索引。`selected_partition` 只是上传时的初选；解析建议只辅助人工判断，均不能替代审核后的 `confirmed_partition`。

### 4.2 输入、处理和输出

- 支持 PDF、DOCX、TXT、Markdown。前端预检非空、扩展名和 25 MB；后端始终重复校验扩展名、签名、编码与实际大小。
- PDF 按页解析；DOCX 按 Heading 层级并保留表格原始位置；Markdown 按标题层级且保留代码围栏；TXT 作为单个 Section。
- Chunker 使用中日韩字符、英文词和其他非空字符近似计算 Token，以窗口与 overlap 切分。每个 Chunk 同时保存展示/回答用的 `text` 和 Embedding 用的 `embedding_text`。
- 成功返回 HTTP 201 `UploadDocumentResponse`，文档状态为 `pending_review`，并包含文档 ID、Chunk 数、解析质量和警告。

### 4.3 接入失败与恢复原则

不支持类型返回 415，过大文件返回 413，空文档或解析失败返回 422，重复有效内容返回 409。解析失败时数据库记录进入 `failed`；已保存的 raw/staging 文件当前不会自动清理。上传为同步请求，前端等待 120 秒，超时后应先从详情或目录确认是否已创建文档，避免盲目重复上传。

## 5. 业务流程二：审核、树索写入与文档管理

### 5.1 审核是可检索边界

只有 `pending_review` 文档可以审核。审核人先完整预览 Chunk，再明确选择最终唯一分区；批准操作以条件更新声明 `pending_review -> indexing`，随后写入并验证该分区的全部 Chunk、文档节点和章节节点。三层均成功后，才写入 `indexed_at` 并将文档设为 `ready`。

```text
ReviewPage
  -> GET detail + GET complete preview
  -> pending_review：批准或拒绝
       approve -> indexing -> 三层树索 upsert + verify -> ready
       reject  -> rejected，不访问索引
  -> ready：改分区 | 退回重新审核 | 删除
```

### 5.2 三层一致性、并发与补偿

批准、改分区、重新审核和删除都先通过 SQL 条件更新抢占状态，避免并发操作互相覆盖。SQLite 与 txtai 没有共同事务，因此服务采用“先状态声明，后索引操作，最后提交业务状态”的编排：

- 批准失败时，按稳定 ID 清理三层条目，文档进入 `failed`。
- 改分区先验证新分区三层条目，再清理其他分区；失败时恢复原分区，恢复失败进入 `failed`。
- 重新审核清理三分区的文档、章节和 Chunk，清空最终分区与索引时间，回到 `pending_review`。
- 删除清理三层索引、raw、staging 和 SQLite；若失败保留可诊断记录并进入 `failed`，可再次删除。
- 进程启动发现遗留 `indexing`、`reindexing` 或 `deleting` 时，将记录标记为恢复失败，要求人工检查。

### 5.3 重要限制

`ready` 只表示三层写入流程完成，不表示内容质量、访问权限或合规审查已经完成。没有真实审核身份、审批流或不可篡改审计历史。对真实大文档逐项验证三层 ID 的耗时，以及进程中断后的补偿恢复，仍需进一步验证。

## 6. 业务流程三：聊天、路由、树状检索与回答

### 6.1 整体流程

```text
ChatPage -> POST /api/v1/chat
  -> InputSafetyGuard：阻断秘密值，脱敏邮箱、手机号、私网 IP
  -> partition_hint 存在？
       是：manual，仅创建该分区子查询
       否：Router LLM 生成 single / composite / clarify
  -> document 索引检索
  -> 以 document_id 约束 section 索引检索
  -> 以精确 document_id + section 对约束 chunk 索引检索
  -> SQLite 校验 ready + confirmed_partition + 范围
  -> 内部 Answer LLM，失败时抽取式降级
  -> 零内部证据且满足明确条件时，可选 Tavily + Web Answer
  -> Citation / URL 白名单 -> ChatResponse
```

父节点仅缩小叶子候选范围，不能直接进入 Answer Prompt 或 Citation。任一父层无候选即返回空内部证据，不会退回 Flat 索引。范围查询会将 txtai 候选扩大至相应层级总量后再施加 metadata 条件，避免无关高分结果挤占目标分支。

### 6.2 路由规则

| 情况 | 路由结果 | 可访问索引 |
| --- | --- | --- |
| 用户指定 `partition_hint` | `manual` | 只访问用户指定的一个分区，跳过 Router LLM |
| 自动单主题问题 | `single` | 一个分区 |
| 自动双主题问题 | `composite` | 两个不同分区，严格最多两个 |
| 表意不完整、歧义或涉及三个分区 | `clarify` | 不访问索引，返回建议分区 |
| Router 未配置、超时或输出不合法 | `clarify` | 不访问索引，附带安全 warning |

复合路由按子查询顺序串行执行，不比较不同分区之间的相似度分数。公司基础信息默认由人事分区承接；仅同时出现可独立检索的财务或技术事项时才允许复合路由。

### 6.3 回答、引用和受限联网兜底

内部检索命中后，Answer LLM 只能接收安全问题与本轮 SQLite 校验通过的 `RetrievalGroup`。服务端只接受本次命中的 Chunk ID；若回答没有引用或引用越界，则丢弃回答和引用，返回不可回答结果。模型不可用、超时或传输失败时，系统使用每组第一条 Chunk 组成抽取式回答，不会因内部 Answer 失败而转向联网。

联网不是常规路径，必须同时满足当前请求显式授权、所有内部检索组均无有效 Chunk、问题未脱敏且被判定为公开低风险、路由不是 `clarify`、Tavily 和 Web Answer 均已配置。搜索只使用公开 HTTPS 结果摘要，不抓取网页正文；最多保留 5 条结果、每域名最多 2 条，最终网页回答最多引用 3 条。内部和网页证据始终互斥。

真实 Tavily 请求曾返回 HTTP 401，因此网页回答成功链路不能作为已完成的真实验证结论。

## 7. 数据库与存储底座

### 7.1 五类持久化边界

| 边界 | 默认位置 | 权威信息 | 典型读写者 |
| --- | --- | --- | --- |
| SQLite | `data/metadata/knowledge.db` | 文档状态、最终分区、Chunk 正文、审核和节点元数据 | 接入、审核、管理、检索、详情 API |
| 原文件 | `data/raw/<document_id>/document.<ext>` | 上传原始字节 | FileStorage |
| 解析快照 | `data/staging/<document_id>/parse.json` | Section、Chunk ID、解析质量与建议 | 接入、详情 |
| tree-only txtai 索引 | `data/indexes-hierarchical/<partition>/{document,section,chunk}/` | 分区内的导航与叶子召回 | 审核、管理、启动同步、树检索 |
| 浏览器会话 | `localStorage` | 当前浏览器聊天历史 | `ChatSessionContext` |

旧 `data/indexes/<partition>/` 是已退役 Flat 运行数据，只读保留至迁移、备份和观察期门槛完成。SQLite 是业务事实与可展示正文的权威来源；txtai 只承担语义导航与召回。

### 7.2 关键表和状态机

`documents` 保存文件元数据、初选/最终分区、状态、审核字段和安全错误；`chunk_candidates` 保存稳定 Chunk ID、原文顺序、正文、Embedding 文本、引用定位和索引时间；`hierarchy_nodes` 保存文档/章节节点元数据及校验和，不重复保存 Chunk 正文。

```text
uploaded -> parsing -> pending_review -> indexing -> ready
                    \                    \-> failed
                     \-> rejected

ready -> reindexing -> ready             (change partition)
ready -> reindexing -> pending_review    (reopen review)
stable -> deleting -> deleted
startup finds indexing/reindexing/deleting -> failed(recovery required)
```

聊天只接受 `ready` 且 `confirmed_partition` 等于当前检索分区的 Chunk。管理操作期间文档不处于 `ready`，不会被检索作为证据。

### 7.3 运行数据边界

日常验证不得写入 `data/raw`、`data/staging`、`data/indexes-hierarchical`、`data/indexes` 或 `data/metadata`。测试使用临时 SQLite、临时目录和 FakeTreeIndexRegistry。真实索引迁移、性能评测、Flat 清理和业务数据重建都需要明确的数据范围、备份与回滚方案。

## 8. API 如何传递数据

### 8.1 契约生成链

```text
Pydantic 请求/响应模型 + FastAPI 路由
  -> scripts/export_openapi.py
  -> contracts/openapi.json
  -> openapi-typescript
  -> frontend/src/api/generated.ts
  -> frontend/src/api/types.ts / client.ts
```

`contracts/openapi.json` 与 `frontend/src/api/generated.ts` 均为生成文件，禁止手工修改。字段变更必须先改 Schema 和服务生产者，补充定向测试，再导出 OpenAPI、生成前端类型并调整 Client/UI。

### 8.2 通用传递约定

- API 前缀为 `/api/v1`；JSON 字段采用 snake_case；上传使用 `multipart/form-data`。
- 请求模型默认禁止未知字段并去除字符串首尾空白。
- 日期以带时区 ISO 8601 返回；SQLite 无时区值在 API 层按 UTC 适配。
- 分页统一使用 `limit`、`offset`，响应回显二者并返回 `total`。
- 所有响应携带 `X-Request-ID`；非 2xx 使用统一错误体。
- Client 默认超时 30 秒；聊天 100 秒；上传、审核与文档管理操作 120 秒；有副作用请求不自动重试。

### 8.3 端点清单

| 方法 | 路径 | 成功响应 | 作用 |
| --- | --- | --- | --- |
| POST | `/api/v1/chat` | `ChatResponse`，200 | 路由、树状检索、回答和引用 |
| POST | `/api/v1/documents` | `UploadDocumentResponse`，201 | 上传、解析和 Chunking |
| GET | `/api/v1/documents` | `DocumentListResponse` | 筛选、分页文档目录 |
| GET | `/api/v1/documents/{document_id}` | `DocumentDetailResponse` | 文档详情与质量报告 |
| GET | `/api/v1/documents/{document_id}/preview` | `ChunkPreviewResponse` | 原文顺序 Chunk 预览 |
| POST | `/api/v1/documents/{document_id}/review` | `ReviewResponse` | 批准或拒绝 |
| POST | `/api/v1/documents/{document_id}/partition` | `ChangeDocumentPartitionResponse` | 调整 `ready` 文档分区 |
| POST | `/api/v1/documents/{document_id}/reopen-review` | `ReopenDocumentReviewResponse` | 移出索引并退回待审核 |
| DELETE | `/api/v1/documents/{document_id}` | `DeleteDocumentResponse` | 删除跨存储数据 |
| GET | `/api/v1/health` | `HealthResponse` 或 503 错误体 | SQLite、九层索引与 Provider 配置状态 |

### 8.4 聊天响应与错误不变量

`ChatResponse` 的 `route`、`searched_partitions`、`citations`、`web_citations` 和 `answer_source` 由后端 Pydantic 与前端 `assertChatContract` 共同校验：`clarify` 不得搜索分区；`composite` 必须恰有两个不同分区；内部与网页引用互斥；引用分区必须在实际搜索范围中。`timing.retrieval` 与实际搜索分区一一对应，模型耗时只在相应模型实际调用时返回。

所有非 2xx 响应使用：

```json
{
  "code": "STABLE_ERROR_CODE",
  "message": "可安全展示的信息",
  "request_id": "req_xxx",
  "details": null
}
```

前端按稳定 `code` 分支，不能解析中文 `message` 判断状态。聊天的澄清、无证据和敏感输入阻断是 HTTP 200 的业务结果，而不是 HTTP 错误。

## 9. 配置、部署形态和健康检查

### 9.1 本地与内网运行

Windows PowerShell 下，树状版本后端通常运行于 `127.0.0.1:8001`，Vite 前端运行于 `127.0.0.1:5174`。开发时前端默认使用 Vite `/api` proxy；分别部署时才配置 `VITE_API_BASE_URL` 和后端 `CORS_ORIGINS`。旧版可使用 `8000`/`5173` 并行对比，但两个版本不得共享 SQLite、原文件或 txtai 索引。

系统还支持由 FastAPI 托管 `frontend/dist` 的可信内网单端口模式。常态内网服务必须使用 `scripts/start_intranet.ps1` 建立受限 CIDR 的临时防火墙规则，并由另一台同网段设备完成访问确认；普通监听 `0.0.0.0` 只能证明连通性，不能证明来源访问受到限制。

### 9.2 关键配置组

| 配置组 | 典型变量 | 影响 |
| --- | --- | --- |
| 应用与内网 | `APP_HOST`、`APP_PORT`、`CORS_ORIGINS`、`SERVE_FRONTEND` | 监听、跨域和单端口静态托管 |
| 数据 | `DATA_ROOT`、`RAW_ROOT`、`STAGING_ROOT`、`HIERARCHICAL_INDEX_ROOT`、`METADATA_DATABASE_URL` | 文件、树索与 SQLite 位置 |
| 上传与 Chunk | `MAX_UPLOAD_SIZE_MB`、`ALLOWED_FILE_TYPES`、`CHUNK_*` | 接入规模和切分方式 |
| 检索 | `EMBEDDING_MODEL`、`RETRIEVAL_TOP_K`、`RETRIEVAL_MIN_SCORE`、`COMPOSITE_TOP_K_PER_PARTITION` | 召回、最低相关性阈值与预算 |
| 树状检索 | `HIERARCHICAL_DOCUMENT_BEAM_WIDTH`、`HIERARCHICAL_SECTION_BEAM_WIDTH`、`HIERARCHICAL_LEAF_CANDIDATE_LIMIT` | 父节点 Beam 与叶子候选预算 |
| LLM | `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`、`ROUTER_LLM_MODEL`、`ANSWER_LLM_MODEL` | 路由与回答能力 |
| 联网 | `WEB_SEARCH_ENABLED`、`WEB_SEARCH_API_KEY`、`WEB_SEARCH_TIMEOUT_SECONDS` | 默认关闭的 Tavily 兜底 |

`RETRIEVAL_MIN_SCORE` 默认 `0.5`，只适用于当前演示模型与数据。更换 Embedding 模型、语言、Chunk 结构或知识数据后，应以少量只读问题重新校准。

### 9.3 健康检查的含义

`GET /api/v1/health` 主动检查 SQLite，并按 finance/hr/tech 分区分别报告 document、section、chunk 三层索引是否加载。任一必需层异常会使服务返回 degraded/503。Router、Answer 与 Web Search 的 `configured` 仅表示配置齐全，不代表外部端点已主动探活或真实调用成功；未配置模型仍可手动路由和抽取式回答。

## 10. 安全、可靠性和当前验证结论

### 10.1 已实现的主要防线

- 上传有扩展名、签名、编码、大小、路径清理和重复内容校验。
- 未审核文档不入索引，`ready + confirmed_partition` 是聊天证据的硬门槛。
- 树索将 document、section、chunk 逐层收窄，Chunk 使用精确文档/章节范围，并由 SQLite 再校验。
- 手动选区优先，自动复合检索严格限制为最多两个分区。
- 秘密值不会进入索引或模型；个人信息与私网地址先脱敏。
- 内部 Chunk 引用和网页 URL 都必须属于本轮受控证据集合。
- 条件状态声明、逐层验证、稳定 ID 补偿和启动恢复降低跨存储不一致风险。
- 非 2xx 隐藏内部细节，所有响应包含 Request ID。

### 10.2 最近记录的验证

2026-09-04 的 tree-only 实施记录显示：后端隔离测试 70/70、前端 Vitest 38/38、Python compileall、Ruff 和前端生产构建均通过；OpenAPI 与前端生成类型已重新生成，重复生成的 SHA-256 一致。验证使用临时 SQLite、临时目录、Fake LLM 与 FakeTreeIndexRegistry，未修改现有运行数据，也未执行真实业务数据迁移或真实 txtai 性能验证。

已完成两条真实 Router/Answer 协议兼容性冒烟，但没有批量路由或回答质量评估。真实 Tavily 搜索一次返回 HTTP 401，故网页回答真实成功路径仍未验证。完整 Playwright E2E、业务验收、路由质量评测和大规模索引压测不属于本轮默认验证。

### 10.3 汇报时应主动说明的风险

1. tree-only 运行代码已完成，但真实业务数据迁移、目录切换、观察期和旧 Flat 数据清理尚未执行。
2. txtai 默认 FAISS 不提供大规模 IVF 的原生 metadata 预过滤；当前通过扩大候选后过滤保证范围正确性，真实规模的性能仍未知。
3. SQLite、文件系统和 txtai 没有跨存储事务；补偿失败与进程崩溃后的恢复仍需人工处理。
4. 上传、解析和索引写入使用同步 HTTP 请求，大文档或慢模型会占用请求时间。
5. `RETRIEVAL_MIN_SCORE=0.5`、真实模型质量、真实搜索可用性和费用尚未以代表性数据验证。
6. 没有认证、权限隔离和审计，不能接收共享环境中的真实敏感知识。

## 11. 建议的汇报表达顺序

1. 先讲目标：构建一个有审核边界、分区隔离和可追溯引用的知识库，而不是通用聊天机器人。
2. 讲数据闭环：上传 -> 候选 Chunk -> 人工审核 -> 三层树索 -> `ready` 证据问答。
3. 强调新版本变化：运行时检索已收敛为 `document -> section -> chunk`，父节点只导航，Flat fallback 已移除。
4. 说明隔离与可信性：手动优先、自动最多两区、叶子 Chunk 仍要经过 SQLite 的状态与分区复核。
5. 说明可维护性：目录和详情统一管理审核、分区迁移、重新审核和删除，并以状态机与补偿处理跨存储操作。
6. 最后说明 MVP 边界与下一阶段重点：获批执行真实树索迁移、完成真实数据与模型评测、补足认证授权、异步任务、失败重试与可观测性。

## 12. 代码阅读索引

| 主题 | 首要文件 |
| --- | --- |
| 应用工厂、异常、Request ID、静态托管 | `app/main.py` |
| 配置 | `app/core/config.py`、`.env.example` |
| ORM、状态与启动恢复 | `app/db/tables.py`、`app/db/session.py` |
| 文档 HTTP API | `app/api/documents.py` |
| 聊天与健康 HTTP API | `app/api/chat.py`、`app/api/health.py` |
| 接入 | `app/services/ingestion.py`、`file_storage.py`、`parser.py`、`chunker.py` |
| 审核与跨存储文档管理 | `app/services/review.py`、`document_management.py` |
| 三层树索与节点构建 | `app/services/hierarchical_index.py`、`hierarchy_builder.py`、`hierarchical_retriever.py` |
| 聊天编排与叶子校验 | `app/services/chat.py`、`retriever.py`、`routing.py`、`answering.py` |
| 联网限制 | `app/services/web_search.py` |
| API 模型 | `app/models/schemas.py`、`app/models/enums.py` |
| 前端请求适配 | `frontend/src/api/client.ts`、`frontend/src/api/types.ts` |
| 页面路由和知识库管理 UI | `frontend/src/App.tsx`、`frontend/src/pages/KnowledgeLibraryPage.tsx`、`frontend/src/pages/ReviewPage.tsx` |
| 聊天会话 | `frontend/src/features/chat/ChatSessionContext.tsx` |
| 权威 HTTP 快照 | `contracts/openapi.json` |

相关现行设计文档：`docs/architecture/system-overview.md`、`docs/architecture/data-and-storage.md`、`docs/features/`、`docs/contracts/api-conventions.md`、`docs/operations/local-development.md` 和 `docs/testing/strategy.md`。
