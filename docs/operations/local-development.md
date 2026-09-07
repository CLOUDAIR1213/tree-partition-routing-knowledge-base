# 本地开发与配置

> 最近核对：2026-09-04  
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
uv run uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload --reload-dir app
```

终端二启动前端：

```powershell
Set-Location frontend
npm run dev
```

| 服务 | 地址 |
| --- | --- |
| 树状版本前端 | `http://127.0.0.1:5174` |
| Swagger | `http://127.0.0.1:8001/docs` |
| 实时 OpenAPI | `http://127.0.0.1:8001/openapi.json` |
| 健康检查 | `http://127.0.0.1:8001/api/v1/health` |

Vite 默认启用前端热模块更新，并固定监听 `5174`；该端口已被占用时会立即失败，不会静默改用其他端口。保存 `frontend/src/` 下的前端代码通常会直接更新浏览器。后端通过 `--reload` 监控 `app/` 下的 Python 文件，保存后会自动重启工作进程。`.env`、依赖、启动参数、`data/` 下运行数据和 txtai 索引不会自动重载，修改后请手动停止并重新启动后端。

并行对比旧版时，旧版可继续使用后端 `8000` 与前端 `5173`；本树状版本使用后端 `8001` 与前端 `5174`。两个版本必须保有各自目录下的 SQLite、原文件和 txtai 索引，不得通过环境变量指向同一份持久化数据。

### 4.1 受信任内网演示

内网演示使用单端口服务：FastAPI 托管 `frontend/dist`，页面通过同源 `/api/v1/*` 访问 API。先停止占用本树状版本 `8001` 端口的本地开发后端，再在**以管理员身份运行的 PowerShell** 中执行：

```powershell
.\scripts\start_intranet.ps1 -AllowedSubnet "10.88.20.0/24"
```

脚本在构建时临时清空 `VITE_API_BASE_URL`，因此即使开发机的 `frontend/.env.local` 配置了直连 API，内网构建产物仍只访问当前服务的同源 `/api/v1/*`；构建失败会在创建防火墙规则或启动服务前停止。脚本还让 `APP_HOST` 和 `APP_PORT` 与实际监听的 `0.0.0.0:8001` 一致，并在退出时恢复本次进程原有的环境变量。旧版后端继续运行在 `8000` 不会冲突；只有同样占用 `8001` 的树状版本进程会阻止该脚本启动。

部署前先确认本机 IPv4 地址和前缀长度，并将命令中的网段替换为当前可信局域网的实际 CIDR：

```powershell
Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.AddressState -eq "Preferred" -and $_.IPAddress -notlike "127.*" } |
  Select-Object InterfaceAlias, IPAddress, PrefixLength
```

脚本会构建前端、启动 `0.0.0.0:8001`，并创建仅允许该私有网段访问的临时 Windows 防火墙规则；规则覆盖 Windows 的网络配置文件，但来源始终被限制到 `AllowedSubnet`。服务停止后规则自动移除。Windows 把企业局域网标记为“公用网络”不改变这条来源限制，也不代表服务被公开到互联网。客户端访问服务器的局域网 IPv4 地址与端口，例如 `http://<server-lan-ip>:8001`。

部署成功需同时满足：启动窗口显示 Uvicorn 正在监听、服务器本机 `GET /api/v1/health` 返回 `200`，以及另一台位于 `AllowedSubnet` 的设备能打开首页。管理员授权取消、端口仍被占用或只完成本机访问，均不视为完成受限内网部署；普通启动仅能证明连通性，不能证明来源访问受到限制。

这个模式没有登录、权限和限流。它只适用于受信任内网演示，不得配置端口转发、反向代理或公网 DNS 将其暴露到互联网。常规开发仍使用本节的双服务和热重载命令。

### 4.2 普通内网验证启动

仅在隔离的可信测试网中，且由操作者主动管理 Windows 防火墙时，可不使用管理员脚本直接启动：

```powershell
$env:SERVE_FRONTEND = "true"
$env:APP_ENV = "trusted_intranet"
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001
```

