# 三分区知识库前端实施规格

> 文档定位：独立前端页面和交互实施说明。  
> 关联后端规格：`txtai-partitioned-knowledge-base-mvp-spec.md`。  
> 参考界面：`C:\Users\wangf\AppData\Local\Temp\codex-clipboard-b85d1642-945a-4904-b819-e0c32a21b5df.png`。  
> 当前阶段：Round 1 / Frontend MVP。  
> 文档版本：v1.1。  
> 更新时间：2026-09-01。

参考截图只用于布局、信息密度和交互位置参考，不复制其品牌名称、Logo、文案或专有素材。

---

## 1. 前端目标

第一轮实现三个页面：

1. 知识库问答首页。
2. 上传知识库文档页面。
3. 文档解析结果与审核入库页面。

核心用户路径：

```text
问答首页
→ 点击右上角“上传知识”
→ 选择文件和知识分区
→ 上传并解析
→ 查看 Chunk 预览
→ 确认或修正分区
→ 批准入库或拒绝
→ 返回问答页进行检索验证
```

本轮不实现：

- 登录、注册和真实用户权限。
- 后台管理员角色系统。
- 多租户界面。
- 文档版本管理。
- 联网搜索开关。
- 多分区同时检索。
- 富文本编辑器。
- 拖动调整 Chunk 边界。
- 移动端原生应用。

---

## 2. 技术基线

推荐技术栈：

```text
React
TypeScript
Vite
react-router-dom
lucide-react
Vitest
React Testing Library
Playwright
openapi-typescript
```

约束：

- 使用当前稳定版本，并通过锁文件固定。
- 图标统一使用 `lucide-react`。
- 第一轮使用原生 `fetch` 封装 API Client，不引入复杂全局状态库。
- 组件局部状态使用 React state；跨页文档 ID 使用 URL 参数。
- 会话记录只保存在当前页面内存，不写 `localStorage`，避免持久化敏感问题。
- 后端 API 基础地址通过 `VITE_API_BASE_URL` 配置。
- 开发环境通过 Vite proxy 访问 FastAPI，避免在组件内写死服务地址。
- 使用固定的后端 `/openapi.json` 生成 TypeScript 契约，并在 CI 中检查类型是否漂移。

---

## 3. 页面路由

| 路径 | 页面 | 说明 |
| --- | --- | --- |
| `/` | `ChatPage` | 知识库问答首页 |
| `/knowledge/upload` | `UploadPage` | 选择文件和分区，提交解析 |
| `/knowledge/review/:documentId` | `ReviewPage` | 查看 Chunk 并审核入库 |
| `*` | `NotFoundPage` | 返回首页入口 |

路由要求：

- 问答页右上角按钮跳转到 `/knowledge/upload`。
- 上传成功后跳转到 `/knowledge/review/{document_id}`。
- 审核完成后保留结果页，提供“返回问答”按钮。
- 浏览器后退必须可用，不能只依靠内部状态切页。
- 页面刷新后根据 URL 重新读取文档状态，不能依赖上一页内存。

---

## 4. 整体布局

### 4.1 桌面端

参考截图采用左侧栏与主内容区结构：

```text
┌────────────────────────────────────────────────────┐
│ 左侧栏 220px │ 顶部操作栏                上传知识 │
│              ├─────────────────────────────────────┤
│ 品牌         │                                     │
│ 新建对话     │             主内容区                │
│ 最近会话     │                                     │
│              │                                     │
│ 当前用户     │                                     │
└────────────────────────────────────────────────────┘
```

尺寸建议：

- 左侧栏宽度：`220px`，固定轨道但不使用浏览器级 `position: fixed`。
- 顶部操作栏高度：`64px`。
- 主内容最大有效宽度：问答输入区 `700px`，上传与审核区 `960px`。
- 页面最小宽度：`320px`。
- 主内容区允许纵向滚动，不能产生整页横向滚动。

### 4.2 左侧栏

从上到下包含：

1. 产品品牌：数据库图标 + “分区知识库”。
2. “开启新对话”按钮。
3. “最近会话”标题。
4. 当前会话内产生的问题列表。
5. 底部演示用户区域。

第一轮会话列表只存在于当前前端内存：

- 提交问题后使用问题前 24 个字符作为标题。
- 刷新页面后允许清空。
- 不将问题写入浏览器持久化存储。
- 点击会话标题可以恢复当前页面内存中的消息。
- 不展示参考图中的无关示例内容。

