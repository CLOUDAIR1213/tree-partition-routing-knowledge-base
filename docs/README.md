# 项目文档导航

> 文档状态：现行  
> 最近核对：2026-09-03
> 代码基线：`61c551f` 加当前工作树快照

本目录是开发者和编码 Agent 理解项目的首要入口。开始修改代码前，先按本页确定阅读范围，再检查对应代码；不要从归档规格或单个文件名猜测当前行为。

## 必读顺序

任何代码任务至少按以下顺序阅读：

1. 本页，确定任务对应的功能和共享文档。
2. [系统总览](architecture/system-overview.md)，理解边界和调用方向。
3. 对应的端到端功能文档。
4. 功能文档引用的数据、契约、运行或测试专题。
5. 最后检查实际代码、测试和 Git 工作树，确认文档没有漂移。

发现文档与代码不一致时，不要静默选择一方。先记录差异，以用户指定基线和实际代码、测试为准，并在同一任务中更新文档或说明为什么暂不更新。

## 按任务选择文档

| 任务 | 必读功能文档 | 同时阅读 |
| --- | --- | --- |
| 聊天、路由、检索、LLM、引用 | [聊天与分区路由](features/chat-and-routing.md) | [数据与存储](architecture/data-and-storage.md)、[API 契约](contracts/api-conventions.md)、[测试策略](testing/strategy.md) |
| 上传、格式校验、解析、Chunking | [文档接入](features/document-ingestion.md) | [数据与存储](architecture/data-and-storage.md)、[API 契约](contracts/api-conventions.md) |
| 预览、审核、批准、拒绝、索引写入 | [文档审核与索引](features/document-review-indexing.md) | [数据与存储](architecture/data-and-storage.md)、[测试策略](testing/strategy.md) |
| 知识库目录、文档详情、筛选、Chunk 顺序展示 | [知识库目录与文档详情](features/knowledge-library-browser.md) | [文档接入](features/document-ingestion.md)、[文档审核与索引](features/document-review-indexing.md)、[数据与存储](architecture/data-and-storage.md)、[API 契约](contracts/api-conventions.md) |
| 真实仿真知识内容、人工上传包、演示数据替换规划 | [真实仿真知识内容构建与人工入库](features/realistic-knowledge-content.md) | [文档接入](features/document-ingestion.md)、[文档审核与索引](features/document-review-indexing.md)、[数据与存储](architecture/data-and-storage.md)、[测试数据规范](testing/test-data.md) |
| 健康检查、错误响应、Request ID、应用启动 | [系统运行时](features/system-runtime.md) | [本地开发](operations/local-development.md)、[API 契约](contracts/api-conventions.md) |
| 数据库、文件目录、txtai 索引 | 受影响的全部功能文档 | [数据与存储](architecture/data-and-storage.md) |
| OpenAPI、前端生成类型、API Client | 受影响的全部功能文档 | [API 契约](contracts/api-conventions.md) |
| 测试、Fixture、代码健康检查 | 对应功能文档 | [测试策略](testing/strategy.md)、[测试数据规范](testing/test-data.md) |
| 启动、环境变量、联调 | [系统运行时](features/system-runtime.md) | [本地开发](operations/local-development.md) |

## 现行文档

### 架构

- [系统总览](architecture/system-overview.md)：技术栈、组件关系、端到端数据流和依赖方向。
- [数据与存储](architecture/data-and-storage.md)：SQLite、原文件、解析快照、三个 txtai 索引和状态机。

### 功能

- [聊天与分区路由](features/chat-and-routing.md)：手动路由、自动单/双分区路由、检索、回答和引用。
- [文档接入](features/document-ingestion.md)：上传、文件安全校验、解析和 Chunking。
- [文档审核与索引](features/document-review-indexing.md)：详情、预览、审核状态和索引写入补偿。
- [知识库目录与文档详情](features/knowledge-library-browser.md)：目录筛选、全状态详情、Chunk 原始顺序展示、审核入口和文档删除/分区管理。
- [真实仿真知识内容构建与人工入库](features/realistic-knowledge-content.md)：已生成、待用户上传的 10 文件人工上传包、固定公司事实、Luna 执行边界和验收规则。
- [系统运行时](features/system-runtime.md)：应用生命周期、健康检查、错误契约和请求标识。

### 共享专题

- [API 契约与错误约定](contracts/api-conventions.md)
- [本地开发与配置](operations/local-development.md)
- [测试策略与当前验证状态](testing/strategy.md)
- [聊天测试数据规范与交付清单](testing/test-data.md)

### 项目汇报

- [项目理解与汇报报告](project-report.md)：项目定位、逐界面与模块边界、复用接口、业务流程、存储底座、API 数据传递、运行方式与当前风险。

### 优化计划（尚未实施）

- [树状路由索引优化与实施方案](plans/tree-routing-index-optimization.md)：2026-09-07 代码审查基线、检索缺陷、诊断方案、树模型、逐层路由、迁移回滚、阶段任务与验收标准；不代表现有功能已完成树化。

## 事实来源

| 来源 | 用途 | 维护规则 |
| --- | --- | --- |
| 实际代码和测试 | 当前行为与约束 | 修改行为时同步更新对应功能文档 |
| `contracts/openapi.json` | 经导出的 HTTP 契约快照 | 从 FastAPI 生成，不手工修改 |
| `frontend/src/api/generated.ts` | 前端生成类型 | 从 OpenAPI 生成，不手工修改 |
| 本目录现行文档 | 功能地图、边界、维护规则 | 代码任务结束前检查是否需要同步 |
| `docs/archive/` | 历史决策和设计演进 | 只作背景，不代表当前实现 |

## 当前基线说明

2026-09-02 核对时，复合路由、本地会话管理和受限联网兜底相关代码、契约、前端和测试均位于未提交工作树中，因此功能文档使用“工作树快照”作为基线。OpenAPI 快照与当前 FastAPI Schema 一致；此前后端 32 个测试、Ruff、前端构建和 22 个前端测试通过，本轮低分过滤与搜索错误分类的定向测试 18/18 通过。真实模型已完成一条单分区和一条双分区只读冒烟；真实 Tavily 请求返回 HTTP 401，需更换有效 Tavily Key 后才能形成网页回答成功冒烟。现有 fixture 不能用于认定业务回答质量通过，详见[测试策略](testing/strategy.md)。

## 文档维护规则

- 一份功能文档描述一条端到端能力，不再建立彼此重复的前端、后端分册。
- 行为、状态、API、存储或文件边界发生变化时，必须同步更新对应功能文档。
- 功能文档固定使用 `write-feature-docs` Skill 的 12 个章节。
- API 字段只在 Schema 和 OpenAPI 中维护；功能文档记录端点、模型名和关键语义。
- 新计划先写入功能文档的“已知限制与后续计划”，未实现前不得写入已实现流程。
- 文件修改边界统一使用 `owned`、`shared`、`generated`、`runtime-data`、`approval-required`。
- 不在文档中记录真实密钥、用户数据、服务器绝对路径或模型隐藏推理。

## 历史归档

`archive/` 保存首轮 MVP 规格、前端规格和复合路由开发计划。归档文件不会随代码持续更新；需要追溯设计原因时再阅读。
