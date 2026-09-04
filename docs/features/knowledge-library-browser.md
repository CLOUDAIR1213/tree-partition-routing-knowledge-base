# 知识库目录与文档详情

> 文档状态：已实现  
> 最近核对：2026-09-03  
> 代码基线：`9221517` 加当前工作树快照  
> 维护责任：待指定

## 1. 功能说明

本功能为知识库维护者提供统一的目录与详情入口，用来确认系统保存了哪些文档、每份文档处于什么状态、最终属于哪个分区、按什么顺序生成了哪些 Chunk，以及是否已经具备聊天检索资格。维护者还可在详情页删除文档、直接调整已入库文档的最终分区，或将其从索引移除后退回重新审核。

SQLite 中的文档状态、分区和 Chunk 正文是页面事实来源；页面不直接读取 txtai 文件或展示向量。目录页使用现有详情和 Chunk 预览 API，审核页升级为所有状态可读的文档详情页，仅在待审核状态显示审核操作。

## 2. 范围与非目标

| 类型 | 内容 |
| --- | --- |
| 包含 | 知识库入口；分页目录；状态、有效分区、标题/文件名筛选；全状态详情；按 `chunk_index` 展示 Chunk；待审核操作；已入库文档更改分区和重新审核；稳定状态文档删除；上传后的统一详情；旧审核链接兼容 |
| 不包含 | 批量操作；编辑原文或 Chunk；拖拽排序；重新解析；从原文件重建 Chunk；全库索引重建；向量可视化；Chunk 全文检索；不可变审计历史；认证与角色权限 |

管理操作跨越 SQLite、原文件、解析快照与 txtai，因此由独立服务编排状态抢占、索引验证与失败补偿。

## 3. 用户流程与状态

1. 用户从侧栏进入 `/knowledge`，页面按创建时间倒序加载文档。
2. 用户按状态、分区和标题/原文件名关键词筛选，筛选变化时回到第一页。
3. 每行展示标题、原文件名、状态、有效分区、Chunk 数量和更新时间。
4. 用户进入 `/knowledge/documents/:documentId` 查看详情。
5. 详情先加载文档元数据；有 Chunk 时再独立加载预览。
6. Chunk 始终按 `chunk_index` 升序显示，不按章节名、页码或检索相关度重排。
7. 只有 `pending_review` 显示批准和拒绝；只有 `ready` 显示“可检索”。
8. 上传成功跳转统一详情；旧的 `/knowledge/review/:documentId` 重定向到新地址。
9. `ready` 文档可直接选择新分区；系统先写入并验证新索引，再清理其他分区，最后更新 SQLite 最终分区和审核字段。
10. `ready` 文档可退回重新审核；系统先从三个索引删除该文档 Chunk，再清空最终分区和 `indexed_at`，状态回到 `pending_review`。
11. `pending_review`、`ready`、`rejected` 和 `failed` 可删除；系统清理三个索引、原文件、解析快照后，删除 SQLite 文档和级联 Chunk。

| 当前状态 | 页面表达 | 可执行操作 | 后续结果 |
| --- | --- | --- | --- |
| `uploaded` | 已上传，等待解析 | 刷新、返回目录 | `parsing` 或 `failed` |
| `parsing` | 正在解析 | 刷新、返回目录 | `pending_review` 或 `failed` |
| `pending_review` | 已解析，尚不可检索 | 批准或拒绝 | `indexing`、`rejected` |
| `indexing` | 正在写入索引 | 刷新、返回目录 | `ready` 或 `failed` |
| `reindexing` | 正在更改分区或移出索引 | 刷新、返回目录 | `ready`、`pending_review` 或 `failed` |
| `deleting` | 正在清理跨存储数据 | 刷新、返回目录 | 记录消失或 `failed` |
| `ready` | 已入库，可在最终分区检索 | 查看 Chunk、更改分区、重新审核、删除 | 保持 `ready`、`reindexing` 或 `deleting` |
| `rejected` | 已拒绝，不可检索 | 查看原因和 Chunk、删除 | `deleting` |
| `failed` | 处理失败，不可检索 | 查看安全错误、删除 | `deleting` |