### 4.3 顶部操作栏

问答首页右上角放置主入口：

```text
[上传图标] 上传知识
```

按钮规范：

- 使用 Lucide `Upload` 图标。
- 使用蓝色主按钮样式。
- 点击跳转 `/knowledge/upload`。
- 桌面端显示图标和文字。
- 小于 `420px` 时可以只显示图标，但必须保留 `aria-label="上传知识"`。
- 不使用右上角浮动圆形按钮，避免与截图标注区域混淆。
- 上传页和审核页将该位置替换为页面相关操作，不重复显示第二个上传入口。

### 4.4 移动端

小于 `720px`：

- 默认隐藏左侧栏。
- 顶栏左侧显示菜单图标，打开抽屉式会话导航。
- 问答区、上传区和审核区改为单列。
- 所有可点击目标有效尺寸不小于约 `44px`。
- 输入框字体不小于 `16px`，避免移动浏览器自动缩放。
- 长文件名和长章节标题必须换行或省略，不能挤出容器。

---

## 5. 视觉规范

### 5.1 风格

整体风格参考截图的安静、轻量工作界面：

- 白色或近白主背景。
- 浅灰左侧栏。
- 蓝色作为主要交互色。
- 绿色只用于成功状态。
- 红色只用于错误和拒绝操作。
- 内容以留白和细分隔线组织，不堆叠装饰卡片。
- 不使用渐变、装饰光斑、玻璃拟态或大面积插画。

### 5.2 圆角与边框

- 普通按钮：`6px` 或 `7px` 圆角。
- 输入框、Composer、上传区域：不超过 `8px`。
- 边框：`1px` 中性浅灰。
- 阴影只用于问答 Composer 和必要浮层，强度保持低。
- 不使用层层嵌套的卡片。

### 5.3 字体层级

- 页面主标题：`22px`，`font-weight: 500`。
- 区块标题：`15px` 或 `16px`，`font-weight: 500`。
- 正文和表单：`14px`；移动输入框 `16px`。
- 辅助文本：`12px`，必须保持可读对比度。
- 不根据视口宽度动态缩放字体。
- `letter-spacing: 0`。

### 5.4 图标

建议映射：

| 场景 | Lucide 图标 |
| --- | --- |
| 产品标识 | `Database` |
| 新建对话 | `CirclePlus` |
| 上传知识 | `Upload` |
| 自动路由 | `Route` |
| 财务 | `Landmark` |
| 人事 | `Users` |
| 技术 | `Code2` |
| 发送 | `ArrowUp` |
| 返回 | `ArrowLeft` |
| 文件选择 | `FileUp` |
| 待审核 | `Clock3` |
| 批准 | `Check` |
| 拒绝 | `X` |

图标按钮必须提供可见文字或 `aria-label`。不得绘制自定义 SVG 代替已有 Lucide 图标。

---

## 6. 问答首页

### 6.1 空会话状态

主内容在视觉上居中，包含：

1. 数据库或消息图标。
2. 标题“从企业知识开始提问”。
3. 分区模式选择。
4. 消息输入 Composer。

不添加营销介绍、功能说明卡片或示例功能墙。

### 6.2 分区模式选择

在标题下方使用分段选择控件：

```text
自动路由 | 财务 | 人事 | 技术
```

行为：

- 默认选择“自动路由”。
- 自动路由请求中 `partition_hint=null`。
- 选择财务、人事或技术时，将对应值传给 `partition_hint`。
- 一次只能选中一个模式。
- 当前选项必须同时使用边框、背景和文本变化，不能只靠颜色。
- 切换分区不清空输入内容。

### 6.3 消息 Composer

Composer 包含：

- 自适应高度文本框。
- 当前路由模式提示。
- 发送按钮。

交互规则：

- 空内容时发送按钮禁用。
- `Enter` 发送，`Shift+Enter` 换行。
- 请求过程中禁止重复提交并显示加载状态。
- 响应为 `clarify` 时展示后端提示，并提供三个分区快捷选项。
- 响应包含引用时，在答案下显示文档标题、章节和 Chunk ID。
- 后端返回安全阻断时展示明确错误，不自动重试。
- 不在浏览器控制台打印完整问题或回答正文。

### 6.4 有消息状态

