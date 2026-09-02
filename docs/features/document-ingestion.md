# 文档接入

> 文档状态：已实现  
> 最近核对：2026-09-02  
> 代码基线：`61c551f` 加当前工作树快照  
> 维护责任：待指定

## 1. 功能说明

文档接入功能允许用户上传 PDF、DOCX、TXT 或 Markdown，选择初始知识分区和可选标题。后端校验文件、保存原文件、解析正文、生成稳定 Chunk，并把文档推进到 `pending_review`，等待人工确认最终分区。

该阶段不会写入正式 txtai 索引，避免未经审核的内容进入问答。

## 2. 范围与非目标

| 类型 | 内容 |
| --- | --- |
| 包含 | 单文件上传；前端预检；服务端扩展名和签名校验；重复内容检测；原文件保存；PDF/DOCX/TXT/Markdown 解析；Chunking；解析快照；待审核状态 |
| 不包含 | 批量上传；异步任务；OCR；扫描 PDF；Excel/PPTX/图片；病毒扫描；文档删除；自动入索引 |

## 3. 用户流程与状态

1. 用户从聊天页进入 `/knowledge/upload`。
2. 选择一个文件、初始分区和可选标题。
3. 前端检查扩展名、非空和 25 MB 限制，然后提交 multipart。
4. 后端重新读取并校验大小、扩展名、内容签名和 UTF-8 编码。
5. 后端按内容 SHA-256 检查未拒绝、未失败的重复文档。
6. 原文件保存后创建 `documents` 记录，状态从 `uploaded` 进入 `parsing`。
7. Parser 生成 Section，Chunker 生成稳定 Chunk ID 和 Embedding 文本。
8. Chunk 写入 SQLite，状态改为 `pending_review`，解析快照写入 staging。
9. 前端跳转到审核页面。

| 当前状态 | 操作或条件 | 下一状态 | 失败处理 |
| --- | --- | --- | --- |
| 未选择文件 | 选择合法文件和分区 | 可提交 | 非法文件显示字段错误 |
| 提交中 | 文件校验并保存 | `uploaded` | 返回稳定错误码，表单保留 |
| `uploaded` | 开始解析 | `parsing` | 异常进入 `failed` |
| `parsing` | Section 和 Chunk 成功写入 | `pending_review` | 解析或空正文进入 `failed` |
| `pending_review` | 接入完成 | 审核功能接管 | 前端跳转审核页 |

## 4. 前端实现

| 路径或组件 | 职责 | 关键状态或行为 |
| --- | --- | --- |
| `frontend/src/pages/UploadPage.tsx` | 表单编排 | 保存文件、标题、分区、提交状态和重复文档入口 |
| `frontend/src/components/UploadDropzone.tsx` | 文件选择和拖放 | 预检四种扩展名、非空和 25 MB；新文件替换旧文件 |
| `frontend/src/components/PartitionSelector.tsx` | 初始分区 | 上传模式不允许自动路由 |
| `frontend/src/api/client.ts` | multipart 上传 | 不手工设置 Content-Type；上传超时 120 秒 |
| `frontend/src/components/layout/TopBar.tsx` | 页面入口 | 聊天页显示白底、细边框的紧凑“上传知识”入口 |

前端校验只改善体验，服务端始终重复校验。前端限制目前硬编码为四种类型和 25 MB，后端允许通过环境变量调整，两端配置可能漂移。

## 5. 后端实现

| 路径或服务 | 职责 | 上下游依赖 |
| --- | --- | --- |
| `app/api/documents.py` | multipart 入口和响应 | Settings、AsyncSession、IngestionService |
| `app/services/ingestion.py` | 接入状态和事务编排 | FileStorage、Parser、Chunker、ORM |
| `app/services/file_storage.py` | 文件名清理、签名检查和保存 | raw/staging 目录 |
| `app/services/parser.py` | 按格式解析 Section | pypdf、python-docx、文本解析 |
| `app/services/chunker.py` | Token 近似切分和稳定 ID | Chunk 配置、SHA-256 |
| `app/db/tables.py` | 文档和 Chunk 持久化 | SQLite |

PDF 按页生成 Section；DOCX 按 Heading 层级并附加表格；Markdown 按标题层级且保留代码围栏；TXT 作为单 Section。Chunker 以中日韩字符、英文词和其他非空字符近似 Token，支持窗口重叠。

## 6. 数据库与存储

| 存储类型 | 表、目录或索引 | 读/写 | 用途与一致性要求 |
| --- | --- | --- | --- |
| SQLite | `documents` | 读写 | 重复检测、文件元数据和接入状态 |
| SQLite | `chunk_candidates` | 写 | 完整 Chunk、Embedding 文本和定位信息 |
| 文件 | `data/raw/<document_id>/` | 写 | 保存原文件 |
| 文件 | `data/staging/<document_id>/parse.json` | 写 | 保存 Section 和 Chunk ID 快照 |
| txtai | `data/indexes/*` | 无 | 接入阶段禁止写入 |

接入包含多次 SQLite commit 和文件系统写入，不是原子事务。解析失败会把文档标记为 `failed`，但当前不会自动删除已保存的 raw/staging 目录。

## 7. API 接口