该方式不创建任何防火墙规则。如果防火墙被关闭，指定端口不会再受 Windows 来源限制，因此它只适合临时验证，不能作为常态内网部署方案。停止进程后环境变量和监听一并失效；恢复长期服务时应重新启用防火墙，并使用 `start_intranet.ps1` 或同等的指定 CIDR 入站规则。

## 5. 后端配置

完整默认值见 `.env.example`，校验和派生规则见 `app/core/config.py`。

`ALLOWED_FILE_TYPES` 和 `CORS_ORIGINS` 使用逗号分隔值，例如 `ALLOWED_FILE_TYPES=pdf,docx,txt,md`；不需要写成 JSON 数组。修改 `.env` 后必须手动重启后端。

| 配置组 | 变量 | 用途 |
| --- | --- | --- |
| 应用 | `APP_HOST`、`APP_PORT`、`CORS_ORIGINS` | HTTP 监听和跨域；默认后端端口为 `8001` |
| 内网页面 | `SERVE_FRONTEND`、`FRONTEND_DIST_DIR` | 开启 FastAPI 静态托管及构建产物目录；启动脚本临时设置前者 |
| 数据 | `DATA_ROOT`、`RAW_ROOT`、`STAGING_ROOT`、`HIERARCHICAL_INDEX_ROOT`、`METADATA_DATABASE_URL` | 持久化位置 |
| 上传 | `MAX_UPLOAD_SIZE_MB`、`ALLOWED_FILE_TYPES` | 服务端上传边界 |
| Chunk | `CHUNK_TARGET_TOKENS`、`CHUNK_MIN_TOKENS`、`CHUNK_MAX_TOKENS`、`CHUNK_OVERLAP_TOKENS` | 切分参数 |
| 检索 | `EMBEDDING_MODEL`、`RETRIEVAL_TOP_K`、`RETRIEVAL_MIN_SCORE`、`COMPOSITE_TOP_K_PER_PARTITION` | txtai、最低相关性过滤和召回预算 |
| 树状检索 | `HIERARCHICAL_DOCUMENT_BEAM_WIDTH`、`HIERARCHICAL_SECTION_BEAM_WIDTH`、`HIERARCHICAL_LEAF_CANDIDATE_LIMIT` | 父节点 Beam 与 Chunk 候选预算；tree-only 无模式开关 |
| LLM | `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` | OpenAI-compatible 传输和默认模型 |
| 专用模型 | `ROUTER_LLM_MODEL`、`ANSWER_LLM_MODEL` | 覆盖默认模型 |
| 路由 | `ROUTER_RETRY_COUNT`、`COMPOSITE_MAX_PARTITIONS` | 输出修复和分区上限；当前上限固定为 2 |
| 回答 | `ANSWER_MODE`、`LLM_TIMEOUT_SECONDS` | LLM/抽取模式和超时 |
| 联网兜底 | `WEB_SEARCH_ENABLED`、`WEB_SEARCH_PROVIDER`、`WEB_SEARCH_BASE_URL`、`WEB_SEARCH_API_KEY` | 默认关闭；当前 Provider 为 Tavily |
| 联网预算 | `WEB_SEARCH_TIMEOUT_SECONDS`、`WEB_SEARCH_MAX_RESULTS` | 单次搜索超时和最多结果数；结果数上限固定为 5 |

`LLM_BASE_URL` 填 API 根地址时服务端追加 `/chat/completions`；已包含该后缀时直接使用。不要把真实 Base URL、Key 或模型响应写入文档和测试 fixture。

`RETRIEVAL_MIN_SCORE` 默认 `0.5`，只用于过滤最终 Chunk 证据；document 和 section 父层始终按 Beam Top-K 导航，不使用该阈值。低于该值的 Chunk 不会作为内部证据，并且不会阻断已显式授权的联网兜底；设置为 `0` 可关闭叶子分数过滤。服务日志以 `tree_retrieval_layer` 记录每层候选数、最高分、阈值过滤数和 Chunk 的 SQLite 校验数，不记录问题或正文。该值依赖当前 Embedding 模型和知识数据，替换任一项后应使用小量只读问题重新校准。修改 `.env` 后需手动重启后端。

