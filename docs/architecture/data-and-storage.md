# 数据与存储

> 最近核对：2026-09-03
> 代码基线：`61c551f` 加当前工作树快照

## 1. 存储概览

系统同时使用 SQLite、文件系统和三个 txtai 索引。三者用途不同：SQLite 是业务元数据和可展示正文的权威来源，文件系统保存原文件与解析快照，txtai 保存分区检索索引。

| 存储 | 默认位置 | 权威内容 | 修改级别 |
| --- | --- | --- | --- |
| SQLite | `data/metadata/knowledge.db` | 文档状态、分区、Chunk 正文和审核信息 | `runtime-data` |
| 原文件 | `data/raw/<document_id>/document.<ext>` | 上传的原始字节 | `runtime-data` |
| 解析快照 | `data/staging/<document_id>/parse.json` | 解析 Section、Chunk ID、质量报告和内容建议调试快照 | `runtime-data` |
| 财务索引 | `data/indexes/finance/` | finance Embedding 索引 | `runtime-data` |
| 人事索引 | `data/indexes/hr/` | hr Embedding 索引 | `runtime-data` |
| 技术索引 | `data/indexes/tech/` | tech Embedding 索引 | `runtime-data` |
| 演示源数据 | `data/fixtures/*.jsonl` | 可审查的 seed 输入 | `shared` |
| 浏览器会话 | `localStorage: partitioned-kb.chat-session` | 当前浏览器的聊天历史快照及 assistant 回答计时 | `runtime-data` |

验证默认不得向 `data/raw`、`data/staging`、`data/indexes` 或 `data/metadata` 写入数据。测试使用 pytest 临时目录、临时 SQLite 和 FakeIndexRegistry。

## 2. SQLite 表

### `documents`

`DocumentTable` 保存一份文档的生命周期和审核结果。

| 字段组 | 字段 | 语义 |
| --- | --- | --- |
| 标识 | `id` | `doc_` 加 24 位十六进制随机值 |
| 文件 | `original_filename`、`stored_path`、`mime_type`、`size_bytes`、`checksum_sha256` | 原文件信息；API 不返回服务器路径和校验和 |
| 分区 | `selected_partition`、`confirmed_partition` | 上传初选和审核最终分区 |
| 状态 | `status`、`error_code`、`error_message` | 生命周期与失败原因 |
| 内容摘要 | `title`、`chunk_count` | 展示标题和 Chunk 数量 |
| 审核 | `reviewed_by`、`review_note`、`reviewed_at` | 审核记录 |
| 时间 | `created_at`、`updated_at` | UTC 时间 |

`checksum_sha256` 有普通索引，但没有数据库唯一约束。接入服务在应用层拒绝状态不是 `rejected` 或 `failed` 的相同内容。

### `chunk_candidates`

`ChunkCandidateTable` 保存审核预览、检索校验和回答证据。

| 字段组 | 字段 | 语义 |
| --- | --- | --- |
| 标识 | `id`、`document_id`、`chunk_index` | 稳定 Chunk ID 和文档内顺序 |
| 正文 | `text`、`embedding_text` | 展示/回答正文与送入 Embedding 的增强文本 |
| 定位 | `title`、`section_path`、`page_start`、`page_end` | 引用元数据 |
| 完整性 | `checksum_sha256`、`indexed_at` | Chunk 校验和及成功索引时间 |

表对 `(document_id, chunk_index)` 有唯一约束，`document_id` 外键启用级联删除。SQLite 连接启动时执行 `PRAGMA foreign_keys=ON`。

## 3. 文档状态机

```text
uploaded -> parsing -> pending_review
                         | approve
                         v
                      indexing -> ready
                         |
                         v
                       failed

pending_review -> rejected
ready -> reindexing -> ready (change partition)
ready -> reindexing -> pending_review (reopen review)
pending_review/ready/rejected/failed -> deleting -> removed
uploaded/parsing -> failed
startup finds indexing/reindexing/deleting -> failed(recovery required)
```

