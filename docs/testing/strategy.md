# 测试策略与当前验证状态

> 最近核对：2026-09-07
> 代码基线：`61c551f` 加当前工作树快照

## 1. 原则

- 代码健康验证覆盖编译、类型检查、定向单元测试、隔离集成测试和窄契约检查。
- 默认不运行完整 E2E、路由质量评估、真实模型 benchmark、批量 seed 或大型模型下载。
- `tests/integration/test_real_txtai_retrieval.py` 默认跳过；仅在操作者显式设置运行服务地址、查询、分区和预期章节后运行。它不写业务数据，但请求成功后可能调用当前配置的 Answer 模型。
- 测试不得写入现有 `data/raw`、`data/staging`、`data/indexes-hierarchical`、`data/indexes` 或 `data/metadata`。
- 外部 LLM 和 txtai 在业务集成测试中使用 Fake；文件和 SQLite 使用 pytest 临时目录。
- 测试结果必须区分通过、失败和未运行，不把未执行写成通过。

## 2. 测试层级

| 层级 | 文件 | 覆盖范围 |
| --- | --- | --- |
| 后端单元 | `tests/unit/test_input_safety.py` | 本地脱敏 |
| 后端单元 | `tests/unit/test_web_search.py` | 联网资格、公开 HTTPS URL 规范化和搜索失败分类 |
| 后端单元 | `tests/unit/test_routing.py` | 公司基础信息的人事路由 Prompt 与 HR JSON 示例 |
| 后端单元 | `tests/unit/test_parser_and_chunker.py` | PDF/DOCX/Markdown 解析、表格原始顺序和 Chunk 完整性 |
| 后端单元 | `tests/unit/test_hierarchical_index.py` | 三层参数化 metadata SQL、精确文档/章节对、未加载层拒绝和索引总量候选窗口 |
| 后端集成 | `tests/integration/test_chat_api.py` | 安全、手动/自动/复合路由、分数阈值、内部/网络引用白名单、联网触发边界和分区/模型计时 |
| 后端集成 | `tests/integration/test_documents_api.py` | 上传、质量报告、建议分区、完整预览、审核、补偿、健康和错误契约 |
| 后端集成 | `tests/integration/test_intranet_frontend.py` | 内网模式的 SPA 入口、前端路由回退、静态资源和 API JSON 404 隔离 |
| 实际服务（显式启用） | `tests/integration/test_real_txtai_retrieval.py` | 真实 txtai 的章节标题精确匹配必须产生目标 Citation |
| 后端 fixture | `tests/conftest.py` | 临时 SQLite、FakeTreeIndexRegistry、TestClient |
| 前端组件 | `frontend/src/App.test.tsx` | 页面路由、聊天、上传、审核超时状态回查、受限 Markdown、assistant 右上角计时，以及请求期间切换会话、新会话首问、跨会话并发、失败和重试归属 |
| 前端 API | `frontend/src/api/client.test.ts` | JSON、multipart、错误体和字段 |
| 前端组件 | `frontend/src/components/PartitionSelector.test.tsx` | 自动/手动分区映射 |
| 前端 E2E | `frontend/tests/e2e/responsive.spec.ts` | 三种视口；默认不运行 |
| 契约 | `contracts/openapi.json`、`frontend/src/api/generated.ts` | 后端 Schema 与前端类型同步 |

## 3. Fake 和隔离规则

`FakeTreeIndexRegistry` 同时记录 document、section、chunk 的 search/upsert/delete 调用和范围，按分区/层级保存测试行，并先应用范围再截断。`FakeLLMProvider` 返回测试内定义的结构化 JSON，不访问网络。所有上传、SQLite 和索引数据位于 pytest `tmp_path` 生命周期中。

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
| Review、三层树索注册表、文档状态 | documents 集成测试、树检索/生命周期定向测试、审核前端测试、启动恢复相关测试 |
| 审批索引耗时与前端超时恢复 | `test_documents_api.py` 检查安全阶段日志；`App.test.tsx` 检查 `indexing -> ready` 轮询、草稿保留和单次提交；前端 build |
| Schema、Enum、API 路由 | 受影响集成测试、OpenAPI 导出、前端生成类型、build/test |
| API Client 或共享 UI | `client.test.ts`、`App.test.tsx`、build |
| 回答 Markdown 展示 | `App.test.tsx`、build；验证标题、列表、粗体、行内代码、安全链接，以及原始 HTML 和图片跳过 |
| 聊天异步会话归属 | `App.test.tsx`、build；请求完成、失败与重试必须在原会话，覆盖新会话和跨会话并发 |
| 聊天性能观测 | `test_chat_api.py`、`client.test.ts`、`App.test.tsx`、会话存储测试、OpenAPI 导出与 build；检索与模型耗时必须分离，非法历史计时必须拒绝 |
| Router Prompt | `test_routing.py`；公司基础信息必须明确指向人事单分区，复合路由边界不得改变 |
| 内网单端口模式 | `test_intranet_frontend.py`、`npm --prefix frontend run build`；普通启动验证连通性，受限部署还需管理员启动后由另一台指定网段设备做只读访问验证 |
| 树 metadata 范围 | `tests/unit/test_hierarchical_index.py`、`test_chat_api.py`；验证范围透传、空范围短路、未加载层拒绝、无关高分候选不挤掉已选分支，以及章节对不发生交叉匹配 |
| 树父层召回 | `tests/integration/test_chat_api.py`；验证低分 document/section 仍可引导到达高分 Chunk，并记录三层安全诊断日志 |
| CSS/响应式 | 相关组件测试；只有用户要求时运行 Playwright 和截图检查 |