检索固定使用 `HIERARCHICAL_INDEX_ROOT/<partition>/{document,section,chunk}/`。章节查询绑定所选文档，Chunk 查询绑定精确文档/章节对；父层无候选时不回退旧 Flat。受限查询将 txtai `similar` 候选数扩大到索引总量，`HIERARCHICAL_LEAF_CANDIDATE_LIMIT` 只限制进入分数融合的叶子返回数。txtai 默认 FAISS 在大规模 IVF 索引上没有原生 metadata pre-filter，因此真实规模的性能仍需单独验证。

旧 Flat 数据迁移必须停服并使用显式临时目录和报告：`uv run --no-sync python -m scripts.migrate_tree_only_indexes --database <knowledge.db> --target <empty-sibling-dir> --report <report.json>`。默认只构建验证；切换还需 `--activate --backup-root <empty-sibling-backup>`，且三个树目录必须同父级。工具不删除 `data/indexes/`，真实执行前需建立代码与索引备份。

`WEB_SEARCH_TIMEOUT_SECONDS` 默认 `60`，允许范围为 `1–120` 秒。它只限制 Tavily 搜索请求；完整聊天仍受前端 100 秒请求超时限制。已有本地 `.env` 不会自动继承 `.env.example` 的新默认值，需将该项手动改为 `60` 后重启后端。

启用受限联网兜底时，在本地 `.env` 设置 `WEB_SEARCH_ENABLED=true` 和 `WEB_SEARCH_API_KEY`。`WEB_SEARCH_BASE_URL` 默认指向 Tavily Search API；Key 与 LLM Key 相互独立，不得提交。健康接口返回 `web_search=configured` 只表示配置齐全，不执行真实探活。

联网失败时后端日志会记录 `web_search_request_failed`、失败类别和 HTTP 状态码，不会记录 Key、搜索问题或 Provider 响应正文。页面会分别提示认证失败、额度/速率受限、HTTP 服务错误、超时、网络连接失败或无效响应；用此信息检查本地 Tavily 配置或账户状态。

## 6. 前端配置

`frontend/.env.local` 支持：

```dotenv
VITE_PROXY_TARGET=http://127.0.0.1:8001
VITE_API_BASE_URL=
VITE_DEV_PORT=5174
```

本地开发保持 `VITE_API_BASE_URL` 为空，使用 Vite `/api` proxy。`VITE_DEV_PORT` 默认 `5174`，为两个项目同时运行预留；除非明确需要其他端口，不要修改。内网单端口模式也必须保持 API Base URL 为空，以便构建页面向当前服务器同源请求 `/api/v1/*`；受限内网脚本会为此强制覆盖本次构建。前后端分别部署时才设置完整 API Origin，并同步后端 CORS。已有本地 `.env` 或 `frontend/.env.local` 若覆盖后端代理端口或 Vite 端口，需按本项目的 `8001`、`5174` 更新后重启相应服务。

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

### 内网设备无法打开页面

确认服务进程仍在运行，服务器与客户端位于预期局域网，并访问 `http://<server-lan-ip>:8001` 而不是 `127.0.0.1`。使用受限启动脚本时，确认 UAC 已授予管理员权限、网段与 `AllowedSubnet` 一致且脚本没有提示端口占用；当前网络即使显示为“公用”，受限入站规则仍可工作。使用普通启动时，先检查操作者配置的 Windows 防火墙策略；如网络切换，请停止服务后按新网段重新运行受限脚本；不要放宽为任意来源或配置公网端口转发。

## 10. 运行数据边界

以下路径只属于运行数据：`data/raw`、`data/staging`、`data/indexes-hierarchical`、`data/indexes`、`data/metadata`。普通开发验证使用 pytest 临时目录和 Fake，不直接写这些目录。`data/indexes` 是已退役 Flat 数据，满足迁移、备份和观察期门槛前不得删除；seed 只在用户明确要求准备演示数据时执行。