失败状态不承诺 txtai 内绝对没有残留；聊天侧仍通过 SQLite 的 `ready` 和最终分区过滤证据。

## 4. 前端实现

| 路径或组件 | 职责 | 关键状态或行为 |
| --- | --- | --- |
| `frontend/src/pages/KnowledgeLibraryPage.tsx` | 目录编排 | URL 筛选、分页、请求竞态、空态与重试 |
| `frontend/src/pages/ReviewPage.tsx` | 通用详情、审核和管理操作 | 元数据和预览独立加载；按状态显示批准、改分区、重新审核或删除；破坏性操作使用确认对话框 |
| `frontend/src/components/KnowledgeDocumentTable.tsx` | 文档列表 | 桌面表格、移动端紧凑行、整行导航 |
| `frontend/src/components/KnowledgeFilters.tsx` | 筛选工具栏 | 搜索、状态、分区、清除筛选 |
| `frontend/src/components/ChunkPreviewList.tsx` | Chunk 展示 | 复用分页与展开，严格按后端顺序显示 |
| `frontend/src/components/DocumentStatusBadge.tsx` | 状态标签 | 复用九种状态映射 |
| `frontend/src/App.tsx` | 路由 | 新增目录和详情，旧审核地址重定向 |
| `frontend/src/components/layout/AppSidebar.tsx` | 全局入口 | “知识库”以普通单行导航固定在最近会话之后、用户区之前，并显示当前页状态；最近会话继续占用侧栏剩余高度 |

URL 保存可恢复的页面状态：

```text
/knowledge?q=VPN&status=ready&partition=tech&page=2
```

搜索约 300 毫秒防抖，状态和分区立即生效。非法筛选回退到全部，非法页码回退到第 1 页。请求状态留在页面组件，不新增全局状态库；使用请求序号避免旧响应覆盖新筛选。

目录采用工作型表格，不使用卡片瀑布流。标题为空时显示原文件名；分区有 `confirmed_partition` 时显示最终分区，否则显示初选分区并标记“待确认”。窄屏保留标题、状态、分区和 Chunk 数，次要时间信息换行。

## 5. 后端实现

列表 API 支持状态、分页、有效分区和标题/文件名关键词筛选。`DocumentManagementService` 负责删除、改分区和重新审核的跨存储编排。

| 路径或服务 | 职责 | 上下游依赖 |
| --- | --- | --- |
| `app/api/documents.py` | 扩展列表过滤，复用详情和预览 | SQLAlchemy、SQLite、Schema |
| `app/models/schemas.py` | 复用现有响应模型 | OpenAPI、前端生成类型 |
| `app/db/tables.py` | 复用文档和 Chunk 字段 | 不计划改 Schema |
| `app/services/review.py` | 批准/拒绝和索引写入 | 复用现有状态与补偿 |
| `app/services/index_registry.py` | txtai 管理 | 目录和详情不直接调用 |
| `app/services/document_management.py` | 文档生命周期管理 | SQLite、FileStorage、IndexRegistry；条件抢占与失败补偿 |

列表查询语义：

- `status` 精确匹配文档状态。
- `partition` 匹配有效分区：确认分区非空时取确认分区，否则取初选分区。
- `q` 去除首尾空白后，对标题和原文件名做大小写不敏感包含匹配，不搜索 Chunk 正文，最长 200 字符。
- 多个条件按 AND 组合，总数和列表使用同一组条件。
- 排序固定为 `created_at DESC, id DESC`，确保同时间戳分页稳定。

当前规模可直接使用 SQLite 包含查询；达到数万文档后再评估 FTS。详情页面不通过 txtai 判断可检索状态，而是继续使用 `status == ready` 且最终分区非空的业务语义。

