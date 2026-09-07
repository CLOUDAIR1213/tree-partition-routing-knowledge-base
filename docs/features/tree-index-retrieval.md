# 树状索引检索

> 文档状态：已实现  
> 最近核对：2026-09-04  
> 代码基线：工作树快照（本目录不是 Git 仓库）  
> 维护责任：待指定

## 1. 功能说明

系统在财务、人事和技术三个虚拟分区根下维护 `document -> section -> chunk` 三层 txtai 索引。聊天依次选择文档、章节和 Chunk，最终只以 SQLite 校验通过的 Chunk 正文回答和引用。旧 Flat 注册表及运行时 fallback 已删除。

## 2. 范围与非目标

| 类型 | 内容 |
| --- | --- |
| 包含 | 三层持久化索引；逐层 Beam Search；绑定 metadata 范围；Chunk 证据校验；审批、删除、重新审核、改分区和启动同步；九层级健康状态 |
| 不包含 | 跨分区树；父节点作为证据；LLM 节点摘要；每文档物理子索引；在线无停机迁移；真实模型性能基准 |

## 3. 用户流程与状态

1. 批准文档时先取得 `pending_review -> indexing` 条件声明。
2. 系统写入并验证最终分区的 Chunk、文档节点和章节节点；全部成功后才提交 `ready`。
3. 聊天先以文档和章节 Beam Top-K 选择检索分支，再用所选文档 ID 约束章节查询，最后用精确 `(document_id, normalize_section(section))` 对约束 Chunk 查询。父层不使用 Chunk 证据阈值过滤。
4. 受限查询把 txtai `similar` 候选数扩大到该层总量，再应用 metadata 条件和返回上限，避免无关高分候选挤占目标分支。
5. SQLite 再校验文档 `ready`、最终分区和精确章节范围；父节点文本不进入 Answer Prompt 或 Citation。
6. 任一父层没有候选时返回空证据，不回退 Flat。
7. 改分区、重新审核和删除清理所有相关层级；启动先验证九个层级都已加载，再同步修复 `ready` 文档并清除已知 Chunk 的跨分区残留。加载失败会报告具体分区、层级和异常类别，不会在同步阶段伪装为普通未就绪错误。

| 当前状态 | 操作或条件 | 下一状态 | 失败处理 |
| --- | --- | --- | --- |
| `pending_review` | 三层写入验证成功 | `ready` | 任一失败则补偿并进入 `failed` |
| `ready` | 改分区 | `reindexing -> ready` | 恢复原分区；恢复失败进入 `failed` |
| `ready` | 重新审核 | `reindexing -> pending_review` | 恢复原分区；恢复失败进入 `failed` |
| 稳定状态 | 删除 | `deleting -> 删除` | 清理失败保留 SQLite 与文件并进入 `failed` |
| 进程启动 | ready 数据同步和验证 | 服务可用 | 数据或索引不一致时启动失败 |

## 4. 前端实现

前端没有检索模式开关，也不展示树节点。聊天继续只展示 Chunk Citation；审核和管理页面沿用现有状态、错误码和操作。

| 路径或组件 | 职责 | 关键状态或行为 |
| --- | --- | --- |
| `frontend/src/pages/ChatPage.tsx` | 聊天入口 | 只消费最终 Chunk Citation |
| `frontend/src/pages/ReviewPage.tsx` | 审核与管理 | 三层同步对用户保持同一 HTTP 语义 |
| `frontend/src/api/generated.ts` | 生成契约 | 健康状态包含每分区三层字段 |

## 5. 后端实现

| 路径或服务 | 职责 | 上下游依赖 |
| --- | --- | --- |
| `app/services/hierarchical_index.py` | 每分区三层索引加载、锁、写删、验证、范围查询和健康 | txtai、Partition |
| `app/services/hierarchy_builder.py` | 派生稳定父节点和 Chunk 行；启动同步及跨分区清理 | SQLite、树索注册表 |
| `app/services/hierarchical_retriever.py` | 文档/章节 Beam、范围传递、父层诊断和三层分数融合 | 树索注册表、Retriever |
| `app/services/retriever.py` | Chunk 命中规范化、最低分过滤、SQLite 权威校验和叶子诊断 | `documents`、`chunk_candidates` |
| `app/services/review.py` | 审批三层写入、逐层验证和补偿 | SQLite、树索注册表 |
| `app/services/document_management.py` | 改分区、重审、删除的三层生命周期 | SQLite、文件、树索注册表 |
| `app/main.py` | 无条件加载树索并同步 ready 文档 | Settings、Database |

