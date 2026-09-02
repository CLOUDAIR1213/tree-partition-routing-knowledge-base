# 本地开发与配置

> 最近核对：2026-09-02  
> 适用环境：Windows PowerShell，本地单机开发

## 1. 开发前阅读

先阅读[文档导航](../README.md)和任务对应的功能文档。确认文件修改级别后再打开代码；行为、API、数据和状态变化需要在同一任务更新文档。

## 2. 环境要求

- Python 3.11 或 3.12
- uv
- Node.js 20+
- npm 10+
- 首次使用 txtai 模型时需要可用的模型缓存或网络

## 3. 安装

仓库根目录：

```powershell
uv sync --group dev
Copy-Item .env.example .env
```

前端：

```powershell
Set-Location frontend
npm install
```

`.env` 和 `frontend/.env.local` 是本地运行配置，不得提交。

## 4. 启动

终端一，在仓库根目录启动后端：

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app
```

终端二启动前端：

```powershell
Set-Location frontend
npm run dev
```

| 服务 | 地址 |
| --- | --- |
| 前端 | `http://127.0.0.1:5173` |
| Swagger | `http://127.0.0.1:8000/docs` |
| 实时 OpenAPI | `http://127.0.0.1:8000/openapi.json` |
| 健康检查 | `http://127.0.0.1:8000/api/v1/health` |

Vite 默认启用前端热模块更新；保存 `frontend/src/` 下的前端代码通常会直接更新浏览器。后端通过 `--reload` 监控 `app/` 下的 Python 文件，保存后会自动重启工作进程。`.env`、依赖、启动参数、`data/` 下运行数据和 txtai 索引不会自动重载，修改后请手动停止并重新启动后端。

## 5. 后端配置

完整默认值见 `.env.example`，校验和派生规则见 `app/core/config.py`。

| 配置组 | 变量 | 用途 |
| --- | --- | --- |
| 应用 | `APP_HOST`、`APP_PORT`、`CORS_ORIGINS` | HTTP 监听和跨域 |
| 数据 | `DATA_ROOT`、`RAW_ROOT`、`STAGING_ROOT`、`INDEX_ROOT`、`METADATA_DATABASE_URL` | 持久化位置 |
| 上传 | `MAX_UPLOAD_SIZE_MB`、`ALLOWED_FILE_TYPES` | 服务端上传边界 |
| Chunk | `CHUNK_TARGET_TOKENS`、`CHUNK_MIN_TOKENS`、`CHUNK_MAX_TOKENS`、`CHUNK_OVERLAP_TOKENS` | 切分参数 |
| 检索 | `EMBEDDING_MODEL`、`RETRIEVAL_TOP_K`、`RETRIEVAL_MIN_SCORE`、`COMPOSITE_TOP_K_PER_PARTITION` | txtai、最低相关性过滤和召回预算 |
| LLM | `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` | OpenAI-compatible 传输和默认模型 |
| 专用模型 | `ROUTER_LLM_MODEL`、`ANSWER_LLM_MODEL` | 覆盖默认模型 |
| 路由 | `ROUTER_RETRY_COUNT`、`COMPOSITE_MAX_PARTITIONS` | 输出修复和分区上限；当前上限固定为 2 |
| 回答 | `ANSWER_MODE`、`LLM_TIMEOUT_SECONDS` | LLM/抽取模式和超时 |
| 联网兜底 | `WEB_SEARCH_ENABLED`、`WEB_SEARCH_PROVIDER`、`WEB_SEARCH_BASE_URL`、`WEB_SEARCH_API_KEY` | 默认关闭；当前 Provider 为 Tavily |
| 联网预算 | `WEB_SEARCH_TIMEOUT_SECONDS`、`WEB_SEARCH_MAX_RESULTS` | 单次搜索超时和最多结果数；结果数上限固定为 5 |

`LLM_BASE_URL` 填 API 根地址时服务端追加 `/chat/completions`；已包含该后缀时直接使用。不要把真实 Base URL、Key 或模型响应写入文档和测试 fixture。

