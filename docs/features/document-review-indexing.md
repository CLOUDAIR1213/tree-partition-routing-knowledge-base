# 文档审核与索引

> 文档状态：已实现  
> 最近核对：2026-09-07
> 代码基线：工作树快照（本目录不是 Git 仓库）  
> 维护责任：待指定

## 1. 功能说明

审核功能让用户查看文档详情、完整 Chunk 预览、解析质量报告和非权威分区建议，明确确认最终唯一分区后，批准写入对应 txtai 索引或拒绝入库。它是未审核内容与聊天可检索内容之间的强制边界。

## 2. 范围与非目标

| 类型 | 内容 |
| --- | --- |
| 包含 | 文档列表；详情；完整 Chunk 分页预览；解析质量和分区建议展示；最终分区确认；审核备注；批准；拒绝；索引写入；失败补偿；状态展示 |
| 不包含 | 身份认证；审核角色；多人审批流；普通失败重试；重新解析；全库索引重建 |

`ready` 文档的删除、分区调整和退回重新审核由[知识库目录与文档详情](knowledge-library-browser.md)负责；退回后再次批准仍使用本功能的 `pending_review -> indexing -> ready` 流程。

## 3. 用户流程与状态

1. 上传成功后前端进入 `/knowledge/documents/:documentId`；旧的 `/knowledge/review/:documentId` 会重定向到该地址。
2. 页面读取详情和第一页完整 Chunk，每页 20 条；任一 Chunk 预览请求失败时，保留详情但禁止批准。
3. 页面展示快照中的章节、Chunk、标题识别率、空白页、表格、异常长度、警告和内容建议。
4. `pending_review` 状态下最终分区初始为空，用户必须明确选择；内容建议不自动选中任何分区。
5. 用户确认完整 Chunk 内容、选择最终分区并填写可选备注后批准，或填写拒绝原因后拒绝。
5. 批准请求先用条件更新把文档声明为 `indexing`，再把全部 Chunk、文档节点和章节节点写入最终分区的三层树索。
6. 三层全部验证成功后写入 Chunk/节点 `indexed_at` 并把文档改为 `ready`。
7. 如果批准请求超过前端 120 秒上限，页面读取文档详情；状态为 `indexing` 时每秒轮询，直到进入 `ready`、`failed` 或其他稳定状态。轮询期间保留审核草稿并禁用重复操作。
8. 拒绝直接改为 `rejected`，不访问任何索引。
9. `ready` 页面提供返回聊天并预选最终分区的入口。

| 当前状态 | 操作或条件 | 下一状态 | 失败处理 |
| --- | --- | --- | --- |
| `pending_review` | reject 且无 confirmed_partition | `rejected` | 并发声明失败返回 409 |
| `pending_review` | approve 且有 confirmed_partition | `indexing` | 缺少分区返回 422 |
| `indexing` | 索引保存和验证成功 | `ready` | 设置所有 Chunk `indexed_at` |
| `indexing` | 索引写入或验证失败 | `failed` | 删除本次 Chunk ID，记录补偿结果 |
| `indexing` | 应用重启 | `failed` | 启动恢复标记 `INDEX_RECOVERY_REQUIRED` |
| 非 `pending_review` | 再次审核 | 状态不变 | 409 `INVALID_DOCUMENT_STATE` |

## 4. 前端实现

| 路径或组件 | 职责 | 关键状态或行为 |
| --- | --- | --- |
| `frontend/src/pages/ReviewPage.tsx` | 页面编排 | 读取详情/预览，维护分页、人工分区、备注、批准/拒绝状态；预览失败时禁用批准；审批超时或初次读到 `indexing` 时自动轮询并阻止重复操作 |
| `frontend/src/components/ChunkPreviewList.tsx` | Chunk 展示 | 每页 20 条、完整正文展开、上一页/下一页 |
| `frontend/src/components/ParseQualitySummary.tsx` | 解析质量展示 | 指标、警告和非权威内容分区建议 |
| `frontend/src/components/DocumentStatusBadge.tsx` | 状态标签 | 覆盖 7 种 DocumentStatus |
| `frontend/src/components/PartitionSelector.tsx` | 最终分区 | 只允许三个明确分区 |
| `frontend/src/api/client.ts` | 文档查询和审核 | GET 默认 30 秒；review POST 120 秒；不自动重试 |

前端只在 `pending_review` 开启审核控件。拒绝对话框要求非空原因，而后端 `note` 本身是可选字段；这是当前前端比 API 更严格的交互约束。

## 5. 后端实现