## 6. 数据库与存储

| 存储类型 | 表、目录或索引 | 读/写 | 用途与一致性要求 |
| --- | --- | --- | --- |
| SQLite | `documents` | 读/写/删 | 目录、详情、状态和分区的权威来源；管理操作写状态、最终分区和最后审核字段 |
| SQLite | `chunk_candidates` | 读/写/删 | 按 `chunk_index` 分页且不返回 `embedding_text`；改分区重写 `indexed_at`；重新审核清空；删除文档时级联删除 |
| 文件 | `data/raw/<document_id>/` | 删 | 仅删除文档操作访问，页面不暴露服务器路径 |
| 文件 | `data/staging/<document_id>/parse.json` | 读/删 | 详情读取质量报告；删除文档时清理 |
| txtai | `data/indexes/<partition>/` | 写/删 | 改分区时保留一个权威分区；重新审核和删除时清理三个分区 |

本功能不新增数据库迁移。详情和 Chunk 分开请求，因此预览失败不影响文档元数据展示。

## 7. API 接口

| 方法 | 路径 | 用途 | 请求模型 | 响应模型 | 主要错误码 |
| --- | --- | --- | --- | --- | --- |
| `GET` | `/api/v1/documents` | 分页目录，支持 `partition`、`q` | Query | `DocumentListResponse` | `INVALID_PARTITION`、`VALIDATION_ERROR` |
| `GET` | `/api/v1/documents/{document_id}` | 文档详情 | Path | `DocumentDetailResponse` | `DOCUMENT_NOT_FOUND` |
| `GET` | `/api/v1/documents/{document_id}/preview` | 顺序化 Chunk 预览 | Query | `ChunkPreviewResponse` | `DOCUMENT_NOT_FOUND`、`PREVIEW_NOT_READY` |
| `POST` | `/api/v1/documents/{document_id}/review` | 待审核批准或拒绝 | `ReviewRequest` | `ReviewResponse` | `INVALID_DOCUMENT_STATE`、`REVIEW_PARTITION_REQUIRED`、`INDEX_WRITE_FAILED` |
| `POST` | `/api/v1/documents/{document_id}/partition` | 更改 `ready` 文档最终分区 | `ChangeDocumentPartitionRequest` | `ChangeDocumentPartitionResponse` | `INVALID_DOCUMENT_STATE`、`PARTITION_UNCHANGED`、`PARTITION_CHANGE_FAILED` |
| `POST` | `/api/v1/documents/{document_id}/reopen-review` | 从索引移除并退回待审核 | `ReopenDocumentReviewRequest` | `ReopenDocumentReviewResponse` | `INVALID_DOCUMENT_STATE`、`REOPEN_REVIEW_FAILED` |
| `DELETE` | `/api/v1/documents/{document_id}` | 删除文件、Chunk、元数据和索引 | 无 | `DeleteDocumentResponse` | `INVALID_DOCUMENT_STATE`、`DOCUMENT_DELETE_FAILED` |

权威契约：`contracts/openapi.json`  
生成命令：`uv run --no-sync python -m scripts.export_openapi`，随后在 `frontend` 执行 `npm run api:types`。

响应模型不增加重复的“是否已索引”字段，前端由 `status === "ready"` 推导可检索展示。

## 8. 文件路径与修改边界

