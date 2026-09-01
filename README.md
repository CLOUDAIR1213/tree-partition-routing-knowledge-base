# 三分区知识库

本地运行的企业知识库 MVP。后端使用 FastAPI、SQLAlchemy、SQLite 和 txtai；前端使用 React、TypeScript 和 Vite。当前可完整演示文档上传、解析、Chunk 预览、分区复核、批准入库和拒绝流程。

当前后端尚未实现 `/api/v1/chat` 和 `/api/v1/route`，因此问答页面已经完成交互界面，但真实问答需要等待后端 Phase 3/4。前端不会把缺少接口误判为问答成功。

## 快速启动

环境要求：

- Python 3.11 或 3.12
- [uv](https://docs.astral.sh/uv/)
- Node.js 20 或更高版本
- npm 10 或更高版本

首次安装后端依赖：

```powershell
uv sync --group dev
Copy-Item .env.example .env
```

终端一，启动后端：

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

终端二，启动前端：

```powershell
Set-Location frontend
npm install
npm run dev
```

启动后访问：

| 服务 | 地址 |
| --- | --- |
| 前端应用 | `http://127.0.0.1:5173` |
| Swagger API 文档 | `http://127.0.0.1:8000/docs` |
| OpenAPI JSON | `http://127.0.0.1:8000/openapi.json` |
| 后端健康检查 | `http://127.0.0.1:8000/api/v1/health` |

前端开发服务器默认把 `/api/*` 代理到 `http://127.0.0.1:8000`，组件中没有硬编码后端地址。

## 已实现流程

1. 从问答首页点击右上角“上传知识”。
2. 选择一个 PDF、DOCX、TXT 或 Markdown 文件，限制 25 MB。
3. 选择财务、人事或技术初始分区，可填写最长 200 字的标题。
4. 后端同步完成文件签名检查、正文解析和 Chunking，返回 `pending_review`。
5. 前端进入 `/knowledge/review/{document_id}`，每页读取 20 条 Chunk。
6. 审核人确认或修改唯一最终分区，并可填写最长 500 字的备注。
7. 批准后只写入最终分区索引；拒绝时不写入任何索引。

PDF 使用 `pypdf` 按页解析，DOCX 使用 `python-docx` 按 Heading 层级解析，TXT 和 Markdown 使用本地解析器。当前不支持 OCR、扫描 PDF、Excel、PPTX 或图片。

## 页面与接口

| 前端页面 | 后端接口 | 说明 |
| --- | --- | --- |
| `/` | `POST /api/v1/chat` | 页面已实现，后端接口尚未实现 |
| `/knowledge/upload` | `POST /api/v1/documents` | multipart 上传并同步解析，成功状态 201 |
| `/knowledge/review/:documentId` | `GET /api/v1/documents/{id}` | 刷新页面时重新读取文档状态 |
| `/knowledge/review/:documentId` | `GET /api/v1/documents/{id}/preview` | 使用 `limit=20&offset=n` 分页读取 Chunk |
| `/knowledge/review/:documentId` | `POST /api/v1/documents/{id}/review` | 批准或拒绝 |
| 未提供独立页面 | `GET /api/v1/documents` | 文档列表和状态筛选 |
| 应用联调 | `GET /api/v1/health` | SQLite、三个索引和 Router 状态 |

全部非 2xx 响应统一使用：

```json
{
  "code": "STABLE_ERROR_CODE",
  "message": "可展示的信息",
  "request_id": "req_xxx",
  "details": null
}
```

前端按 `code` 分支处理，`request_id` 用于定位后端日志，不通过中文错误文本判断业务状态。

## OpenAPI 契约同步

后端模型和接口变化后，在仓库根目录导出快照：

```powershell
uv run --no-sync python -m scripts.export_openapi
```

然后重新生成前端类型：

```powershell
Set-Location frontend
npm run api:types
npm run build
```

`contracts/openapi.json` 是前后端运行期契约来源，`frontend/src/api/generated.ts` 由 `openapi-typescript` 生成，不应手工编辑。

## 环境变量

后端变量位于根目录 `.env`，完整默认值见 [.env.example](.env.example)。常用变量：

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `APP_PORT` | `8000` | 后端端口 |
| `METADATA_DATABASE_URL` | `sqlite+aiosqlite:///./data/metadata/knowledge.db` | 元数据数据库 |
| `EMBEDDING_MODEL` | `Qwen/Qwen3-Embedding-0.6B` | txtai Embedding 模型 |
| `MAX_UPLOAD_SIZE_MB` | `25` | 后端上传限制 |
| `ALLOWED_FILE_TYPES` | `pdf,docx,txt,md` | 后端允许扩展名 |
| `CORS_ORIGINS` | `localhost:5173,127.0.0.1:5173` | 允许的前端来源 |

前端可在 `frontend/.env.local` 设置：

```dotenv
VITE_PROXY_TARGET=http://127.0.0.1:8000
VITE_API_BASE_URL=
```

- 本地开发建议保持 `VITE_API_BASE_URL` 为空，使用 Vite proxy。
- 前后端分别部署时，将 `VITE_API_BASE_URL` 设置为后端完整 Origin，并同步配置后端 `CORS_ORIGINS`。
- 修改 `.env.local` 后必须重启 Vite。

## 目录结构

```text
app/                  FastAPI 应用、数据库、模型和业务服务
contracts/            经过审查的 OpenAPI 快照
data/                 SQLite、原文件、暂存文件和三个独立索引
frontend/             React 前端、组件测试和 Playwright 测试
scripts/              OpenAPI 导出和演示索引脚本
tests/                后端单元与集成测试
```

## 代码健康检查

后端：

```powershell
uv run pytest
uv run --no-sync python -m scripts.export_openapi
```

前端：

```powershell
Set-Location frontend
npm run build
npm test
npm run api:check
npm run test:e2e
```

`npm run build` 同时执行严格 TypeScript 检查。Playwright 覆盖 1440×900、1024×768 和 390×844 三种视口。

## 演示数据

```powershell
uv run --no-sync python -m scripts.seed_demo_indexes
```

seed 脚本可重复执行，固定文档 ID 和 Chunk ID 通过 txtai `upsert` 更新，不会持续追加重复记录。

## 常见问题

### 前端显示无法连接后端

先打开 `http://127.0.0.1:8000/api/v1/health`。如果无法访问，确认 Uvicorn 正在仓库根目录运行；如果后端端口不是 8000，修改 `frontend/.env.local` 中的 `VITE_PROXY_TARGET` 并重启前端。

### 上传返回 `DUPLICATE_DOCUMENT`

后端使用文件内容校验重复，不是按文件名判断。前端会保留表单并提供已有文档的审核页入口。

### 第一次启动较慢

txtai 可能首次下载 `Qwen/Qwen3-Embedding-0.6B`。可以使用 `EMBEDDING_MODEL` 指向本机已经缓存的兼容模型。

### 问答返回接口不存在

这是当前实现边界，不是代理故障。后端健康响应中的 `router` 当前为 `not_configured`，并且 OpenAPI 尚无 `/api/v1/chat`。文档上传、审核和入库不受影响。

## 安全边界

当前没有登录、角色或真实审核权限，只适合本地演示。部署到共享环境前必须增加身份认证和审核授权。不要上传真实密钥、个人敏感数据或未脱敏的企业文件。