| 路径或服务 | 职责 | 上下游依赖 |
| --- | --- | --- |
| `app/api/documents.py` | 列表、详情、预览和审核端点 | AsyncSession、ReviewService、树索注册表 |
| `app/services/review.py` | 状态声明、三层树索写入和补偿 | ORM、HierarchicalIndexRegistry、anyio thread |
| `app/services/hierarchical_index.py` | 三层 upsert/save/verify/delete | txtai Embeddings 和每分区/层级 RLock |
| `app/services/ingestion.py` | 文档查找帮助函数 | DocumentTable |
| `app/db/session.py` | 启动恢复 | 把遗留 indexing 标记 failed |
| `app/models/schemas.py` | ReviewRequest/Response | ReviewAction、Partition、DocumentStatus |

批准时先提交 SQLite 的 `indexing` 状态，再在线程中执行同步 txtai 写入。这个顺序允许并发审核只有一个请求取得文档，但也意味着 SQLite 与索引之间需要显式补偿。后端以 `review_index_stage` 分别记录 chunk、document、section 的 upsert/verify 数量、耗时和结果，并以 `review_index_completed` 记录整体耗时；日志不包含正文、文件路径或密钥。

## 6. 数据库与存储

| 存储类型 | 表、目录或索引 | 读/写 | 用途与一致性要求 |
| --- | --- | --- | --- |
| SQLite | `documents` | 读写 | 状态、最终分区、审核信息和错误 |
| SQLite | `chunk_candidates` | 读写 | 预览、索引输入和 `indexed_at` |
| txtai | `data/indexes-hierarchical/<confirmed_partition>/chunk/` | 写/删除 | 唯一 Chunk 索引；失败时按 Chunk ID 补偿 |
| SQLite/txtai | `hierarchy_nodes`、`data/indexes-hierarchical/<partition>/{document,section}/` | 读写/删除 | 持久化文档和章节路由节点；失败时按节点 ID 补偿 |
| 原文件/解析快照 | `data/raw/`、`data/staging/` | 只读 | API 从 `parse.json` 读取质量报告；前端不直接读取运行目录 |

拒绝不删除原文件和 Chunk，也不写索引。详情和预览可继续读取已拒绝或失败的文档，只是审核操作会被状态检查拒绝。

## 7. API 接口

| 方法 | 路径 | 用途 | 请求模型 | 响应模型 | 主要错误码 |
| --- | --- | --- | --- | --- | --- |
| `GET` | `/api/v1/documents` | 状态、有效分区、标题/文件名筛选和分页列表 | query params | `DocumentListResponse` | `INVALID_PARTITION`、`VALIDATION_ERROR` |
| `GET` | `/api/v1/documents/{document_id}` | 读取详情、审核结果和可用质量报告 | path param | `DocumentDetailResponse` | `DOCUMENT_NOT_FOUND` |
| `GET` | `/api/v1/documents/{document_id}/preview` | 分页读取完整 Chunk 和可用质量报告 | query params | `ChunkPreviewResponse` | `DOCUMENT_NOT_FOUND`、`PREVIEW_NOT_READY` |
| `POST` | `/api/v1/documents/{document_id}/review` | approve 或 reject | `ReviewRequest` | `ReviewResponse` | `INVALID_DOCUMENT_STATE`、`REVIEW_PARTITION_REQUIRED`、`VALIDATION_ERROR`、`INDEX_WRITE_FAILED` |

文档 ID 路径必须匹配 `doc_[0-9a-f]{24}`。列表和预览 `limit` 为 1 到 100，`offset` 不得为负数。

权威契约：`contracts/openapi.json`  
契约生成命令：`uv run --no-sync python -m scripts.export_openapi`

## 8. 文件路径与修改边界

| 文件或目录 | 职责 | 修改级别 | 修改要求 |
| --- | --- | --- | --- |
| `frontend/src/pages/ReviewPage.tsx` | 审核页面 | `owned` | 同步批准/拒绝页面测试 |
| `frontend/src/components/ChunkPreviewList.tsx` | 预览和分页 | `owned` | 保持后端 limit/offset 语义 |
| `frontend/src/components/ParseQualitySummary.tsx` | 质量与建议展示 | `owned` | 建议必须始终标为非权威 |
| `frontend/src/components/DocumentStatusBadge.tsx` | 状态展示 | `owned` | 新状态需同步枚举和样式 |
| `app/services/review.py` | 审核编排 | `owned` | 重点检查并发、补偿和状态机 |
| `app/api/documents.py` | 文档 HTTP 入口 | `shared` | 同时影响接入功能和 OpenAPI |
| `app/services/hierarchical_index.py` | 三层索引注册表 | `shared` | 同时影响聊天检索、启动和健康检查 |
| `app/db/tables.py`、`app/db/session.py` | 状态持久化与恢复 | `shared` | 检查接入和聊天过滤 |
| `app/models/enums.py`、`app/models/schemas.py` | 状态和契约 | `shared` | 同步前端生成类型与状态组件 |
| `frontend/src/api/generated.ts`、`contracts/openapi.json` | 生成契约 | `generated` | 只通过生成流程更新 |
| `data/indexes-hierarchical/`、`data/metadata/`、`data/raw/`、`data/staging/` | 运行数据 | `runtime-data` | 测试必须使用临时目录或 Fake |
| 多级审批、权限、生产审计 | 生产流程 | `approval-required` | 需要业务责任和安全决策 |