发生第一次问答后，主区域切换为消息流：

```text
用户问题
助手回答
来源引用
...
底部 Composer
```

- 消息区域最大宽度与 Composer 对齐。
- 用户问题和助手回答通过对齐与轻微背景差异区分。
- 引用使用紧凑列表，不把每条引用做成大卡片。
- Composer 固定在消息内容末端的可见区域内，不遮挡最后一条消息。
- 页面加载和动态内容不得造成布局跳动。

---

## 7. 上传知识页面

### 7.1 页面入口

点击问答页右上角“上传知识”按钮进入：

```text
/knowledge/upload
```

页面顶部包含：

- 标题“上传知识库文档”。
- 简短状态文案：“解析完成后进入待审核区”。
- “返回问答”按钮。

### 7.2 桌面布局

内容采用两列布局：

```text
左侧：文件选择 + 文档标题
右侧：知识分区选择 + 提交操作
```

小于 `720px` 时改为单列，文件选择在前，分区和提交在后。

### 7.3 文件选择

上传区域支持：

- 点击选择文件。
- 拖放一个文件。
- 显示已选文件名、类型和可读大小。
- 支持 PDF、DOCX、TXT、Markdown。
- 前端提前校验扩展名和 25 MB 大小限制。
- 前端校验仅用于用户体验，最终以后端结果为准。

第一轮只允许单文件上传。选择第二个文件时替换第一个文件，不创建文件队列。

### 7.4 分区选择板块

必须显示三个单选项，默认不选中：

| 分区 | 显示名称 | 辅助说明 |
| --- | --- | --- |
| `finance` | 财务 | 报销、发票、预算、付款和会计处理 |
| `hr` | 人事 | 入职、合同、考勤、绩效和福利 |
| `tech` | 技术 | 研发、部署、数据库、运维和故障处理 |

每个分区选项使用原生 radio，整行标签可点击。禁止使用自由文本填写分区。

### 7.5 提交按钮

主操作：

```text
[上传图标] 上传并解析
```

启用条件：

- 已选择合法文件。
- 已选择一个分区。
- 当前没有上传请求。

提交时使用 `multipart/form-data`：

```text
file
partition
title（可选）
```

### 7.6 上传状态

| 状态 | 前端表现 |
| --- | --- |
| idle | 显示文件和分区选择 |
| validating | 本地校验，不显示虚假进度百分比 |
| uploading | 禁用表单，按钮显示“上传中” |
| parsing | 显示“正在解析文档” |
| pending_review | 跳转审核预览页 |
| failed | 保留用户选择并显示后端错误 |
| duplicate | 显示已存在文档 ID，允许前往查看 |

后端当前为同步解析，因此第一轮只显示不确定进度状态，不能伪造 `35%`、`80%` 等数值。

---

## 8. 审核预览页面

### 8.1 页面结构

```text
顶部：返回上传 / 文档标题 / 状态
文档信息：文件名、选择分区、Chunk 数量
Chunk 预览：分页列表
审核区：最终分区、备注、拒绝、批准入库
```

不把页面每个区块都包成卡片。文档信息和审核操作使用全宽区块与分隔线组织；Chunk 是重复项目，可以使用紧凑列表。

### 8.2 状态头部

状态显示：

| 后端状态 | 中文显示 |
| --- | --- |
| `uploaded` | 已上传 |
| `parsing` | 解析中 |
| `pending_review` | 待审核 |
| `indexing` | 入库中 |
| `ready` | 已入库 |
| `rejected` | 已拒绝 |
| `failed` | 处理失败 |

状态不能只依赖颜色，必须显示文字和对应图标。

### 8.3 Chunk 预览

每条 Chunk 显示：

- Chunk 顺序号。
- 章节路径。
- 页码范围。
- 前 300 个字符。
- 展开和收起按钮。

要求：

- 默认每页 20 条。
- 展开只影响当前 Chunk。
- 长文本保留换行，不能突破容器宽度。
- 不显示服务器文件绝对路径。
- 加载下一页时保留当前滚动位置。

### 8.4 最终分区确认

审核区再次显示财务、人事、技术三个单选项：

- 默认选择上传时的 `selected_partition`。
- 审核人可以修改。
- 页面同时展示“上传选择”和“最终确认”，避免改区无痕。
- 批准请求使用 `confirmed_partition`。

