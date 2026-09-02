# 测试策略与当前验证状态

> 最近核对：2026-09-02  
> 代码基线：`61c551f` 加当前工作树快照

## 1. 原则

- 代码健康验证覆盖编译、类型检查、定向单元测试、隔离集成测试和窄契约检查。
- 默认不运行完整 E2E、路由质量评估、真实模型 benchmark、批量 seed 或大型模型下载。
- 测试不得写入现有 `data/raw`、`data/staging`、`data/indexes` 或 `data/metadata`。
- 外部 LLM 和 txtai 在业务集成测试中使用 Fake；文件和 SQLite 使用 pytest 临时目录。
- 测试结果必须区分通过、失败和未运行，不把未执行写成通过。

## 2. 测试层级

| 层级 | 文件 | 覆盖范围 |
| --- | --- | --- |
| 后端单元 | `tests/unit/test_input_safety.py` | 本地脱敏 |
| 后端单元 | `tests/unit/test_web_search.py` | 联网资格、公开 HTTPS URL 规范化和搜索失败分类 |
| 后端单元 | `tests/unit/test_parser_and_chunker.py` | PDF/DOCX/Markdown 解析和 Chunking |
| 后端集成 | `tests/integration/test_chat_api.py` | 安全、手动/自动/复合路由、分数阈值、内部/网络引用白名单和联网触发边界 |
| 后端集成 | `tests/integration/test_documents_api.py` | 上传、预览、审核、补偿、健康和错误契约 |
| 后端 fixture | `tests/conftest.py` | 临时 SQLite、FakeIndexRegistry、TestClient |
| 前端组件 | `frontend/src/App.test.tsx` | 页面路由、聊天、上传、审核，以及请求期间切换会话、新会话首问、跨会话并发、失败和重试归属 |
| 前端 API | `frontend/src/api/client.test.ts` | JSON、multipart、错误体和字段 |
| 前端组件 | `frontend/src/components/PartitionSelector.test.tsx` | 自动/手动分区映射 |
| 前端 E2E | `frontend/tests/e2e/responsive.spec.ts` | 三种视口；默认不运行 |
| 契约 | `contracts/openapi.json`、`frontend/src/api/generated.ts` | 后端 Schema 与前端类型同步 |

## 3. Fake 和隔离规则

`FakeIndexRegistry` 记录 search/upsert/delete 调用，并按分区保存测试行。`FakeLLMProvider` 返回测试内定义的结构化 JSON，不访问网络。所有上传、SQLite 和索引数据位于 pytest `tmp_path` 生命周期中。

Fake 应与生产接口保持语义一致。当前已知差异是 Fake `verify` 检查全部 Chunk，而生产 `IndexRegistry.verify` 只检查第一个 Chunk；这会掩盖部分索引写入问题，应在修复生产实现时补充针对真实 Registry 接口的定向测试。

## 4. 默认验证命令

后端：

```powershell
uv run pytest -q
```

前端：

```powershell
Set-Location frontend
npm run build
npm test
```

契约：

```powershell
uv run --no-sync python -m scripts.export_openapi
Set-Location frontend
npm run api:check
```

生成检查会改写生成文件，应在确认 API 变更属于当前任务后执行；只读审核可以使用内存 OpenAPI 比较。

## 5. 按功能选择测试

| 变更 | 最低检查 |
| --- | --- |
| ChatService、Router、Answer、Retriever | `test_chat_api.py`、输入安全测试、前端聊天测试、OpenAPI 检查 |
| Parser、Chunker、FileStorage、Ingestion | parser/chunker 单元测试、documents 集成测试、上传前端测试 |
| Review、IndexRegistry、文档状态 | documents 集成测试、审核前端测试、启动恢复相关测试 |
| Schema、Enum、API 路由 | 受影响集成测试、OpenAPI 导出、前端生成类型、build/test |
| API Client 或共享 UI | `client.test.ts`、`App.test.tsx`、build |
| 聊天异步会话归属 | `App.test.tsx`、build；请求完成、失败与重试必须在原会话，覆盖新会话和跨会话并发 |
| CSS/响应式 | 相关组件测试；只有用户要求时运行 Playwright 和截图检查 |

