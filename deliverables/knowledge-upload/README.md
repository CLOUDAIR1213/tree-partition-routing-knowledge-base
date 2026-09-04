# 星澜仿真知识内容上传包

本目录包含 10 个可人工上传的业务文件和 4 个不上传的管理材料。业务资料全部使用虚构公司事实，供用户通过现有上传、审核和索引流程逐个入库。本次生成未调用上传或审核 API，未运行 seed，未修改 `data/raw`、`data/staging`、`data/indexes` 或 `data/metadata`。

## 文件结构

- `hr/`：4 个文件，包含公司基础资料、入转调离、考勤福利和人事补充通知。
- `finance/`：3 个文件，包含财务基础手册、差旅采购发票制度和财务补充通知。
- `tech/`：3 个文件，包含技术安全基础手册、权限发布故障规范和知识索引补充通知。
- `fact-matrix.md`：跨文件事实唯一来源、权威归属和禁止重复位置。
- `upload-manifest.md`：人工上传顺序、初始分区、章节和事实点。
- `acceptance-questions.md`：9 条自动单分区、6 条自动双分区、6 条手动指定分区和 1 条联网兜底自然语言验收问题。

## 静态验证记录

生成后使用项目现有 `StandardDocumentParser` 和 `SectionChunker(550, 100, 700, 75)` 做只读检查。DOCX 字符数为 Parser 规范化正文字符数，Markdown 字符数为 UTF-8 原文字符数。没有调用上传、审核、seed 或索引写入。

| 检查项 | 结果 |
| --- | --- |
| 上传业务文件 | 10 个：HR 4、Finance 3、Tech 3 |
| 管理材料 | 4 个：README、fact-matrix、upload-manifest、acceptance-questions |
| DOCX/Markdown 可读取 | 10/10 通过；DOCX 7 个、Markdown 3 个 |
| 章节与 Chunk 顺序 | 10/10 通过；每份 Chunk 序号从 0 连续，合计 71 个 Chunk |
| 实际字符数 | 合计 16,511；单文件数据已写入 `upload-manifest.md` |
| Section 数 | DOCX 每份 7；HR Markdown 7；Finance/Tech Markdown 8 |
| 事实矩阵对照 | 通过；固定公司事实、金额、期限、系统和版本已覆盖 |
| 敏感信息扫描 | 通过；未发现实际个人信息、凭据、私钥、内网 IP 或生产 URL |
| 运行数据目录未变化 | 通过；未写入或删除 `data/raw`、`data/staging`、`data/indexes`、`data/metadata` |

## 验证说明

本次使用一次性临时校验脚本仅读取交付文件，并在临时进程内调用 Parser/Chunker；脚本不属于交付包，完成后已删除。DOCX 结构审计也已通过；当前环境没有 LibreOffice/`soffice`，因此未完成 PNG 渲染视觉检查。

## 人工入库前提

先按 `upload-manifest.md` 顺序上传，每个文档在 `pending_review` 中检查标题、章节路径、Chunk 顺序和正文后再批准。全部文档完成单分区和双分区验收后，旧演示运行数据的备份、清理和索引重建仍需用户另行授权。