只有 `pending_review` 可以审核，只有 `ready` 且 `confirmed_partition` 与检索分区一致的 Chunk 可以进入回答证据。

## 4. 文件存储规则

- 文件名只保留最后一个路径段，移除控制字符并截断为 255 字符。
- 服务端根据允许扩展名和内容签名校验 PDF、DOCX、TXT、Markdown。
- TXT 和 Markdown 必须能以 UTF-8 BOM 兼容方式解码。
- 每份文档使用独立随机目录，目标路径必须仍位于配置根目录下。
- `parse.json` 含 Section 内容、Chunk ID、解析质量和内容建议；详情与预览 API 会读取其中已验证的质量报告，它本身仍不是外部文件契约。

## 5. txtai 分区索引

`IndexRegistry` 为 `finance`、`hr`、`tech` 各维护一个 `Embeddings` 实例和写锁。索引不共享查询，也不跨索引比较相似度。

写入行包含 Chunk ID、Embedding 文本、文档 ID、分区和引用元数据。检索命中后，Retriever 必须回到 SQLite 读取正文并校验状态和最终分区；索引中的元数据不能替代该校验。

## 6. 一致性与补偿

SQLite 与 txtai 没有共同事务。批准审核时先把文档原子声明为 `indexing`，再写入和保存索引。索引失败时尝试删除本次 Chunk ID，并把文档标记为 `failed`；补偿是否成功写入错误消息和 API details。

`IndexRegistry.verify` 逐个确认所有传入 Chunk ID，`verify_absent` 确认删除后不再存在。更改分区时先写入并验证新分区，再清理其他分区；失败时尝试恢复原分区。重新审核和删除会按 Chunk ID 清理三个分区，用于同时消除历史补偿失败留下的行。

## 7. 并发与幂等

- 审核通过 SQL 条件更新 `pending_review` 状态实现单次声明；并发审核只有一个请求成功。
- 删除和分区管理通过 SQL 条件更新进入 `deleting` 或 `reindexing`，与审核及其他管理请求互斥。
- seed 使用固定文档和 Chunk ID 配合 txtai upsert，可重复执行，但它会写持久业务存储，只能在用户明确要求时运行。
- 上传重复判断按内容校验和，不按文件名；`rejected` 和 `failed` 文档不阻止重新上传。
- 当前有单文档删除、改分区和重新审核端点；没有通用失败重试、重新解析或全库重建端点。

## 8. 数据安全

- API 不返回 `stored_path`、文档校验和或 `embedding_text`。
- Answer LLM 只接收安全处理后的问题和本次召回的公开证据字段。
- `.env`、原文件、解析快照、SQLite 和索引不得提交。
- 浏览器会话快照不得包含 API Key；清理站点数据、单条删除或清空历史会移除对应本地记录。
- 当前没有用户级数据权限；共享部署前必须增加认证、授权和审计。

## 9. 相关代码

| 路径 | 职责 | 修改级别 |
| --- | --- | --- |
| `app/db/tables.py` | ORM 表结构 | `shared` |
| `app/db/session.py` | 连接、初始化和启动恢复 | `shared` |
| `app/services/file_storage.py` | 原文件和解析快照 | `shared` |
| `app/services/index_registry.py` | 三分区索引 | `shared` |
| `app/services/ingestion.py` | 接入写入 | `owned`，归文档接入功能 |
| `app/services/review.py` | 审核和索引一致性 | `owned`，归审核功能 |
| `app/services/document_management.py` | 删除、分区迁移和重新审核一致性 | `owned`，归知识库管理功能 |
| `app/services/retriever.py` | 检索后的 SQLite 校验 | `owned`，归聊天功能 |
| `frontend/src/features/chat/chatSessionStorage.ts` | 版本化浏览器会话快照 | `owned`，归聊天功能 |
| `data/raw/`、`data/staging/`、`data/indexes/`、`data/metadata/` | 运行期数据 | `runtime-data` |