## 6. 2026-09-02 验证结果

| 检查 | 结果 | 说明 |
| --- | --- | --- |
| 后端 pytest | 32/32 通过 | LLM 和 Search 均使用 Fake；fixture 与本地 `.env` 隔离 |
| 前端 Vitest | 27/27 通过 | 4 个测试文件通过，包含联网授权、公开网络来源展示、请求期间切换会话、新会话首问、跨会话并发、失败、重试和快速切换隔离 |
| 前端生产构建 | 通过 | TypeScript project build 和 Vite build 通过 |
| OpenAPI 内存比较 | 通过 | `create_app().openapi()` 与快照一致，共 7 个 operations |
| Ruff | 通过 | 使用 `uvx ruff check app scripts tests`，未修改项目依赖 |
| 浏览器冒烟 | 通过 | 内置浏览器 DOM 与控制台检查通过；完整 Playwright E2E 未运行 |
| 真实 LLM | 两条冒烟通过 | single 路由到 finance；composite 路由到 tech + finance；未做批量质量评估 |
| 真实 Web Search | 未通过 | 一次只读 Tavily 请求进入 Provider 后返回 HTTP 401；Fake Provider 路径通过 |
| seed/真实 txtai 写入 | 用户已执行 | 本轮 Agent 只读检查 16 份 ready 文档，未写持久业务数据 |

真实模型第一次 Router 冒烟暴露模型把 `subqueries` 输出为字符串数组；Router Prompt 增加对象数组的严格 JSON 模板后，单分区和复合请求通过。完整请求实测超过原前端 30 秒默认超时，因此聊天请求单独调整为 100 秒。

## 7. 测试缺口

- 聊天知识数据、路由问题集和上传样本的数量与结构已经交付，但内容质量、预期证据和自动化接线尚未完成，详见[测试数据规范与交付清单](test-data.md)。
- 生产 IndexRegistry 全 Chunk 验证缺少测试。
- 没有批量真实模型路由质量、回答质量和故障注入测试。
- Tavily Provider 尚未完成一条真实网页回答成功冒烟，也没有搜索质量、费用或限流验证；本轮一次真实请求返回 HTTP 401。
- `RETRIEVAL_MIN_SCORE=0.5` 的低分过滤已由 Fake Provider 集成测试覆盖，并在一次真实请求中确认无关 Docker Chunk 被过滤；“Python 装饰器是什么？”的真实 Tavily 请求返回 HTTP 401，默认阈值也仍需用更有代表性的知识数据校准。
- 当前知识 fixture 是占位文本，问题集存在章节引用失配，不能作为黄金数据。
- 没有索引写入进程崩溃和补偿失败恢复测试。
- 没有上传解析资源耗尽或恶意文档测试。
- 没有认证与权限测试，因为对应能力尚未实现。
- E2E 存在但本轮未验证复合引用和最新工作树视觉状态。

## 8. 修改边界

| 路径 | 级别 | 规则 |
| --- | --- | --- |
| `tests/` | `shared` | 按受影响功能修改，保持临时数据隔离 |
| `frontend/src/*.test.tsx`、`frontend/src/api/*.test.ts` | `shared` | 同步 UI/API 行为 |
| `frontend/tests/e2e/` | `shared` | 只有需要 E2E 时修改和运行 |
| `data/fixtures/` | `shared` | 源数据需审查，不等同运行数据 |
| `tests/fixtures/` | `shared` | 测试源文件需保持虚构、可复现，并由测试显式读取 |
| `data/raw/`、`data/staging/`、`data/indexes/`、`data/metadata/` | `runtime-data` | 禁止普通测试写入 |
| 大规模质量集和真实模型 benchmark | `approval-required` | 需要用户明确范围、成本和数据边界 |