| 文件或目录 | 职责 | 修改级别 | 修改要求 |
| --- | --- | --- | --- |
| `docs/features/knowledge-library-browser.md` | 本功能文档 | `owned` | 实施时同步状态和验证结果 |
| `frontend/src/pages/KnowledgeLibraryPage.tsx` | 目录页 | `owned` | URL 筛选、分页和空态 |
| `frontend/src/components/KnowledgeDocumentTable.tsx` | 列表 | `owned` | 文档元数据与详情导航 |
| `frontend/src/components/KnowledgeFilters.tsx` | 筛选 | `owned` | 标题、状态和分区筛选 |
| `frontend/src/pages/ReviewPage.tsx` | 全状态详情和审核行为 | `shared` | 保留测试和旧链接兼容 |
| `frontend/src/components/ChunkPreviewList.tsx`、`DocumentStatusBadge.tsx` | 共享展示 | `shared` | 检查所有消费者 |
| `frontend/src/App.tsx`、`frontend/src/components/layout/` | 路由与导航 | `shared` | 检查聊天、上传、审核和移动端 |
| `frontend/src/api/client.ts`、`types.ts` | API 适配 | `shared` | 以生成类型为准 |
| `app/api/documents.py` | 文档 API | `shared` | 保持既有端点兼容 |
| `app/services/document_management.py` | 管理操作和补偿 | `owned` | 同时检查 SQLite、文件和三个 txtai 索引 |
| `app/services/index_registry.py` | 索引写入、删除和全 Chunk 验证 | `shared` | 检查审核、检索、健康和启动流程 |
| `app/models/enums.py`、`app/models/schemas.py`、`app/db/session.py` | 状态、API 契约和中断恢复 | `shared` | 同步前端状态和生成契约 |
| `contracts/openapi.json`、`frontend/src/api/generated.ts` | 契约产物 | `generated` | 只能运行生成命令更新 |
| `tests/integration/test_documents_api.py`、`frontend/src/App.test.tsx` | 验证 | `shared` | 使用临时数据和 Mock |
| `data/raw/`、`data/staging/`、`data/indexes/`、`data/metadata/` | 真实数据 | `runtime-data` | 实施验证不得修改 |
| 普通失败重试、重新解析、全库索引重建 | 跨存储生命周期 | `approval-required` | 需独立设计并获得明确方向 |

## 9. 核心不变量与安全约束

- 目录和详情以 SQLite 为权威来源，不直接读取 txtai 文件。
- 只有 `ready` 且有最终分区的文档显示为可检索。
- Chunk 按 `chunk_index` 升序展示，章节和页码不能改变顺序。
- 分区筛选与展示统一采用“确认分区优先，否则初选分区”。
- API 和页面不得显示 `stored_path`、checksum、`embedding_text`、索引目录或堆栈。
- 审核继续由后端保证 `pending_review` 的单次状态声明。
- 删除、改分区和重新审核必须先用条件更新抢占状态；`indexing`、`reindexing`、`deleting`、`uploaded` 和 `parsing` 不允许并发管理。
- 管理操作期间文档不是 `ready`，聊天检索必须忽略它。
- 更改分区后，全部 Chunk 必须在新分区可验证，且在其他两个分区不存在，才能恢复 `ready`。
- 重新审核后 `confirmed_partition` 和所有 Chunk `indexed_at` 必须为 null，三个索引中都不得保留该文档 Chunk。
- 删除成功后三个索引、raw、staging、`documents` 和 `chunk_candidates` 都不得再保留该文档。
- 页面必须解释详情顺序是原文顺序，聊天召回顺序是语义相关度顺序。

## 10. 错误处理与恢复