由于第一轮没有登录，页面不展示虚假的审核人身份；`reviewer_name` 可以不传或由开发配置提供演示值。

### 8.5 审核操作

两个操作：

- 次要危险操作：“拒绝”。
- 主要操作：“批准入库”。

规则：

- 只有 `pending_review` 状态显示可用审核按钮。
- 拒绝前显示确认对话框，要求填写简短原因。
- 批准前必须选择最终分区。
- 请求中禁用两个按钮，避免重复提交。
- `ready` 后显示“返回问答”按钮，可以自动把 `partition_hint` 设置为最终分区。
- 审核失败保留当前页和填写内容。

---

## 9. 组件设计

```text
AppShell
├── AppSidebar
├── TopBar
│   └── UploadKnowledgeButton
└── RouteOutlet
    ├── ChatPage
    │   ├── RouteModeSelector
    │   ├── MessageList
    │   └── ChatComposer
    ├── UploadPage
    │   ├── UploadDropzone
    │   ├── DocumentTitleField
    │   ├── PartitionSelector
    │   └── UploadActions
    └── ReviewPage
        ├── DocumentStatusHeader
        ├── DocumentSummary
        ├── ChunkPreviewList
        ├── PartitionSelector
        └── ReviewActions
```

### 9.1 `PartitionSelector`

统一用于：

- 问答页手动指定分区。
- 上传页选择初始分区。
- 审核页确认最终分区。

组件属性建议：

```ts
type Partition = "finance" | "hr" | "tech";

interface PartitionSelectorProps {
  value: Partition | null;
  onChange: (value: Partition) => void;
  includeAuto?: boolean;
  disabled?: boolean;
  layout: "segmented" | "list";
}
```

当 `includeAuto=true` 时，前端内部值为 `null`，API 序列化为 `partition_hint: null`。

### 9.2 `UploadDropzone`

负责：

- 原生文件 input。
- 拖放交互。
- 扩展名和文件大小预检。
- 文件名和大小展示。

不负责实际 API 请求，提交由 `UploadPage` 统一控制。

### 9.3 `ChunkPreviewList`

负责：

- 分页请求。
- 展开单条 Chunk。
- 空状态和加载状态。
- 页码、章节和预览文本展示。

不得在组件 mount 时一次请求全部 Chunk。

---

## 10. API 对接

### 10.1 契约来源和同步规则

设计期以两份规格中的同名字段为准；后端实现后，以 FastAPI `/openapi.json` 为运行期唯一事实来源。

前端应提供脚本：

```json
{
  "scripts": {
    "api:types": "openapi-typescript ../contracts/openapi.json -o src/api/generated.ts",
    "api:check": "npm run api:types && git diff --exit-code -- src/api/generated.ts"
  }
}
```

约束：

- 不在手写类型中重新发明字段名。
- `contracts/openapi.json` 由后端 `scripts/export_openapi.py` 生成，前端不得手工编辑。
- 后端字段、枚举、可空性或状态码变化时，前端类型必须在同一变更中更新。
- 时间字段保持 ISO 8601 字符串，在展示层格式化，不在 API Client 中转换为 `Date`。
- 可空字段使用 `null`，不要把 `null` 和缺失字段混为一谈。
- API JSON 保持 `snake_case`，第一轮不增加前端字段映射层。

前端预检必须与后端约束一致：

| 字段 | 前端限制 |
| --- | --- |
| `question` | trim 后 1～2000 个字符 |
| `title` | 可选，trim 后最多 200 个字符 |
| `reviewer_name` | 第一轮传 `null`；如启用演示值，不超过 100 个字符 |
| `note` | 可选，最多 500 个字符 |
| `limit` | 1～100，默认 20 |
| `offset` | 大于等于 0，默认 0 |

前端预检不能替代后端校验。

### 10.2 共享 TypeScript 类型

下面是前端消费时必须得到的类型形状。实际实现优先从 `generated.ts` 导出别名，例如 `components["schemas"]["ChatResponse"]`；不要再维护一份内容相同的手写接口。

