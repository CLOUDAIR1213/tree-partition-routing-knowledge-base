# 系统运行时

> 文档状态：部分实现  
> 最近核对：2026-09-02  
> 代码基线：`61c551f` 加当前工作树快照  
> 维护责任：待指定

## 1. 功能说明

系统运行时负责 FastAPI 应用创建与关闭、配置加载、目录和数据库初始化、索引加载、可选 LLM Provider、CORS、Request ID、统一异常响应和健康检查。它为聊天和文档功能提供共享运行边界。

本地演示所需能力已实现；生产级认证、结构化业务日志、指标、追踪和迁移管理尚未实现，因此状态为“部分实现”。

## 2. 范围与非目标

| 类型 | 内容 |
| --- | --- |
| 包含 | 应用工厂；lifespan；Settings；目录创建；SQLite 初始化；中断索引恢复；索引加载；LLM 与可选 Search Provider 装配；CORS；Request ID；异常处理；健康检查 |
| 不包含 | 用户认证；授权；限流；生产 secrets manager；数据库迁移；分布式追踪；指标告警；模型主动探活；后台任务调度 |

## 3. 用户流程与状态

| 当前状态 | 操作或条件 | 下一状态 | 失败处理 |
| --- | --- | --- | --- |
| 进程启动 | 创建目录和 SQLite 表 | 初始化中 | 未捕获异常阻止应用启动 |
| 初始化中 | 恢复遗留 indexing、加载索引、构造 Provider | 服务中 | 索引加载错误记录为健康 error |
| 服务中 | 收到 HTTP 请求 | 请求处理中 | 分配或接受合法 Request ID |
| 请求处理中 | AppError/校验/HTTP/未知异常 | 统一 JSON 响应 | 响应头写入 X-Request-ID |
| 服务中 | GET health | ok 或 503 degraded | details 携带组件状态 |
| 服务中 | 进程关闭 | 已关闭 | 清空索引注册表并释放数据库连接 |

## 4. 前端实现

没有独立健康状态页面。`frontend/src/api/client.ts` 定义 `systemApi.health()`，但当前 UI 未调用；运行故障通过各页面的 API 错误提示体现。

| 路径或组件 | 职责 | 关键状态或行为 |
| --- | --- | --- |
| `frontend/src/api/client.ts` | 共享 fetch、超时和错误体 | 普通请求默认 30 秒，聊天 100 秒；非 2xx 转 ApiError；无法识别错误体时生成稳定 fallback |
| `frontend/src/components/layout/AppShell.tsx` | 应用布局生命周期 | 路由变化关闭移动侧栏；Escape 关闭侧栏 |
| `frontend/vite.config.ts` | 本地代理 | `/api` 默认代理到 `127.0.0.1:8000` |
| `frontend/src/vite-env.d.ts` | 前端环境变量类型 | `VITE_API_BASE_URL`、`VITE_PROXY_TARGET` |

## 5. 后端实现

| 路径或服务 | 职责 | 上下游依赖 |
| --- | --- | --- |
| `app/main.py` | 应用工厂、lifespan、中间件和异常处理 | Settings、Database、IndexRegistry、LLM Provider |
| `app/core/config.py` | 环境配置和派生状态 | pydantic-settings、`.env` |
| `app/core/request_id.py` | Request ID 生成和校验 | secrets、正则 |
| `app/core/errors.py` | 稳定应用错误 | API 异常处理器 |
| `app/api/dependencies.py` | 请求级依赖 | app.state |
| `app/api/health.py` | 组件状态 | SQLite、IndexRegistry、Settings |
| `app/db/session.py` | 数据库生命周期 | SQLAlchemy async engine |
| `app/services/index_registry.py` | 索引加载和健康 | txtai |
| `app/services/llm.py` | 可选 LLM Provider 构造 | Settings、httpx |
| `app/services/web_search.py` | 默认关闭的 Tavily Search Provider 构造 | Settings、httpx |

健康检查只主动执行 SQLite `SELECT 1`；索引状态表示实例是否成功加载；Router、Answer 和 Web Search 状态表示配置是否齐全，不代表外部端点实际可访问。

## 6. 数据库与存储

| 存储类型 | 表、目录或索引 | 读/写 | 用途与一致性要求 |
| --- | --- | --- | --- |
| SQLite | metadata database | 读写 | 初始化表、健康查询、恢复遗留 indexing |
| 文件目录 | data roots | 写目录 | 启动时确保目录存在，不写业务测试数据 |
| txtai | 三个分区目录 | 读/加载 | 加载失败使健康 degraded |
| 进程内存 | `app.state` | 读写 | Settings、Database、IndexRegistry、LLM Provider、Search Provider |
| 环境文件 | `.env` | 只读 | 本地配置和密钥；不得提交 |

## 7. API 接口

