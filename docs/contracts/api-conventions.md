# API 契约与错误约定

> 最近核对：2026-09-03
> 代码基线：工作树快照（本目录不是 Git 仓库）

## 1. 契约来源

HTTP API 由 FastAPI 路由和 `app/models/schemas.py` 定义。`contracts/openapi.json` 是导出的审查快照，`frontend/src/api/generated.ts` 是从该快照生成的 TypeScript 类型。

```text
FastAPI routes + Pydantic schemas
  -> scripts/export_openapi.py
  -> contracts/openapi.json
  -> openapi-typescript
  -> frontend/src/api/generated.ts
  -> frontend/src/api/types.ts
  -> frontend/src/api/client.ts
```

`contracts/openapi.json` 和 `frontend/src/api/generated.ts` 都是 `generated`，禁止手工修改。

## 2. 通用约定

- 业务 API 前缀为 `/api/v1`。
- JSON 请求使用 snake_case 字段。
- 文档上传使用 multipart/form-data，浏览器负责生成 boundary。
- 时间字段使用带时区的 ISO 8601；SQLite 返回无时区值时 API 适配为 UTC。
- 请求模型默认 `extra="forbid"` 且去除字符串首尾空白。
- 所有响应头包含 `X-Request-ID`。
- 客户端提供的 Request ID 只有匹配 `[A-Za-z0-9_-]{1,100}` 时才会沿用。
- 分页统一使用 `limit` 和 `offset`，响应回显二者并返回 `total`。

## 3. 端点总表

| 方法 | 路径 | 功能 | 成功响应 |
| --- | --- | --- | --- |
| `POST` | `/api/v1/chat` | 路由、检索与回答 | `ChatResponse`，HTTP 200 |
| `POST` | `/api/v1/documents` | 上传、解析、Chunking | `UploadDocumentResponse`，HTTP 201 |
| `GET` | `/api/v1/documents` | 文档列表和状态筛选 | `DocumentListResponse` |
| `GET` | `/api/v1/documents/{document_id}` | 文档详情 | `DocumentDetailResponse` |
| `GET` | `/api/v1/documents/{document_id}/preview` | Chunk 分页预览 | `ChunkPreviewResponse` |
| `POST` | `/api/v1/documents/{document_id}/review` | 批准或拒绝 | `ReviewResponse` |
| `POST` | `/api/v1/documents/{document_id}/partition` | 调整已入库文档分区 | `ChangeDocumentPartitionResponse` |
| `POST` | `/api/v1/documents/{document_id}/reopen-review` | 退回重新审核 | `ReopenDocumentReviewResponse` |
| `DELETE` | `/api/v1/documents/{document_id}` | 删除文档的跨存储数据 | `DeleteDocumentResponse` |
| `GET` | `/api/v1/health` | 组件健康和模型配置状态 | `HealthResponse` 或 503 错误体 |

端点的业务流程和修改边界见对应[功能文档](../README.md)。完整字段、枚举和 required/nullability 以 `contracts/openapi.json` 为准。

## 4. 统一错误体

所有非 2xx 响应使用：

```json
{
  "code": "STABLE_ERROR_CODE",
  "message": "可安全展示的信息",
  "request_id": "req_xxx",
  "details": null
}
```

前端必须按 `code` 分支，不得解析中文 `message` 判断业务状态。`details` 只放安全、结构化的定位信息，不放堆栈、服务器路径、密钥或正文。

| 来源 | code 规则 |
| --- | --- |
| `AppError` | 使用服务层指定的稳定 code 和状态码 |
| Pydantic/FastAPI 校验 | `INVALID_PARTITION` 或 `VALIDATION_ERROR`，details 包含字段错误 |
| 路由不存在 | `NOT_FOUND` |
| 方法错误 | `METHOD_NOT_ALLOWED` |
| 未分类异常 | `INTERNAL_ERROR`，隐藏内部异常 |

聊天的 clarify、无证据和敏感阻断属于业务结果，使用 HTTP 200 和 `ChatResponse.code`，不是 `ErrorResponse`。

## 5. 聊天响应不变量

- `route=clarify` 时 `searched_partitions` 必须为空。
- `route=composite` 时必须有两个不同的 `searched_partitions`。
- 单分区 route 必须与唯一 searched partition 相同。
- 每条 Citation 都包含 partition，并且该 partition 必须已被检索。
- `answer_source=internal` 时必须只有内部 `citations`；`answer_source=web` 时必须只有 `web_citations`；`answer_source=none` 时两类引用都为空。
- `ChatRequest.allow_web_fallback` 默认关闭；`searched_partitions` 始终只表示实际访问的内部索引。
- `ChatResponse.timing.retrieval` 与 `searched_partitions` 一一对应，记录每个分区的索引查询加本地证据校验耗时；`router_llm_ms` 和 `answer_llm_ms` 只在对应模型实际调用时返回非空毫秒值。
- 后端 Pydantic 和前端 `assertChatContract` 都执行这些结构校验。

## 6. 前端 API Client

`frontend/src/api/client.ts` 提供统一 fetch：

- 默认超时 30 秒；聊天为 100 秒；上传、审核和文档管理操作为 120 秒。
- JSON body 自动设置 `Content-Type: application/json`。
- FormData 不设置 Content-Type。
- 非 2xx 转换为 `ApiError`；无法识别的错误体转换为 `INVALID_ERROR_RESPONSE`。
- AbortError 转换为 `ApiTimeoutError`。
- 不自动重试有副作用的 POST。
- 成功响应除聊天外主要依赖生成类型，当前没有完整运行时 Schema 校验。

## 7. 契约变更流程

1. 阅读受影响的功能文档，确认端点语义和文件边界。
2. 修改后端 Enum、Pydantic Schema、路由和服务生产者。
3. 更新后端定向测试，确保所有响应分支都满足新 Schema。
4. 从仓库根目录导出 OpenAPI：

   ```powershell
   uv run --no-sync python -m scripts.export_openapi
   ```

5. 在 `frontend` 生成类型并更新适配代码：

   ```powershell
   npm run api:types
   npm run build
   npm test
   ```

6. 运行 `npm run api:check` 或检查生成文件 diff。
7. 更新功能文档中的端点、模型名、错误语义和已知限制，不复制整个 Schema。

## 8. 当前契约状态

2026-09-04 从当前 FastAPI Schema 重新导出 `contracts/openapi.json` 并生成前端类型，共 10 个 HTTP operations。健康模型现按 finance/hr/tech 分区分别包含 document、section、chunk 状态。

## 9. 修改边界

| 路径 | 级别 | 规则 |
| --- | --- | --- |
| `app/models/enums.py`、`app/models/schemas.py` | `shared` | 检查全部 API 生产者、测试和前端消费者 |
| `app/api/` | `shared` | 按所属功能文档修改 |
| `contracts/openapi.json` | `generated` | 只由导出脚本更新 |
| `frontend/src/api/generated.ts` | `generated` | 只由 openapi-typescript 更新 |
| `frontend/src/api/types.ts`、`frontend/src/api/client.ts` | `shared` | 允许手工适配，但必须基于生成类型 |
| `.env`、`data/` | `runtime-data` | 与契约生成无关，不得修改 |