```ts
export type Partition = "finance" | "hr" | "tech";
export type RouteName = Partition | "clarify";
export type DecisionSource = "user_hint" | "llm" | "safety_fallback";
export type SafetyAction = "safe" | "redacted" | "blocked";

export type DocumentStatus =
  | "uploaded"
  | "parsing"
  | "pending_review"
  | "indexing"
  | "ready"
  | "rejected"
  | "failed";

export interface ErrorResponse {
  code: string;
  message: string;
  request_id: string;
  details: Record<string, unknown> | null;
}

export interface UploadDocumentResponse {
  document_id: string;
  original_filename: string;
  selected_partition: Partition;
  confirmed_partition: Partition | null;
  status: DocumentStatus;
  chunk_count: number;
  warnings: string[];
  request_id: string;
}

export interface DocumentSummaryResponse {
  document_id: string;
  original_filename: string;
  title: string | null;
  selected_partition: Partition;
  confirmed_partition: Partition | null;
  status: DocumentStatus;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentDetailResponse extends DocumentSummaryResponse {
  mime_type: string;
  size_bytes: number;
  reviewed_at: string | null;
  review_note: string | null;
  error_code: string | null;
  error_message: string | null;
  request_id: string;
}

export interface DocumentListResponse {
  items: DocumentSummaryResponse[];
  total: number;
  limit: number;
  offset: number;
  request_id: string;
}

export interface ChunkPreviewItem {
  chunk_id: string;
  chunk_index: number;
  title: string | null;
  section_path: string | null;
  page_start: number | null;
  page_end: number | null;
  preview: string;
}

export interface ChunkPreviewResponse {
  document_id: string;
  title: string | null;
  selected_partition: Partition;
  confirmed_partition: Partition | null;
  status: DocumentStatus;
  chunk_count: number;
  items: ChunkPreviewItem[];
  total: number;
  limit: number;
  offset: number;
  request_id: string;
}

export interface ReviewRequest {
  action: "approve" | "reject";
  confirmed_partition: Partition | null;
  reviewer_name: string | null;
  note: string | null;
}

export interface ReviewResponse {
  document_id: string;
  selected_partition: Partition;
  confirmed_partition: Partition | null;
  status: DocumentStatus;
  indexed_chunk_count: number;
  reviewed_at: string;
  review_note: string | null;
  request_id: string;
}

export interface RouteRequest {
  question: string;
  partition_hint: Partition | null;
}

export interface RouteResponse {
  code:
    | "OK"
    | "ROUTE_CLARIFICATION_REQUIRED"
    | "ROUTER_INVALID_OUTPUT"
    | "SENSITIVE_INPUT_BLOCKED";
  route: RouteName;
  alternative_route: Partition | null;
  rewritten_query: string;
  needs_clarification: boolean;
  decision_source: DecisionSource;
  safety_action: SafetyAction;
  reason_code: string;
  request_id: string;
}

export interface ChatRequest {
  question: string;
  partition_hint: Partition | null;
}

export interface Citation {
  chunk_id: string;
  document_id: string;
  title: string;
  section: string | null;
  page_start: number | null;
  page_end: number | null;
}

export interface ChatResponse {
  code:
    | "OK"
    | "ROUTE_CLARIFICATION_REQUIRED"
    | "NO_INTERNAL_EVIDENCE"
    | "SENSITIVE_INPUT_BLOCKED";
  answer: string;
  route: RouteName;
  decision_source: DecisionSource;
  answerable: boolean;
  citations: Citation[];
  suggested_partitions: Partition[];
  request_id: string;
  warning: string | null;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  metadata_database: "ok" | "error";
  indexes: {
    finance: "ready" | "error";
    hr: "ready" | "error";
    tech: "ready" | "error";
  };
  router: "configured" | "not_configured";
  request_id: string;
}
```

### 10.3 API Client 行为

API Client 必须：

- 统一拼接 `VITE_API_BASE_URL`。
- 自动设置 JSON 请求的 `Content-Type: application/json`。
- 上传 `FormData` 时不手动设置 `Content-Type`，由浏览器生成 multipart boundary。
- 对所有非 2xx 响应解析 `ErrorResponse` 并抛出类型化 `ApiError`。
- 保留后端 `code` 和 `request_id`，不能通过中文文本判断错误类型。
- 对 HTTP 200 的业务 `code` 继续分支处理，不能把所有 200 当成可回答成功。
- 超时后允许用户主动重试，不自动重复上传或审核操作。
- 不在日志中输出完整问题、回答正文、Chunk 正文或文件内容。

```ts
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: ErrorResponse,
  ) {
    super(body.message);
  }
}
```

### 10.4 页面与接口映射

