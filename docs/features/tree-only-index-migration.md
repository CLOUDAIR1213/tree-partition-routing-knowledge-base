# Tree-only 索引迁移

> 文档状态：部分实现  
> 最近核对：2026-09-04  
> 代码基线：工作树快照（本目录不是 Git 仓库）  
> 维护责任：待指定

## 1. 功能说明

本计划把当前“树节点索引 + 旧 Flat Chunk 索引”的混合实现迁移为只由树索注册表管理的 `document -> section -> chunk` 三层检索。迁移完成后，聊天、审批、删除、改分区、重新审核、启动恢复和健康检查都不再依赖 `app/services/index_registry.py` 或 `data/indexes/<partition>/`。

目标状态中的 Chunk 仍是唯一回答证据，SQLite 仍是文档状态、最终分区和 Chunk 正文的权威来源。树的 document、section 和 chunk 三层分别持久化到同一树索根目录下的独立 txtai 索引；父节点只缩小候选范围，不进入 Answer Prompt 或 Citation。

tree-only 代码、离线迁移工具、隔离测试和生成契约已经实现；真实业务 SQLite 的离线构建、目录切换、观察期和旧 Flat 运行数据清理尚未执行。本文件同时记录已完成实现与剩余运维门槛，不授权普通验证删除现有运行期索引。

## 2. 范围与非目标

| 类型 | 内容 |
| --- | --- |
| 包含 | 树索注册表接管 Chunk 叶子；移除 Flat 检索和 fallback；审批及管理操作只同步树索；离线迁移既有 `ready` 文档；树索健康状态；旧配置和代码退役；验证成功后的 Flat 运行数据清理 |
| 不包含 | 修改聊天 HTTP 请求；节点成为回答证据；跨分区搜索；LLM 节点摘要；在线无停机迁移；每文档或每章节物理子索引；真实模型质量评测；未经确认的大规模模型下载或业务数据重建 |

目标树结构：

```text
virtual partition root
  -> document txtai index
       -> section txtai index, constrained by document_id
            -> chunk txtai index, constrained by exact document_id + section
                 -> SQLite ready + confirmed_partition validation
```

`chunk` 层移动到树索根目录并由树索注册表管理，不再调用旧 `IndexRegistry`。本阶段仍采用每分区、每层一个索引；若后续需要原生 allowed-ID 预过滤或物理子索引，必须另行评测和批准。

## 3. 用户流程与状态

实施分为六个阶段，禁止跳过迁移验证直接删除 Flat 数据。

1. 扩展 `HierarchicalIndexRegistry`，让其管理 document、section、chunk 三层索引，并为 Chunk 提供精确文档/章节范围查询、写入、删除和验证。
2. 将聊天、审批和文档管理服务切换到单一树索注册表；删除运行时 Flat fallback，但暂时保留旧 Flat 文件用于回滚。
3. 增加离线迁移脚本。服务停止后，从 SQLite 读取全部 `ready` 文档和 Chunk，在临时树索根构建三层索引并生成只读校验报告。
4. 校验每个 `ready` 文档的文档节点、章节节点、全部 Chunk ID、分区唯一性、数量和校验和；全部通过后原子切换树索目录。
5. 启动 tree-only 服务，执行健康检查和隔离的定向检索验证；观察期内旧 Flat 目录只读保留，不参与请求。
6. 在代码版本和旧索引备份可恢复、观察期无阻断问题后，由操作者显式删除旧 `data/indexes/`。Flat 代码、配置和测试兼容层已先行移除，运行时不再读取旧目录。

| 当前状态 | 操作或条件 | 下一状态 | 失败处理 |
| --- | --- | --- | --- |
| 现有混合实现 | tree-only 代码及隔离测试通过 | 待迁移 | 不读取或删除运行期索引 |
| 待迁移 | 停服并开始临时目录重建 | 迁移中 | 保留当前树索与 Flat 索引 |
| 迁移中 | 三层索引和分区唯一性全部验证成功 | 待切换 | 生成失败报告并删除临时构建目录 |
| 迁移中 | 任一文档、节点或 Chunk 验证失败 | 迁移失败 | 不切换目录，不删除 Flat 索引 |
| 待切换 | 树索目录切换并启动成功 | tree-only 观察期 | 启动失败时恢复旧目录和旧代码版本 |
| tree-only 观察期 | 健康、审批、检索和管理冒烟通过 | 可清理 Flat | 发现回归则回滚，不清理旧索引 |
| 可清理 Flat | 操作者确认备份和删除目标 | tree-only 完成 | 删除失败时停止并保留可诊断现场 |

