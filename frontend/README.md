# 前端子项目

React、TypeScript 和 Vite 前端。开始修改前先阅读仓库根目录的 [`docs/README.md`](../docs/README.md)，再按任务阅读：

- 聊天与引用：[`docs/features/chat-and-routing.md`](../docs/features/chat-and-routing.md)
- 文档上传：[`docs/features/document-ingestion.md`](../docs/features/document-ingestion.md)
- 文档审核：[`docs/features/document-review-indexing.md`](../docs/features/document-review-indexing.md)
- API Client 与生成类型：[`docs/contracts/api-conventions.md`](../docs/contracts/api-conventions.md)
- 本地代理和配置：[`docs/operations/local-development.md`](../docs/operations/local-development.md)

## 启动与验证

```powershell
npm install
npm run dev
npm run build
npm test
```

开发服务器默认把 `/api/*` 代理到 `http://127.0.0.1:8000`。本地覆盖使用未提交的 `.env.local`；详细规则见本地开发文档。

## 目录边界

| 路径 | 用途 | 修改级别 |
| --- | --- | --- |
| `src/pages/` | 路由页面 | 按对应功能为 `owned` |
| `src/features/chat/` | 聊天状态和展示 | `owned`，归聊天功能 |
| `src/components/` | 共享或功能组件 | 根据功能文档为 `owned`/`shared` |
| `src/api/client.ts`、`src/api/types.ts` | API 适配 | `shared` |
| `src/api/generated.ts` | OpenAPI 生成类型 | `generated`，禁止手工修改 |
| `src/styles.css` | 全局样式 | `shared` |
| `tests/e2e/` | Playwright | 默认不运行，按项目验证规则使用 |

后端契约变化时，先从仓库根目录更新 `contracts/openapi.json`，再执行 `npm run api:types`。完整顺序见 API 契约文档。