| 方法 | 路径 | 用途 | 请求模型 | 响应模型 | 主要错误码 |
| --- | --- | --- | --- | --- | --- |
| `POST` | `/api/v1/documents` | 上传、解析并生成 Chunk | multipart body | `UploadDocumentResponse` | `DUPLICATE_DOCUMENT`、`UNSUPPORTED_FILE_TYPE`、`FILE_TOO_LARGE`、`EMPTY_DOCUMENT`、`DOCUMENT_PARSE_FAILED`、`INVALID_PARTITION` |

multipart 字段为 `file`、`partition` 和可选 `title`。成功返回 HTTP 201 和 `pending_review`。

权威契约：`contracts/openapi.json`  
契约生成命令：`uv run --no-sync python -m scripts.export_openapi`

## 8. 文件路径与修改边界

| 文件或目录 | 职责 | 修改级别 | 修改要求 |
| --- | --- | --- | --- |
| `frontend/src/pages/UploadPage.tsx` | 上传表单 | `owned` | 同步页面测试和错误映射 |
| `frontend/src/components/UploadDropzone.tsx` | 文件预检 | `owned` | 与后端限制保持一致 |
| `app/services/ingestion.py` | 接入编排 | `owned` | 保持未审核不入索引 |
| `app/services/file_storage.py` | 文件边界 | `owned` | 保持路径穿越和内容签名检查 |
| `app/services/parser.py` | 解析 | `owned` | 新格式需增加依赖、测试和安全限制 |
| `app/services/chunker.py` | Chunking | `owned` | 改算法时评估稳定 ID 和索引兼容性 |
| `app/api/documents.py` | 共享文档路由 | `shared` | 同时检查审核功能和 OpenAPI |
| `app/db/tables.py`、`app/models/schemas.py` | 数据和 API 模型 | `shared` | 检查审核、聊天和前端生成类型 |
| `app/core/config.py`、`.env.example` | 上传和 Chunk 配置 | `shared` | 同步前端提示和运行文档 |
| `frontend/src/api/generated.ts`、`contracts/openapi.json` | 生成契约 | `generated` | 禁止手工编辑 |
| `data/raw/`、`data/staging/`、`data/metadata/` | 运行数据 | `runtime-data` | 验证使用临时目录 |
| OCR、病毒扫描、对象存储 | 新基础设施 | `approval-required` | 需要资源和安全决策 |

## 9. 核心不变量与安全约束

- 前端预检不能替代服务端校验。
- 原始文件名不得控制服务器路径。
- 扩展名必须在允许列表中，且 PDF/DOCX 内容签名必须匹配。
- TXT 和 Markdown 只接受 UTF-8 兼容内容。
- `document_id` 由服务端随机生成，文件保存在其独立目录。
- 上传和解析完成后状态必须是 `pending_review`，不得直接 `ready`。
- API 不返回 `stored_path`、SHA-256 或 `embedding_text`。
- 当前没有认证和上传权限控制，不得在共享环境接收真实企业文件。

## 10. 错误处理与恢复

| 场景 | 对外表现 | 内部处理 | 恢复方式 |
| --- | --- | --- | --- |
| 文件类型或签名错误 | 415 `UNSUPPORTED_FILE_TYPE` | 不解析 | 用户重新选择文件 |
| 文件为空 | 422 `EMPTY_DOCUMENT` | 不解析 | 用户提供有正文文件 |
| 超出后端限制 | 413 `FILE_TOO_LARGE` | 不保存 | 压缩或调整明确配置 |
| 相同有效内容已存在 | 409 `DUPLICATE_DOCUMENT` | 返回已有文档 ID | 前端进入已有审核页 |
| 加密、损坏或非 UTF-8 | 422 `DOCUMENT_PARSE_FAILED` | 文档标记 failed | 修复文件后重新上传 |
| 无可解析正文 | 422 `EMPTY_DOCUMENT` | 文档标记 failed | OCR 或提供文本版 |
| 前端 120 秒超时 | 页面错误，保留表单 | 后端可能仍在处理 | 通过已有文档入口或列表确认，避免盲目重复 |

## 11. 测试与验证

| 层级 | 覆盖内容 | 文件或命令 |
| --- | --- | --- |
| 后端单元 | Markdown/DOCX/PDF 解析、稳定 Chunk、窗口边界 | `tests/unit/test_parser_and_chunker.py` |
| 后端集成 | 四种格式、签名不匹配、重复、路径穿越 | `tests/integration/test_documents_api.py` |
| 前端组件 | 非法文件、合法文件和分区后可提交 | `frontend/src/App.test.tsx` |
| 前端 API | multipart boundary 和字段 | `frontend/src/api/client.test.ts` |

2026-09-02：解析/Chunk 单元测试和文档接入相关集成测试通过；前端生产构建通过。没有向现有 `data/` 写入验证数据，也没有运行真实大文件或恶意压缩包测试。

## 12. 已知限制与后续计划

- 上传、解析和 Chunking 在一个同步 HTTP 请求中执行。
- 不支持 OCR、扫描 PDF、Excel、PPTX、图片和其他编码文本。
- 前端文件类型和 25 MB 限制是硬编码，与后端环境配置可能不一致。
- DOCX/PDF 没有独立的解压或解析资源预算，尚未针对压缩炸弹和复杂恶意文件加固。
- 失败文档的 raw/staging 文件不会自动清理。
- 没有文档删除、重新解析和后台任务状态 API。