| 页面操作 | 后端接口 | 成功 HTTP | 响应类型 |
| --- | --- | ---: | --- |
| 自动或指定分区问答 | `POST /api/v1/chat` | 200 | `ChatResponse` |
| 调试路由 | `POST /api/v1/route` | 200 | `RouteResponse` |
| 上传并解析 | `POST /api/v1/documents` | 201 | `UploadDocumentResponse` |
| 查询文档列表 | `GET /api/v1/documents` | 200 | `DocumentListResponse` |
| 读取文档状态 | `GET /api/v1/documents/{document_id}` | 200 | `DocumentDetailResponse` |
| 读取 Chunk 预览 | `GET /api/v1/documents/{document_id}/preview` | 200 | `ChunkPreviewResponse` |
| 批准或拒绝 | `POST /api/v1/documents/{document_id}/review` | 200 | `ReviewResponse` |
| 健康检查 | `GET /api/v1/health` | 200 | `HealthResponse` |

### 10.5 API Client 方法签名

```ts
export interface ListDocumentsParams {
  status?: DocumentStatus;
  limit?: number;
  offset?: number;
}

export interface UploadDocumentInput {
  file: File;
  partition: Partition;
  title?: string;
}

export interface PreviewParams {
  limit?: number;
  offset?: number;
}

export interface DocumentsApi {
  upload(input: UploadDocumentInput): Promise<UploadDocumentResponse>,
  list(params?: ListDocumentsParams): Promise<DocumentListResponse>,
  get(documentId: string): Promise<DocumentDetailResponse>,
  preview(
    documentId: string,
    params?: PreviewParams,
  ): Promise<ChunkPreviewResponse>,
  review(
    documentId: string,
    input: ReviewRequest,
  ): Promise<ReviewResponse>,
}

export interface KnowledgeApi {
  route(input: RouteRequest): Promise<RouteResponse>,
  chat(input: ChatRequest): Promise<ChatResponse>,
}

export interface SystemApi {
  health(): Promise<HealthResponse>,
}
```

### 10.6 上传请求实现

```ts
async function uploadDocument(
  input: UploadDocumentInput,
): Promise<UploadDocumentResponse> {
  const body = new FormData();
  body.append("file", input.file);
  body.append("partition", input.partition);
  if (input.title) body.append("title", input.title);

  return apiFetch("/api/v1/documents", {
    method: "POST",
    body,
  });
}
```

### 10.7 审核请求约束

批准：

```ts
const approveRequest: ReviewRequest = {
  action: "approve",
  confirmed_partition: "finance",
  reviewer_name: null,
  note: "章节和分区确认无误",
};
```

拒绝：

```ts
const rejectRequest: ReviewRequest = {
  action: "reject",
  confirmed_partition: null,
  reviewer_name: null,
  note: "文件内容不完整",
};
```

批准时 `confirmed_partition` 必填；拒绝时固定为 `null`。第一轮没有登录，不在前端伪造审核人身份。

---

## 11. 页面状态和错误处理

### 11.1 全局状态

每个页面必须覆盖：

- 首次加载。
- 正常内容。
- 空数据。
- API 错误。
- 网络超时。
- 操作成功。

不得只实现 happy path。

### 11.2 常见错误映射

| 后端错误码 | 前端处理 |
| --- | --- |
| `VALIDATION_ERROR` | 按 `details.field` 定位字段，无法定位时显示页面错误 |
| `INVALID_PARTITION` | 标记分区选择并要求重新选择 |
| `UNSUPPORTED_FILE_TYPE` | 标记文件区域，保留分区选择 |
| `FILE_TOO_LARGE` | 显示限制，允许重新选择文件 |
| `EMPTY_DOCUMENT` | 说明没有可解析正文 |
| `DOCUMENT_PARSE_FAILED` | 显示 `request_id` 和重试入口 |
| `DUPLICATE_DOCUMENT` | 显示已存在文档并提供查看入口 |
| `DOCUMENT_NOT_FOUND` | 显示文档不存在并提供返回上传页入口 |
| `PREVIEW_NOT_READY` | 重新读取文档状态，不循环高频重试 |
| `INVALID_DOCUMENT_STATE` | 刷新当前文档状态并禁用审核操作 |
| `REVIEW_PARTITION_REQUIRED` | 标记最终分区选择 |
| `INDEX_WRITE_FAILED` | 保留审核页，提示没有完成入库 |
| `ROUTE_CLARIFICATION_REQUIRED` | 展示分区快捷选择 |
| `SENSITIVE_INPUT_BLOCKED` | 提示删除敏感值后重新提交 |
| `LLM_TIMEOUT` | 保留问题并提供手动重试 |
| `SERVICE_UNAVAILABLE` | 显示服务暂不可用，并读取 `details.health` 展示组件状态 |
| `INTERNAL_ERROR` | 显示通用错误和 `request_id`，不展示堆栈 |