## 4. 前端实现

没有新增用户可操作的检索模式。聊天页继续只展示最终 Chunk Citation，不展示树节点或分数。由于服务端不再允许 Flat/树模式切换，前端不增加检索模式控件。

健康响应结构如发生变化，前端生成类型和 API Client 必须同步；当前 UI 不展示健康详情，因此不新增页面。

| 路径或组件 | 职责 | 关键状态或行为 |
| --- | --- | --- |
| `frontend/src/pages/ChatPage.tsx` | 聊天入口 | 请求结构不变；只消费 Chunk Citation |
| `frontend/src/pages/ReviewPage.tsx` | 审批和管理入口 | 状态和操作不变；错误提示继续使用稳定错误码 |
| `frontend/src/api/client.ts` | API 适配 | 检查健康响应运行时读取，不引入 Flat 模式字段 |
| `frontend/src/api/generated.ts` | 生成类型 | Health Schema 变化后由 OpenAPI 重新生成 |

## 5. 后端实现

索引能力已收敛到一个树索注册表。`HierarchicalRetriever` 负责逐层搜索；普通 `Retriever` 保留为共享 Chunk 命中规范化与 SQLite 权威校验器，不持有 Flat 注册表。

| 路径或服务 | 职责 | 上下游依赖 |
| --- | --- | --- |
| `app/services/hierarchical_index.py` | 扩展为 document、section、chunk 三层注册表；统一加载、健康、写入、删除、验证和范围查询 | txtai、Partition、写锁 |
| `app/services/hierarchical_retriever.py` | 唯一检索入口；文档、章节、Chunk 逐层收窄和重排 | 树索注册表、SQLite 叶子校验 |
| `app/services/retriever.py` | 收敛为 Chunk 命中规范化和 SQLite 权威校验 | `ChunkCandidateTable`、`DocumentTable` |
| `app/services/hierarchy_builder.py` | 派生非叶节点；支持离线构建完整三层清单与校验数据 | SQLite、树索注册表 |
| `app/services/review.py` | 审批只写入并验证树索三层；任一层失败不得进入 `ready` | SQLite、树索注册表 |
| `app/services/document_management.py` | 删除、改分区和重审清理所有分区的三层条目 | SQLite、文件、树索注册表 |
| `app/main.py` | 无条件加载树索；启动拒绝缺失的必需层；移除检索模式分支 | Settings、Database、树索注册表 |
| `app/api/health.py` | 报告每个分区的 document/section/chunk 状态 | HealthResponse、树索注册表 |
| `app/services/index_registry.py` | 旧 Flat 注册表 | 已删除；运行时消费者为零 |
| `scripts/migrate_tree_only_indexes.py` | 离线重建、验证、报告和目录切换 | 已实现；必须在停服状态显式运行 |

迁移脚本必须具备以下保护：

- 使用显式源数据库和目标临时目录，拒绝把目标解析为现有 Flat 或当前活动树索目录。
- 默认只构建和验证，不删除旧目录；清理必须是独立、显式步骤。
- 只读取 SQLite 中 `ready` 且有 `confirmed_partition` 的文档。
- 对每份文档验证一个文档节点、全部规范化章节节点、全部 Chunk ID 和唯一分区归属。
- 输出不含正文、服务器绝对路径或密钥的结构化报告。
- 任何失败都不得修改文档状态或当前活动索引。

## 6. 数据库与存储

| 存储类型 | 表、目录或索引 | 读/写 | 用途与一致性要求 |
| --- | --- | --- | --- |
| SQLite | `documents` | 读写 | 文档状态和最终分区权威来源；迁移期间只读 |
| SQLite | `chunk_candidates` | 读写 | Chunk 正文、顺序、校验和和索引时间；迁移来源 |
| SQLite | `hierarchy_nodes` | 读写 | document/section 节点元数据；Chunk 不重复保存 |
| txtai | `data/indexes-hierarchical/<partition>/document/` | 读写删 | 文档级导航节点 |
| txtai | `data/indexes-hierarchical/<partition>/section/` | 读写删 | 章节级导航节点 |
| txtai | `data/indexes-hierarchical/<partition>/chunk/` | 读写删 | 已实现的唯一 Chunk 向量索引和回答证据入口 |
| txtai | `data/indexes/<partition>/` | 迁移期只读，最终删除 | 旧 Flat Chunk 索引；切换后不得再被代码加载 |
| 文件 | 临时树索构建目录 | 写/删 | 离线构建成功后切换；失败时可安全清理 |
| 文件 | 迁移报告 | 写 | 只记录计数、ID 校验结果、分区和错误类别，不记录正文 |