| 场景 | 对外表现 | 内部处理 | 恢复方式 |
| --- | --- | --- | --- |
| 目录加载失败 | 页面错误和重试 | 保留 URL 筛选 | 用户重试 |
| 筛选竞态 | 只显示最新请求 | 丢弃过期响应 | 自动 |
| 页码越界 | 回到最后有效页或第 1 页 | 校正 URL，避免循环 | 自动一次 |
| 文档不存在 | 明确不存在 | 处理 `DOCUMENT_NOT_FOUND` | 返回目录 |
| 详情成功、预览失败 | 元数据保留，Chunk 区报错 | 两个请求独立 | 单独重试 |
| 尚无 Chunk | 显示处理状态 | 不把 409 当整页失败 | 稍后刷新 |
| 并发审核冲突 | 提示状态变化 | 处理 `INVALID_DOCUMENT_STATE` | 重新读取 |
| 索引写入失败 | 显示失败且不可检索 | 沿用补偿逻辑 | 当前人工排查 |
| 改分区失败 | 500 `PARTITION_CHANGE_FAILED` | 删除新分区行并恢复旧分区；补偿失败则标记 `failed` | 补偿成功后保持原分区；否则人工检查 |
| 重新审核的移除失败 | 500 `REOPEN_REVIEW_FAILED` | 尝试恢复原分区唯一索引 | 补偿成功后保持 `ready` |
| 删除索引失败 | 500 `DOCUMENT_DELETE_FAILED` | 保留文件与 SQLite，状态改为 `failed` | 在详情页重试删除 |
| 删除文件或 SQLite 失败 | 500 `DOCUMENT_DELETE_FAILED` | 索引已清理，保留可重试的 `failed` 记录 | 重试删除 |
| 应用在 `reindexing`/`deleting` 中断 | 下次启动显示 `failed` | 写入 `REINDEX_RECOVERY_REQUIRED` 或 `DELETE_RECOVERY_REQUIRED` | 人工检查；删除可直接重试 |

## 11. 测试与验证

| 层级 | 覆盖内容 | 文件或命令 |
| --- | --- | --- |
| 后端集成 | 状态、有效分区、关键词、组合过滤、稳定分页和非法参数 | `tests/integration/test_documents_api.py` |
| 前端 API | 查询参数编码和错误体 | `frontend/src/api/client.test.ts` |
| 前端页面 | 列表、筛选、分页、空态、重试和详情导航 | `frontend/src/App.test.tsx` 或新增页面测试 |
| 前端页面 | 九种状态、审核可见性、详情/预览独立失败、Chunk 顺序 | `frontend/src/App.test.tsx` |
| 后端集成 | 删除四类存储、分区迁移、重新审核、非法状态和补偿 | `tests/integration/test_documents_api.py` |
| 前端 API/页面 | 三个管理端点、确认对话框、状态刷新和删除后返回目录 | `frontend/src/api/client.test.ts`、`frontend/src/App.test.tsx` |
| 契约 | OpenAPI 与生成类型同步 | `uv run --no-sync python -m scripts.export_openapi`、`npm run api:check` |
| 构建 | TypeScript 与 Vite | `npm run build` |
| 响应式 | 三种视口的列表与详情 | `frontend/tests/e2e/responsive.spec.ts`，仅用户明确要求时运行 |

实施后的最低验证为文档 API 定向测试、前端 API/页面测试、前端构建、OpenAPI 检查和 Ruff。全部测试使用临时 SQLite 与 FakeIndexRegistry，不修改现有运行数据。

本次已核对文档导航、系统总览、接入、审核、存储、API、测试文档，以及实际路由、页面、组件、后端端点、Schema、测试和 Git 状态。2026-09-03 实际执行：后端全量测试 45/45 通过；前端 Vitest 37/37 通过；前端生产构建通过；OpenAPI 快照与应用 Schema 一致，前端类型连续两次生成哈希一致；Ruff 通过；本地目录、详情、管理操作区和改分区对话框的只读浏览器检查通过，无控制台错误。未运行完整 E2E，浏览器检查未提交任何管理操作。

## 12. 已知限制与后续计划

- 当前列表只支持标题/文件名包含搜索，不搜索 Chunk 正文。
- 当前页面不自动轮询 `uploaded`、`parsing` 或 `indexing`；用户可刷新页面读取最新状态。
- 当前不存在待审核数量统计、来源或时间范围筛选。
- 尚无批量删除、从原文件重新解析、普通失败状态重试和全库索引重建。
- 审核与管理备注仅保留最后一次操作字段，尚无追加式、不可变的审计历史。
- SQLite 与 txtai 仍无共同事务；当进程在索引操作与 SQLite 最终提交之间崩溃时，文档会转为 `failed` 并需人工检查。
- 检索分数诊断、认证、审核角色和审计仍未实现。