HTTP 200 的业务 `code` 处理：

| code | 页面行为 |
| --- | --- |
| `OK` | 正常展示回答或路由 |
| `ROUTE_CLARIFICATION_REQUIRED` | 展示 `suggested_partitions` 快捷选择 |
| `ROUTER_INVALID_OUTPUT` | 提示路由暂时无法确定，允许手动选区 |
| `NO_INTERNAL_EVIDENCE` | 显示内部知识库暂无依据，不当作网络错误 |
| `SENSITIVE_INPUT_BLOCKED` | 显示安全提示，不进行自动重试 |

### 11.3 Toast 与页面错误

- 与当前字段直接相关的错误放在字段附近。
- 会阻止整个页面继续操作的错误使用页面级警告。
- 短暂成功提示可以使用 Toast。
- 不使用 Toast 展示长段解析错误或审核原因。
- 动态提示使用 `aria-live="polite"`，校验错误使用 `role="alert"`。

---

## 12. 可访问性与键盘操作

- 所有表单控件必须有可见 label。
- 分区选择使用原生 radio。
- 上传区域必须包含原生 file input，键盘可以触发。
- 按钮使用原生 `button`，不能用 `div` 模拟。
- 图标装饰元素设置 `aria-hidden="true"`。
- 图标按钮必须有 `aria-label`。
- 焦点样式必须可见，不能全局移除 outline。
- Tab 顺序遵循页面视觉顺序。
- 错误信息与对应字段通过 `aria-describedby` 关联。
- 加载状态不要持续抢占屏幕阅读器焦点。
- 颜色不是状态的唯一表达方式。

---

## 13. 前端测试

### 13.1 API 契约测试

必须覆盖：

- `npm run api:check` 不产生未提交类型差异。
- 每个 API Client 方法使用文档定义的路径和 HTTP 方法。
- JSON 请求使用 `snake_case` 字段。
- 上传请求不手动覆盖 multipart `Content-Type`。
- 201 上传响应可以解析为 `UploadDocumentResponse`。
- 200 业务失败响应按 `code` 分支，而不是抛出网络错误。
- 非 2xx 响应可以解析为 `ErrorResponse`。
- `request_id` 在成功和失败响应中均被保留。
- `null` 字段不会被错误当成缺失契约。
- 未知枚举值在开发和测试环境中触发显式失败。

### 13.2 组件测试

必须覆盖：

- `PartitionSelector` 单选行为。
- 自动路由映射为 `partition_hint=null`。
- 上传页没有文件或分区时不能提交。
- 文件大小和扩展名预检。
- `UploadDropzone` 键盘可用。
- `ChunkPreviewList` 分页和单条展开。
- 审核页只有 `pending_review` 可以批准或拒绝。
- 批准请求使用最终确认分区。

### 13.3 页面集成测试

必须覆盖：

1. 问答页右上角按钮进入上传页。
2. 浏览器后退返回问答页。
3. 上传成功进入审核页。
4. 审核页刷新后能重新加载状态。
5. 修改分区后批准请求提交新分区。
6. 拒绝后页面显示 `rejected`。
7. `ready` 后可以返回问答并选择对应分区。
8. API 错误不会清空已选文件之外的表单信息。

### 13.4 视觉与响应式测试

使用 Playwright 截图检查：

- `1440 × 900` 问答页和上传页。
- `1024 × 768` 问答页、上传页和审核页。
- `390 × 844` 三个页面。

检查项：

- 右上角“上传知识”位置明确且不遮挡内容。
- 侧栏和主内容不重叠。
- Composer、按钮和最长中文标签不溢出。
- 上传两列在窄屏正确变成单列。
- Chunk 长文本不会造成横向滚动。
- 加载、错误和成功状态不会改变主布局宽度。

---

## 14. 前端实施阶段

### Phase F0：工程初始化