## 6. 验证结果

| 检查 | 结果 | 说明 |
| --- | --- | --- |
| 2026-09-07 审批超时恢复 | 后端 73 项通过、1 项跳过；前端 39/39；build、compileall、Ruff 通过 | Mock/Fake 下验证审批超时后自动回查、`indexing -> ready` 轮询、单次提交和安全阶段耗时日志；未写运行数据 |
| 2026-09-04 tree-only 实施 | 70/70 后端测试、编译和 Ruff 通过 | 三层参数化 SQL、生命周期、未加载层拒绝、迁移保护和候选挤占；只使用临时 SQLite/Fake |
| 后端 pytest | 48/48 通过 | LLM 和 Search 均使用 Fake；fixture 与本地 `.env` 隔离，包含内网 SPA 静态托管和公司基础信息人事路由 Prompt 测试 |
| 前端 Vitest | 38/38 通过 | 4 个测试文件通过，包含联网授权、公开网络来源展示、请求期间切换会话、新会话首问、跨会话并发、失败、重试、快速切换隔离、受限 Markdown、知识库管理和聊天计时展示 |
| 聊天定向集成 | 13/13 通过 | Fake Provider 下验证单分区、复合分区的检索/模型计时形状与非负值；未写持久业务数据 |
| 前端生产构建 | 通过 | TypeScript project build 和 Vite build 通过 |
| OpenAPI 内存比较 | 通过 | `create_app().openapi()` 与快照一致，共 7 个 operations |
| Ruff | 通过 | 使用 `uvx ruff check app scripts tests`，未修改项目依赖 |
| 浏览器冒烟 | 通过 | 内置浏览器 DOM 与控制台检查通过；完整 Playwright E2E 未运行 |
| 真实 LLM | 两条冒烟通过 | single 路由到 finance；composite 路由到 tech + finance；未做批量质量评估 |
| 真实 Web Search | 未通过 | 一次只读 Tavily 请求进入 Provider 后返回 HTTP 401；Fake Provider 路径通过 |
| 真实 txtai 章节标题回归 | 通过 | 操作者明确启用当前运行服务和财务文档预期章节后，获得目标 Citation；未写入业务数据 |
| seed/真实 txtai 写入 | 用户已执行 | 本轮 Agent 只读检查 16 份 ready 文档，未写持久业务数据 |
| 实际内网监听与远端访问 | 已完成普通启动验证 | 此前配置下局域网地址 health 与 SPA 路由均返回 `200`；用户确认远端验收完成。本轮未启用防火墙，不将其视为来源限制验证 |

真实模型第一次 Router 冒烟暴露模型把 `subqueries` 输出为字符串数组；Router Prompt 增加对象数组的严格 JSON 模板后，单分区和复合请求通过。完整请求实测超过原前端 30 秒默认超时，因此聊天请求单独调整为 100 秒。

## 7. 测试缺口

- 聊天知识数据、路由问题集和上传样本的数量与结构已经交付，但内容质量、预期证据和自动化接线尚未完成，详见[测试数据规范与交付清单](test-data.md)。
- HierarchicalIndexRegistry 已逐个验证三层 ID，但尚无针对真实 txtai 的大规模索引迁移和删除性能测试。
- 三层树索与 metadata 范围已有 Fake 生命周期、迁移和候选挤占回归覆盖；真实业务数据迁移尚未执行，txtai 默认 FAISS 的大规模 IVF 路径也没有原生 metadata pre-filter。
- 没有批量真实模型路由质量、回答质量和故障注入测试。
- Tavily Provider 尚未完成一条真实网页回答成功冒烟，也没有搜索质量、费用或限流验证；本轮一次真实请求返回 HTTP 401。
- `RETRIEVAL_MIN_SCORE=0.5` 的低分过滤已由 Fake Provider 集成测试覆盖，并在一次真实请求中确认无关 Docker Chunk 被过滤；“Python 装饰器是什么？”的真实 Tavily 请求返回 HTTP 401，默认阈值也仍需用更有代表性的知识数据校准。
- 当前知识 fixture 是占位文本，问题集存在章节引用失配，不能作为黄金数据。
- 没有索引写入进程崩溃和补偿失败恢复测试。
- 没有上传解析资源耗尽或恶意文档测试。
- 没有认证与权限测试，因为对应能力尚未实现。
- E2E 存在但本轮未验证复合引用和最新工作树视觉状态。
- 尚未在第二台局域网设备上完成带受限防火墙规则的端口访问验证；网络切换后应重新核对 CIDR 并完成该验证。

## 8. 修改边界

| 路径 | 级别 | 规则 |
| --- | --- | --- |
| `tests/` | `shared` | 按受影响功能修改，保持临时数据隔离 |
| `frontend/src/*.test.tsx`、`frontend/src/api/*.test.ts` | `shared` | 同步 UI/API 行为 |
| `frontend/tests/e2e/` | `shared` | 只有需要 E2E 时修改和运行 |
| `data/fixtures/` | `shared` | 源数据需审查，不等同运行数据 |
| `tests/fixtures/` | `shared` | 测试源文件需保持虚构、可复现，并由测试显式读取 |
| `data/raw/`、`data/staging/`、`data/indexes-hierarchical/`、`data/indexes/`、`data/metadata/` | `runtime-data` | 禁止普通测试写入 |
| 大规模质量集和真实模型 benchmark | `approval-required` | 需要用户明确范围、成本和数据边界 |