`RETRIEVAL_MIN_SCORE` 默认 `0.5`。低于该值的 txtai 召回不会作为内部证据，并且不会阻断已显式授权的联网兜底；设置为 `0` 可关闭分数过滤。该值依赖当前 Embedding 模型和知识数据，替换任一项后应使用小量只读问题重新校准。修改 `.env` 后需手动重启后端。

`WEB_SEARCH_TIMEOUT_SECONDS` 默认 `60`，允许范围为 `1–120` 秒。它只限制 Tavily 搜索请求；完整聊天仍受前端 100 秒请求超时限制。已有本地 `.env` 不会自动继承 `.env.example` 的新默认值，需将该项手动改为 `60` 后重启后端。

启用受限联网兜底时，在本地 `.env` 设置 `WEB_SEARCH_ENABLED=true` 和 `WEB_SEARCH_API_KEY`。`WEB_SEARCH_BASE_URL` 默认指向 Tavily Search API；Key 与 LLM Key 相互独立，不得提交。健康接口返回 `web_search=configured` 只表示配置齐全，不执行真实探活。

联网失败时后端日志会记录 `web_search_request_failed`、失败类别和 HTTP 状态码，不会记录 Key、搜索问题或 Provider 响应正文。页面会分别提示认证失败、额度/速率受限、HTTP 服务错误、超时、网络连接失败或无效响应；用此信息检查本地 Tavily 配置或账户状态。

## 6. 前端配置

`frontend/.env.local` 支持：

```dotenv
VITE_PROXY_TARGET=http://127.0.0.1:8000
VITE_API_BASE_URL=
```

本地开发保持 `VITE_API_BASE_URL` 为空，使用 Vite `/api` proxy。前后端分别部署时才设置完整 API Origin，并同步后端 CORS。修改环境变量后重启 Vite。

## 7. 日常开发循环

1. 从 `docs/README.md` 选择并阅读功能文档。
2. 检查 `git status`，保留不属于当前任务的改动。
3. 在功能文档 `owned` 范围内修改；触及 `shared` 时列出受影响消费者。
4. API 或 Schema 变化按[契约流程](../contracts/api-conventions.md)重新生成。
5. 运行符合[测试策略](../testing/strategy.md)的定向检查。
6. 更新功能文档状态、文件边界、错误和验证结果。
7. 检查 diff，确保没有业务数据、密钥或无关生成物。

## 8. 常用验证

后端小型测试：

```powershell
uv run pytest -q
```

前端类型、构建和单元测试：

```powershell
Set-Location frontend
npm run build
npm test
```

OpenAPI 内存或生成检查见[API 契约](../contracts/api-conventions.md)。Playwright、seed、真实模型评估和大型下载不是默认验证，只有用户明确要求时运行。

## 9. 常见问题

### 自动模式一直要求选择分区

检查 health 的 `router` 字段。`not_configured` 表示缺少 LLM transport 或 Router 模型；手动分区仍可使用。

### Answer 显示抽取式降级

检查 health 的 `answer`。`not_configured` 表示 LLM 模式缺少配置；`extractive` 表示配置明确选择抽取模式。健康状态不主动探测外部模型连通性。

### 测试中的 health 状态与预期不同

`Settings` 默认读取仓库 `.env`。测试 fixture 已显式覆盖为空的 LLM URL、Key 和模型字段，因此测试 health 固定为 `not_configured`，不会调用本机真实模型。新增测试 fixture 时必须保持同样隔离，不要删除或暴露本地密钥来规避测试问题。

### 上传超时

上传和解析是同步请求，前端等待上限 120 秒。超时后先通过详情或列表确认是否已经创建文档，不要直接重复写入业务数据。

### 第一次启动很慢

txtai 可能加载或下载 Embedding 模型。使用本地已缓存的兼容模型可以避免大型下载。

## 10. 运行数据边界

以下路径只属于运行数据：`data/raw`、`data/staging`、`data/indexes`、`data/metadata`。普通开发验证使用 pytest 临时目录和 Fake，不直接写这些目录。seed 只在用户明确要求准备演示数据时执行。