- [ ] 创建 React + TypeScript + Vite 项目。
- [ ] 配置 Router 和 API Base URL。
- [ ] 从 `contracts/openapi.json` 生成 TypeScript 类型。
- [ ] 建立基础样式、颜色和响应式断点。
- [ ] 引入 `lucide-react`。
- [ ] 建立 Vitest、Testing Library 和 Playwright。

交付：空应用可以启动，三个路由可访问。

### Phase F1：应用框架与问答页

- [ ] 实现 `AppShell` 和左侧栏。
- [ ] 实现顶部操作栏和右上角“上传知识”。
- [ ] 实现空会话页面。
- [ ] 实现分区模式选择。
- [ ] 实现 Composer、消息流和引用列表。
- [ ] 对接 `/chat`。

交付：可以自动路由或指定分区完成一次问答。

### Phase F2：上传页

- [ ] 实现文件选择和拖放。
- [ ] 实现文件类型与大小预检。
- [ ] 实现分区选择板块。
- [ ] 实现标题输入和提交状态。
- [ ] 对接 `/documents`。
- [ ] 上传成功跳转审核页。

交付：可以选择分区上传文档并进入待审核状态。

### Phase F3：审核页

- [ ] 实现文档状态头部。
- [ ] 实现 Chunk 分页预览。
- [ ] 实现最终分区确认。
- [ ] 实现拒绝确认和批准入库。
- [ ] 对接状态、预览和审核接口。

交付：可以查看解析结果并批准或拒绝入库。

### Phase F4：质量验证

- [ ] 完成组件和页面集成测试。
- [ ] 完成桌面和移动截图检查。
- [ ] 检查键盘操作和可访问性。
- [ ] 检查错误、空状态和加载状态。
- [ ] 更新 README 启动与联调说明。

交付：前端流程可演示、可复现、可与后端联调。

---

## 15. Definition of Done

- [ ] 页面布局与参考图的信息结构一致，但使用自己的品牌和内容。
- [ ] 前端类型与后端 OpenAPI 一致，`api:check` 通过。
- [ ] 所有 API 方法、状态码、业务 code 和错误体都有契约测试。
- [ ] 成功和失败响应都保留后端 `request_id`。
- [ ] 左侧栏、顶部栏和主内容区在桌面端稳定显示。
- [ ] 右上角存在清晰的“上传知识”按钮。
- [ ] 点击按钮进入独立上传页面。
- [ ] 问答页支持自动路由和三个手动分区。
- [ ] 上传页必须选择文件和一个分区。
- [ ] 上传成功进入审核预览页。
- [ ] 审核页能分页查看 Chunk。
- [ ] 审核页能确认或修改最终分区。
- [ ] 批准、拒绝、失败和 ready 状态都有明确界面。
- [ ] 不在前端持久化敏感问题或文档正文。
- [ ] 桌面与移动布局没有重叠、裁切或横向溢出。
- [ ] 所有核心控件可通过键盘使用。
- [ ] 组件测试、页面集成测试和视觉测试通过。
- [ ] README 包含安装、启动、构建、测试和后端联调说明。

---

## 16. 给编码 Agent 的首个前端任务

```text
请先阅读 txtai-partitioned-kb-frontend-spec.md、后端规格和项目中的 AGENTS.md。

本任务完成 Phase F0 和 Phase F1：

1. 创建或接入 React + TypeScript + Vite 前端。
2. 实现参考图风格的 AppShell、左侧会话栏和顶部操作栏。
3. 在右上角实现带 Upload 图标的“上传知识”按钮，并跳转 /knowledge/upload。
4. 实现问答首页空状态、自动/财务/人事/技术分区选择和 Composer。
5. 实现消息列表与引用展示。
6. 建立类型安全 API Client 并对接 /api/v1/chat。
7. 实现 720px 和 420px 响应式布局。
8. 编写核心组件测试和三种视口截图测试。

不要复制参考产品的品牌、Logo 和内容，不要实现登录、联网、多分区并行检索或无关仪表盘。

开始前说明：
- 现有前端技术栈和目录判断；
- 准备新增或修改的文件；
- 页面和组件边界；
- 与后端 API 的联调假设。

完成后报告：
- 修改文件；
- 启动地址；
- 测试命令和真实结果；
- 桌面和移动截图；
- 已知限制和 Phase F2 入口。
```