每个分区和层级使用独立 `RLock`。索引加载失败时，查询、删除和缺失验证都会抛出不可用错误，不能把未加载层误判为空索引。

## 6. 数据库与存储

| 存储类型 | 表、目录或索引 | 读/写 | 用途与一致性要求 |
| --- | --- | --- | --- |
| SQLite | `documents`、`chunk_candidates` | 读写 | 状态、最终分区和 Chunk 正文权威来源 |
| SQLite | `hierarchy_nodes` | 读写删 | 文档/章节节点元数据与校验和；不复制 Chunk |
| txtai | `data/indexes-hierarchical/<partition>/document/` | 读写删 | 文档导航节点 |
| txtai | `data/indexes-hierarchical/<partition>/section/` | 读写删 | 章节导航节点 |
| txtai | `data/indexes-hierarchical/<partition>/chunk/` | 读写删 | 唯一 Chunk 向量索引和回答证据入口 |

分区根为虚拟节点。文档节点 ID 为 `hdoc:<document_id>`，章节节点 ID 为 `hsec:<document_id>:<section_path_hash>`。SQLite 与 txtai 没有共同事务，业务服务通过状态声明、逐层验证和稳定 ID 补偿维护一致性。

## 7. API 接口

| 方法 | 路径 | 用途 | 请求模型 | 响应模型 | 主要错误码 |
| --- | --- | --- | --- | --- | --- |
| `POST` | `/api/v1/chat` | 三层检索与回答 | `ChatRequest` | `ChatResponse` | `INDEX_NOT_READY`、`PARTITION_ISOLATION_VIOLATION` |
| `POST` | `/api/v1/documents/{document_id}/review` | 审批写入三层 | `ReviewRequest` | `ReviewResponse` | `INDEX_WRITE_FAILED` |
| `POST` | `/api/v1/documents/{document_id}/partition` | 迁移三层分区 | `ChangeDocumentPartitionRequest` | `ChangeDocumentPartitionResponse` | `PARTITION_CHANGE_FAILED` |
| `POST` | `/api/v1/documents/{document_id}/reopen-review` | 清理三层并退回审核 | `ReopenDocumentReviewRequest` | `ReopenDocumentReviewResponse` | `REOPEN_REVIEW_FAILED` |
| `DELETE` | `/api/v1/documents/{document_id}` | 清理三层并删除文档 | 无 | `DeleteDocumentResponse` | `DOCUMENT_DELETE_FAILED` |
| `GET` | `/api/v1/health` | 九个分区/层级状态 | 无 | `HealthResponse` | `SERVICE_UNAVAILABLE` |

权威契约：`contracts/openapi.json`  
契约生成命令：`uv run --no-sync python -m scripts.export_openapi`

## 8. 文件路径与修改边界

| 文件或目录 | 职责 | 修改级别 | 修改要求 |
| --- | --- | --- | --- |
| `docs/features/tree-index-retrieval.md` | 当前树索行为 | `owned` | 行为、补偿和验证变化时同步 |
| `app/services/hierarchical_index.py`、`app/services/hierarchy_builder.py`、`app/services/hierarchical_retriever.py` | 树索核心 | `owned` | 保持三层隔离和父节点不作为证据 |
| `app/services/retriever.py`、`app/services/review.py`、`app/services/document_management.py` | 共享业务编排 | `shared` | 检查聊天、审核、管理和补偿消费者 |
| `app/main.py`、`app/api/health.py`、`app/models/schemas.py` | 启动与健康契约 | `shared` | 同步 OpenAPI 和前端类型 |
| `contracts/openapi.json`、`frontend/src/api/generated.ts` | 契约产物 | `generated` | 只通过生成命令更新 |
| `data/indexes-hierarchical/`、`data/metadata/` | 运行数据 | `runtime-data` | 普通验证不得写入 |
| `data/indexes/` | 已退役 Flat 运行数据 | `runtime-data` | 只读保留，须满足迁移、备份和人工确认后才能删除 |
| 真实 txtai 迁移、性能评测和 Flat 数据清理 | 运维操作 | `approval-required` | 需明确数据、停机、备份与回滚 |

