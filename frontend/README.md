# 分区知识库前端

React、TypeScript 和 Vite 实现的三分区知识库界面。已接入后端文档上传、状态读取、Chunk 分页预览和审核接口。

## 启动

要求 Node.js 20+、npm 10+，并确保后端默认运行在 `http://127.0.0.1:8000`。

```powershell
npm install
npm run dev
```

访问 `http://127.0.0.1:5173`。开发服务器把 `/api/*` 代理到后端，配置位于 [vite.config.ts](vite.config.ts)。

如需修改后端地址，创建 `.env.local`：

```dotenv
VITE_PROXY_TARGET=http://127.0.0.1:8000
VITE_API_BASE_URL=
```

本地联调建议使用 proxy。只有前后端分别部署时才设置 `VITE_API_BASE_URL`，此时后端必须允许对应 CORS Origin。

## 页面

| 路径 | 功能 | 后端状态 |
| --- | --- | --- |
| `/` | 自动/手动分区问答界面 | `/api/v1/chat` 尚未实现 |
| `/knowledge/upload` | 文件预检、初始分区、multipart 上传 | 已接入 |
| `/knowledge/review/:documentId` | 文档状态、20 条分页预览、批准/拒绝 | 已接入 |
| `*` | 404 与返回首页入口 | 不依赖后端 |

上传支持 PDF、DOCX、TXT 和 MD，前端预检限制 25 MB。预检只用于用户体验，后端会重新校验文件签名、扩展名、大小和分区。

## 契约

前端 API 分层：

```text
src/api/generated.ts  OpenAPI 自动生成类型，不手工修改
src/api/types.ts      生成类型别名和前端方法参数
src/api/client.ts     fetch、超时、错误体和 API 方法
```

后端变更后先在仓库根目录执行：

```powershell
uv run --no-sync python -m scripts.export_openapi
```

再在 `frontend` 执行：

```powershell
npm run api:types
npm run build
```

`apiFetch` 的行为约束：

- JSON 自动设置 `Content-Type: application/json`。
- FormData 不设置 Content-Type，由浏览器生成 multipart boundary。
- 非 2xx 解析为带 `code`、`message`、`request_id` 的 `ApiError`。
- 上传和审核超时为 120 秒，不自动重试有副作用的请求。
- 不记录问题正文、回答正文、Chunk 正文或文件内容。

## 脚本

| 命令 | 用途 |
| --- | --- |
| `npm run dev` | 启动 Vite 开发服务器 |
| `npm run build` | 严格 TypeScript 检查并生成生产包 |
| `npm run preview` | 本地预览生产包 |
| `npm test` | 运行 Vitest 与 Testing Library |
| `npm run test:e2e` | 运行三视口 Playwright 测试 |
| `npm run api:types` | 从 `../contracts/openapi.json` 生成类型 |
| `npm run api:check` | 检查生成类型是否漂移 |

首次运行 Playwright 如缺少浏览器：

```powershell
npx playwright install chromium
```

测试截图和 trace 位于 `test-results/`，该目录不会提交到 Git。

## 状态与错误

- 上传表单在失败时保留文件、标题和分区。
- `DUPLICATE_DOCUMENT` 提供已有文档入口。
- 审核页面刷新后通过 URL 文档 ID 重新读取状态。
- 只有 `pending_review` 可以批准或拒绝。
- 批准必须提供唯一 `confirmed_partition`；拒绝固定提交 `null` 和原因。
- 完成入库后可以返回问答页，并带上最终分区 query 参数。

会话和问题只保存在 React 页面内存，不写入 localStorage。

## 目录

```text
src/api/             OpenAPI 类型和 API Client
src/components/      布局、分区、上传和 Chunk 组件
src/features/chat/   问答会话、消息列表和 Composer
src/pages/           问答、上传、审核和 404 页面
src/test/            Vitest 公共配置
tests/e2e/           Playwright 页面与响应式测试
```

完整双端启动、后端环境变量和故障排查见仓库根目录 [README.md](../README.md)。