| 方法 | 路径 | 用途 | 请求模型 | 响应模型 | 主要错误码 |
| --- | --- | --- | --- | --- | --- |
| `GET` | `/api/v1/health` | 检查 SQLite、索引和模型配置状态 | 无 | `HealthResponse` | `SERVICE_UNAVAILABLE` |

健康 `status` 只由 SQLite 和三个索引决定。Router、Answer 或 Web Search 未配置不会让服务 degraded，因为手动路由、抽取式回答和纯内部检索仍可工作。`web_search` 分为 `disabled`、`not_configured` 和 `configured`。

权威契约：`contracts/openapi.json`  
契约生成命令：`uv run --no-sync python -m scripts.export_openapi`

## 8. 文件路径与修改边界

| 文件或目录 | 职责 | 修改级别 | 修改要求 |
| --- | --- | --- | --- |
| `app/main.py` | 应用共享入口 | `shared` | 检查所有 API、测试 fixture 和启动行为 |
| `app/core/config.py`、`.env.example` | 配置契约 | `shared` | 同步运行文档、健康状态和测试隔离 |
| `app/core/errors.py`、`app/core/request_id.py` | 错误与请求标识 | `shared` | 同步 API 契约和前端错误处理 |
| `app/api/dependencies.py` | 共享依赖 | `shared` | 检查所有路由装配 |
| `app/api/health.py` | 健康端点 | `owned` | 同步 HealthResponse 和集成测试 |
| `frontend/src/api/client.ts` | 共享 API Client | `shared` | 检查所有功能和前端测试 |
| `frontend/vite.config.ts` | 开发代理 | `shared` | 同步本地开发文档 |
| `contracts/openapi.json`、`frontend/src/api/generated.ts` | 生成契约 | `generated` | 禁止手工编辑 |
| `.env`、`data/` | 配置密钥和业务数据 | `runtime-data` | 不提交，不用于普通验证修改 |
| 认证、限流、指标和生产部署 | 生产能力 | `approval-required` | 需要部署与安全方案 |

## 9. 核心不变量与安全约束

- 无效或缺失的客户端 Request ID 必须由服务端替换。
- 所有响应包含 `X-Request-ID`；统一错误体包含同一 `request_id`。
- `.env` 密钥不得进入响应、日志、OpenAPI 或文档。
- 未分类异常不得向客户端返回堆栈或内部细节。
- CORS Origin 来自明确配置，不使用通配凭证组合。
- Provider 未配置时系统仍应支持手动分区和抽取式回答。
- Search Provider 默认关闭；启用但缺少 Key 时只报告 `not_configured`，不得阻止内部能力启动。
- 当前无认证，只允许可信本地演示环境。

## 10. 错误处理与恢复

| 场景 | 对外表现 | 内部处理 | 恢复方式 |
| --- | --- | --- | --- |
| AppError | 指定 HTTP 状态和稳定 code | details 可选 | 按功能错误恢复 |
| 请求模型校验失败 | 422 `VALIDATION_ERROR` 或 `INVALID_PARTITION` | 返回字段级 details | 修正请求 |
| 未知路由 | 404 `NOT_FOUND` | 统一 JSON | 修正 URL |
| 方法不允许 | 405 `METHOD_NOT_ALLOWED` | 统一 JSON | 修正方法 |
| 未分类异常 | 500 `INTERNAL_ERROR` | 隐藏内部异常 | 通过 Request ID 定位；当前缺少实际日志记录 |
| SQLite 或索引异常 | 503 `SERVICE_UNAVAILABLE` | health details 返回组件状态 | 修复组件并重启/重试 |
| 遗留 indexing | 文档改为 failed | 启动时标记恢复错误 | 人工检查索引状态 |

## 11. 测试与验证

| 层级 | 覆盖内容 | 文件或命令 |
| --- | --- | --- |
| 后端集成 | 健康响应、统一 404、Request ID | `tests/integration/test_documents_api.py` |
| 应用 fixture | 临时目录、SQLite、FakeIndexRegistry | `tests/conftest.py` |
| 契约 | HealthResponse 和错误模型 | `contracts/openapi.json` |
| 前端 API | 错误体和 request_id | `frontend/src/api/client.test.ts` |

2026-09-02：测试 fixture 已显式清空 LLM 和 Search 配置，不读取本机真实密钥；此前后端 32 个测试全部通过，本轮聊天定向测试 13/13 通过。OpenAPI 内存比较与生成快照一致。Router 与 Answer 已完成两条真实聊天兼容性冒烟；真实 Tavily 请求本轮返回不可用，尚未获得网页回答成功冒烟。健康状态仍只表示配置完整，不主动访问外部端点。

## 12. 已知限制与后续计划

- Router/Answer 健康状态只检查配置，不主动探测模型端点。
- 未分类异常处理器没有记录异常，Request ID 暂时无法关联实际后端日志。
- 项目依赖 structlog，但当前代码没有建立统一日志配置。
- 没有认证、限流、指标、Tracing、数据库迁移和生产部署清单。
- SQLite `create_all` 不能安全承担复杂 Schema 迁移。