## 9. 核心不变量与安全约束

- 只有 `pending_review` 文档可以审核。
- approve 必须提供一个最终分区；reject 必须让 `confirmed_partition` 为 null。
- 前端在 Chunk 完整预览不可用时不得发送 approve；后端仍以 `pending_review`、有 Chunk 和 `confirmed_partition` 作为写入守卫。
- 内容建议不能自动填充或覆盖最终分区，最终分区必须由审核人明确选择。
- 一份文档的 document、section、chunk 三层只存在于一个最终分区。
- 并发审核只能有一个请求取得 `pending_review -> indexing/rejected` 状态。
- 任一树索层失败不得把文档标记为 `ready`。
- `ready` 只表示写入流程完成，不代表内容质量、权限或合规审查已完成。
- 当前没有真实审核身份，`reviewer_name` 来自请求且没有认证保证。

## 10. 错误处理与恢复

| 场景 | 对外表现 | 内部处理 | 恢复方式 |
| --- | --- | --- | --- |
| 文档不存在 | 404 `DOCUMENT_NOT_FOUND` | 不查询 Chunk/索引 | 检查 URL 或重新上传 |
| 没有 Chunk | 409 `PREVIEW_NOT_READY` | 不审核 | 检查接入失败状态 |
| 重复或并发审核 | 409 `INVALID_DOCUMENT_STATE` | 条件更新失败并 rollback | 刷新文档状态 |
| approve 缺分区 | 422 `REVIEW_PARTITION_REQUIRED` | 不改状态 | 选择最终分区 |
| reject 带分区 | 422 `VALIDATION_ERROR` | 不改状态 | 提交 null |
| 索引写入失败 | 500 `INDEX_WRITE_FAILED` | 删除本次 ID，文档 failed | 检查补偿结果后人工重建/重试 |
| 审批请求在前端 120 秒超时 | 页面显示正在确认入库结果并禁用重复操作 | 浏览器中止请求不会取消后端同步树索写入；页面立即回查并对 `indexing` 每秒轮询 | `ready` 自动切换成功状态；`failed` 显示错误；连续三次仍为 `pending_review` 才允许重新批准 |
| 启动发现 indexing | 健康启动后文档 failed | `INDEX_RECOVERY_REQUIRED` | 人工检查索引并恢复 |

## 11. 测试与验证

| 层级 | 覆盖内容 | 文件或命令 |
| --- | --- | --- |
| 后端集成 | 预览、分区修正、拒绝、状态校验、补偿 | `tests/integration/test_documents_api.py` |
| 测试隔离 | 临时 SQLite 和 FakeTreeIndexRegistry | `tests/conftest.py` |
| 前端组件 | 详情/完整预览、质量报告、人工分区、预览失败时禁用批准，以及审批超时后 `indexing -> ready` 自动恢复且只提交一次 | `frontend/src/App.test.tsx` |
| 前端 API | review 路径、字段和超时层 | `frontend/src/api/client.test.ts` |

2026-09-04：tree-only 改造后后端 70/70、前端 38/38、Python compileall、Ruff 和生产构建通过，包含三层审核写入、拒绝、补偿、删除、分区迁移与重新审核。没有对真实 txtai 部分写入、进程崩溃窗口或并发多请求进行压力测试。

2026-09-07：审批超时恢复与索引阶段耗时日志完成。后端 73 项通过、1 项显式真实服务测试跳过，前端 39/39、生产构建、Python compileall 和 Ruff 通过；新增前端回归覆盖超时后 `indexing -> ready` 自动恢复和审批只提交一次。验证使用 Mock/Fake 与临时数据，未执行真实 txtai 写入或性能基准。

## 12. 已知限制与后续计划

- Chunk 与树节点验证均逐项执行，实际运行时的大文档验证成本仍需观测。
- 审批入库仍同步执行，前端为 `POST /documents/{document_id}/review` 设置 120 秒请求上限；超时回查与 `indexing` 轮询已实现，但没有阶段进度百分比。改为后台任务、进度 API 或可取消任务仍需独立设计和批准。
- failed 文档仍没有通用重试；ready 文档已可退回重新审核，pending_review、ready、rejected 和 failed 已可删除。
- SQLite 和 txtai 不是原子事务，补偿失败后需要人工处理。
- 没有待审核数量统计、批量审核或审核角色；目录页只支持单文档进入详情。
- 没有认证、审核角色、签名或不可抵赖审计。