## 9. 核心不变量与安全约束

- 每个分区必须加载 document、section、chunk 三层；任一层失败使健康降级。
- 每个子查询只能访问声明分区；章节绑定文档 ID，Chunk 绑定精确文档/章节对。
- Chunk 是唯一回答和引用来源，且必须通过 SQLite 的 `ready + confirmed_partition` 校验。
- `RETRIEVAL_MIN_SCORE` 只过滤最终 Chunk 证据；document 和 section 只按各自 Beam 宽度导航，避免不同层向量分数尺度造成召回阻断。
- 任一层未加载不能被当成空索引，删除不能在缺失验证能力时继续提交业务删除。
- 一份 ready 文档的节点和 Chunk 只能存在于最终分区。

## 10. 错误处理与恢复

| 场景 | 对外表现 | 内部处理 | 恢复方式 |
| --- | --- | --- | --- |
| 父层或 Chunk 层未加载 | 503 `INDEX_NOT_READY` | 不返回无依据回答 | 修复索引并重启 |
| 审批任一层失败 | 500 `INDEX_WRITE_FAILED` | 清理三层，文档 failed | 检查补偿后人工处理 |
| 改分区失败 | 500 `PARTITION_CHANGE_FAILED` | 恢复原分区三层 | 恢复失败时人工重建 |
| 重审/删除清理失败 | 对应 500 错误码 | 保留或标记业务记录 failed | 修复索引后重试 |
| 启动同步失败 | 应用启动失败 | 不提供不完整 tree-only 服务 | 修复 SQLite/索引一致性后重启 |

## 11. 测试与验证

| 层级 | 覆盖内容 | 文件或命令 |
| --- | --- | --- |
| 单元 | 三层契约、绑定 SQL、空范围、未加载层拒绝 | `tests/unit/test_hierarchical_index.py` |
| 集成 | 三层检索、无 Flat fallback、候选挤占 | `tests/integration/test_chat_api.py` |
| 实际服务（显式启用） | 真实 txtai 下的章节标题精确匹配与 Citation | `tests/integration/test_real_txtai_retrieval.py` |
| 集成 | 审批、改分区、重审、删除和健康 | `tests/integration/test_documents_api.py` |
| 迁移 | 路径保护、失败不切换、备份切换 | `tests/integration/test_tree_index_migration.py` |

2026-09-04：父节点改为仅按 Beam 导航，`RETRIEVAL_MIN_SCORE` 仅过滤 Chunk；三层日志记录候选数、最高分和阈值过滤数，不记录问题或正文。`tests/integration/test_real_txtai_retrieval.py` 默认跳过，只有操作者明确提供运行服务和业务文档预期章节时才执行；它不写入业务数据，但可能调用当前配置的 Answer 模型。本轮在操作者批准的运行服务上执行了一条财务章节标题精确匹配检查，获得预期 Citation。

## 12. 已知限制与后续计划

- 当前目录不是 Git 仓库，真实迁移或删除运行数据前仍需建立可恢复代码包。
- tree-only 代码与离线迁移工具已实现，但现有业务 SQLite 尚未由 Agent 执行真实迁移，旧 `data/indexes/` 仍只读保留。
- txtai metadata filter 仍需扩大候选到 `index.count()`；默认 FAISS 没有原生 allowed-ID 预过滤，大规模性能尚未验证。
- SQLite 与 txtai 无共同事务，进程中断和补偿失败仍需人工恢复。
- 父层与 Chunk 的分数尺度不能直接比较；生产阈值仍需以显式启用的真实 txtai 回归和获批质量评测持续校准。