SQLite 与 txtai 仍没有共同事务。在线业务操作必须先声明文档状态，再完成三层索引写入和逐层验证，最后提交 SQLite；失败时按稳定 ID 清理三层条目。离线迁移不修改业务状态，通过新目录构建和切换隔离失败影响。

旧 `data/indexes/` 属于 `runtime-data`。只有在 tree-only 代码、迁移报告、启动健康和回滚备份全部确认后才能删除；文档编写、单元测试和普通验证不得触碰它。

## 7. API 接口

聊天和文档端点的请求、成功响应及主要业务错误码保持不变。健康响应计划把索引状态扩展为每分区的 document、section、chunk 三层状态；具体字段以实施时生成的 OpenAPI 为准。

| 方法 | 路径 | 用途 | 请求模型 | 响应模型 | 主要错误码 |
| --- | --- | --- | --- | --- | --- |
| `POST` | `/api/v1/chat` | tree-only 逐层检索与回答 | `ChatRequest` | `ChatResponse` | `INDEX_NOT_READY`、`PARTITION_ISOLATION_VIOLATION` |
| `POST` | `/api/v1/documents/{document_id}/review` | 写入并验证树索三层 | `ReviewRequest` | `ReviewResponse` | `INDEX_WRITE_FAILED` |
| `POST` | `/api/v1/documents/{document_id}/partition` | 迁移三层索引分区 | `ChangeDocumentPartitionRequest` | `ChangeDocumentPartitionResponse` | `PARTITION_CHANGE_FAILED` |
| `POST` | `/api/v1/documents/{document_id}/reopen-review` | 清理三层索引 | `ReopenDocumentReviewRequest` | `ReopenDocumentReviewResponse` | `REOPEN_REVIEW_FAILED` |
| `DELETE` | `/api/v1/documents/{document_id}` | 删除所有分区的三层索引及业务数据 | 无 | `DeleteDocumentResponse` | `DOCUMENT_DELETE_FAILED` |
| `GET` | `/api/v1/health` | 检查 SQLite 和九个树索分区/层级实例 | 无 | `HealthResponse` | `SERVICE_UNAVAILABLE` |

权威契约：`contracts/openapi.json`  
契约生成命令：`uv run --no-sync python -m scripts.export_openapi`

## 8. 文件路径与修改边界

| 文件或目录 | 职责 | 修改级别 | 修改要求 |
| --- | --- | --- | --- |
| `docs/features/tree-only-index-migration.md` | 本实施计划 | `owned` | 实施进度、决策和验证结果必须同步 |
| `docs/features/tree-index-retrieval.md` | 当前树索行为 | `shared` | 未完成前只在已知限制中链接本计划；完成后改为 tree-only 事实 |
| `docs/features/chat-and-routing.md` | 聊天检索行为 | `shared` | 移除 Flat 和 fallback 语义时同步更新 |
| `docs/features/document-review-indexing.md` | 审批写入行为 | `shared` | 同步三层写入、补偿和错误语义 |
| `docs/features/knowledge-library-browser.md` | 删除和管理行为 | `shared` | 同步所有分区/层级清理规则 |
| `docs/features/system-runtime.md` | 启动和健康 | `shared` | 同步树索强制加载和健康降级规则 |
| `docs/architecture/system-overview.md`、`docs/architecture/data-and-storage.md` | 共享架构与存储 | `shared` | 删除混合架构和 Flat 权威路径描述 |
| `docs/operations/local-development.md`、`.env.example` | 配置和启动 | `shared` | 删除 `RETRIEVAL_MODE`、`INDEX_ROOT` 及 fallback 指引 |
| `docs/testing/strategy.md` | 验证范围 | `shared` | 增加 tree-only、迁移、失败恢复和真实 txtai 缺口 |
| `app/services/hierarchical_index.py`、`hierarchical_retriever.py`、`hierarchy_builder.py` | 树索核心 | `owned` | 增加 Chunk 层并保持父节点不作为证据 |
| `app/services/index_registry.py` | 旧 Flat 索引 | `owned` | 已删除；不得重新引入运行时消费者 |
| `app/services/retriever.py`、`review.py`、`document_management.py` | 共享业务编排 | `shared` | 检查聊天、审批、管理、补偿和分区隔离 |
| `app/main.py`、`app/core/config.py`、`app/api/health.py` | 运行时装配 | `shared` | 检查启动、测试 fixture、健康契约和配置消费者 |
| `app/models/schemas.py` | Health 和共享 API 模型 | `shared` | 同步 OpenAPI、前端生成类型和 API Client |
| `scripts/migrate_tree_only_indexes.py` | 离线迁移工具 | `owned` | 已实现；默认不删除旧数据，输出安全报告 |
| `tests/unit/test_hierarchical_index.py` | 三层范围和 Registry 单元测试 | `owned` | 已实现；只使用内存记录器 |
| `tests/integration/test_tree_index_migration.py` | 离线迁移和切换测试 | `owned` | 已实现；只使用临时目录和 SQLite |
| `tests/integration/test_chat_api.py`、`test_documents_api.py`、`tests/conftest.py` | 端到端隔离测试 | `shared` | 删除 Fake Flat 依赖，覆盖三层树索生命周期 |
| `contracts/openapi.json`、`frontend/src/api/generated.ts` | 生成契约 | `generated` | 只能通过生成命令更新 |
| `data/indexes/`、`data/indexes-hierarchical/`、`data/metadata/` | 运行期索引和元数据 | `runtime-data` | 普通验证不得修改；正式迁移需停服、备份和报告 |
| 真实 txtai 性能评测、物理子索引、业务数据迁移执行 | 生产和数据操作 | `approval-required` | 明确数据范围、模型缓存、停机窗口和回滚责任后执行 |

## 9. 核心不变量与安全约束

- tree-only 完成后，应用代码不得导入、构造或调用旧 `IndexRegistry`，运行时不得读取 `data/indexes/`。
- 每个分区必须同时具备 document、section、chunk 三个已加载索引；任一必需层错误都使 health 为 degraded。
- Chat 的每个子查询只能访问声明分区的三层索引。
- section 查询必须绑定已选文档 ID；chunk 查询必须绑定精确 `(document_id, normalize_section(section))` 对。
- Chunk 是唯一回答和 Citation 来源；document/section 文本和 ID 不得进入 API 或 Answer Prompt。
- 只有 SQLite 中 `ready` 且 `confirmed_partition` 匹配的 Chunk 可以成为证据。
- 审批、改分区、重审和删除必须验证三层写入或清理结果；任一层失败不得宣告成功。
- 删除文档必须在 SQLite 级联删除前取得全部稳定节点和 Chunk ID，并清理所有分区，避免再次产生不可追踪的孤儿树节点。
- 迁移只读取已审核内容；报告不得包含 Chunk 正文、原文件路径、密钥或模型响应。
- Flat 运行数据只有在 tree-only 验收和可恢复备份确认后才能删除，且删除目标必须解析到本项目明确的 `data/indexes/`。

## 10. 错误处理与恢复

| 场景 | 对外表现 | 内部处理 | 恢复方式 |
| --- | --- | --- | --- |
| 任一树索层加载失败 | health 503 `SERVICE_UNAVAILABLE` | 标记具体分区和层级 error | 修复目录或模型配置后重启 |
| 聊天时树索不可用 | 503 `INDEX_NOT_READY` | 不使用 Flat fallback | 修复树索，不返回无依据回答 |
| 审批的任一层写入失败 | 500 `INDEX_WRITE_FAILED` | 清理本次 document/section/chunk 条目，文档 failed | 检查补偿报告后人工处理 |
| 改分区失败 | 500 `PARTITION_CHANGE_FAILED` | 恢复旧分区三层并清理目标分区 | 补偿成功保持原 ready，否则 failed |
| 重审或删除清理失败 | 对应 500 稳定错误码 | 保留 SQLite 文档并标记 failed | 修复索引后重试 |
| 离线迁移构建失败 | CLI 非零退出 | 保留活动树索和 Flat，不切换目录 | 修复错误后重新构建临时目录 |
| 离线校验发现缺失或跨分区项 | CLI 非零退出并生成安全报告 | 禁止切换和 Flat 清理 | 根据文档 ID/计数定位 SQLite 或索引问题 |
| tree-only 启动失败 | 服务不可用 | 树索加载错误在同步写入前报告具体分区、层级和异常类别；不删除旧 Flat 和旧树索备份 | 修复对应索引或模型问题后重启，必要时恢复旧代码版本与活动目录 |
| Flat 数据清理失败 | 运维操作失败 | 停止继续删除并记录确切目标 | 从备份恢复或人工完成清理 |

## 11. 测试与验证

| 层级 | 覆盖内容 | 文件或命令 |
| --- | --- | --- |
| 单元 | 三层 Registry、绑定参数、空范围短路、未加载层拒绝和健康状态 | `tests/unit/test_hierarchical_index.py` |
| 集成 | tree-only 单/双分区检索、SQLite 校验、无 Flat fallback | `tests/integration/test_chat_api.py` |
| 集成 | 审批、改分区、重审、删除的三层同步及逐层失败补偿 | `tests/integration/test_documents_api.py` |
| 迁移 | 临时目录重建、完整性报告、失败不切换、成功切换和备份 | `tests/integration/test_tree_index_migration.py` |
| 启动 | 任一分区/层级错误时 health degraded，全部加载时 ok | `tests/integration/test_documents_api.py` 或独立运行时测试 |
| 契约 | HealthResponse 与生成文件同步 | `uv run --no-sync python -m scripts.export_openapi`、`npm run api:check` |
| 代码健康 | Python 编译、定向 pytest、Ruff、前端类型和测试 | `uv run python -m compileall -q app tests`、`uv run pytest -q`、`uvx ruff check app scripts tests`、`npm run build`、`npm test` |
| 真实 txtai | 小规模三层写入、重启加载、范围检索、删除和延迟 | 需要用户批准模型与数据范围后执行 |

2026-09-04 已完成 tree-only 代码、迁移工具、Flat 注册表删除、OpenAPI 和前端类型生成。实际执行后端 70/70、Python compileall、Ruff、前端生产构建和 38/38 Vitest，全部通过；前端生成类型重复生成 SHA-256 一致。`npm run api:check` 最后的 `git diff` 因本目录不是 Git 仓库不可用。迁移测试使用临时 SQLite、临时目录和 Fake 树索；未读取或写入现有业务 SQLite，未修改运行期索引，未加载真实 Embedding 模型。

实施完成的最低验收清单：

- [x] 应用、测试、脚本和 `.env.example` 不再存在旧 Flat 注册表、`RETRIEVAL_MODE` 或 `INDEX_ROOT` 运行消费者。
- [x] 隔离测试覆盖 document、section、chunk 范围、候选挤占和无 Flat fallback。
- [x] 审批和管理操作统一验证三层，未加载层不能伪装为空索引。
- [x] health 对九个分区/层级实例逐项报告，任一错误返回 degraded。
- [x] 离线迁移工具在临时目录测试中完成构建、完整性报告、失败保护和备份切换。
- [ ] 使用真实业务 SQLite 和真实 txtai 模型在停服窗口生成通过报告并切换活动树索。
- [ ] tree-only 服务完成真实数据的只读检索与观察期验证。
- [ ] 旧 Flat 目录在备份和观察期确认后由操作者显式删除并记录恢复点。

## 12. 已知限制与后续计划

- tree-only 应用代码已经实施，旧 `IndexRegistry` 已删除；真实运行数据迁移、活动目录切换和 Flat 数据清理仍待运维执行。
- 当前目录不是 Git 仓库。正式删除代码或运行数据前必须建立可恢复的代码基线或交付包，不能只依赖当前工作目录回滚。
- txtai 9.13 默认 FAISS 没有原生 metadata allowed-ID 预过滤。三层 tree-only 能消除旧 Flat 代码和存储，但不自动解决大规模候选扩展的性能问题。
- 真实 txtai 的迁移时间、内存、召回率和删除成本尚未测量；未获批准前不得用业务数据或大型模型执行基准。
- 本阶段不建设每文档/每章节物理子索引。若 tree-only 的全量候选扩展无法满足延迟目标，需要单独设计物理子索引或迁移向量引擎。
- Flat 运行数据删除仍是最后一步；任何真实迁移或观察期验收失败都必须保留旧索引和树索备份。
