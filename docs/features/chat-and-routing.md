# 聊天与分区路由

> 文档状态：已实现  
> 最近核对：2026-09-03
> 代码基线：`61c551f` 加当前工作树快照  
> 维护责任：待指定

## 1. 功能说明

聊天功能接收企业知识问题，在财务、人事和技术三个知识分区中选择一个或两个分区检索，并基于已审核证据返回回答和可追溯引用。用户可以显式指定分区，也可以让 Router LLM 自动判断单一分区、复合分区或要求澄清。用户显式授权后，全部内部检索均无证据的公开低风险问题可以使用受限网络搜索兜底。每条 assistant 回答还返回分区检索与模型调用的独立耗时，用于区分索引性能与模型等待时间。

代码、契约和 Fake Provider 测试已覆盖内部单分区、复合路由、低分过滤及受限联网兜底。真实模型只完成两条内部问答兼容性冒烟；真实 Tavily 请求本轮返回 HTTP 401，当前知识 fixture 也不代表业务回答质量已通过。

## 2. 范围与非目标

| 类型 | 内容 |
| --- | --- |
| 包含 | 输入安全；手动单分区；自动单分区；最多两个分区复合路由；独立检索；`ready` 校验；LLM 或抽取式内部回答；显式授权的零证据受限联网；内部与网络来源白名单；受限 Markdown 回答展示；浏览器本地会话管理 |
| 不包含 | 三分区同时检索；内部与网络证据混合回答；任意网页抓取；登录、下载和脚本执行；服务端持久会话；跨设备同步；跨轮上下文；路由置信度；模型质量评估；基于身份的知识权限 |

## 3. 用户流程与状态

1. 用户在 `/` 选择自动路由或财务、人事、技术之一并提交问题。
2. 前端在发送时创建不可变的请求上下文：`requestId`、`conversationId`、`userMessageId` 和 `assistantMessageId`。用户消息、加载状态、成功回答、失败状态和重试输入都只使用其中的 `conversationId`；`activeConversationId` 只决定当前展示哪个会话。
3. 前端调用 `POST /api/v1/chat`，请求期间保留输入并显示该请求所属会话的加载状态；用户可切换到其他会话，原请求继续在后台执行。
4. 后端先阻断秘密值，或对邮箱、手机号、私网 IP 脱敏。
5. 存在 `partition_hint` 时跳过 Router；否则 Router 返回 `single`、`composite` 或 `clarify`。公司基础信息（如公司简介、组织概况、主营业务、使命愿景、办公地点或联系渠道）默认路由为人事单分区；仅当同时存在可独立检索的财务或技术事项时才使用复合路由。
6. Retriever 逐个访问计划中的索引，过滤低于 `RETRIEVAL_MIN_SCORE` 的召回，再用 SQLite 过滤非 `ready` 或分区不匹配的结果，同时按分区记录“索引检索加本地证据校验”耗时。
7. 自动路由和 Answer LLM 分别记录调用及本地输出校验耗时；有内部证据时由 Answer LLM 生成回答，未配置、超时或传输失败时使用每个分区首个 Chunk 的抽取式回答，不进入联网。
8. 全部内部检索组均为空、用户通过输入框左下角的“未命中时联网”图标开关显式启用联网且问题通过低风险资格判断时，Tavily Provider 最多返回 5 条结构化结果，再由独立 Web Answer Prompt 生成最多 3 条来源的回答。
9. 后端分别校验内部 Chunk ID 或网页 URL 白名单；Answer 的 JSON `answer` 字段可包含受限 Markdown。前端校验 `answer_source`、计时字段及两类 Citation 的互斥形状，只为 assistant 消息渲染 Markdown，并在其右上角显示本轮计时。
10. `clarify` 响应在助手消息内展示统一提示语和三个内容自适应的轻量分区按钮；选择后使用原问题发起手动单分区请求，clarify 本身不触发联网。

本地会话清理流程：用户从最近会话的更多菜单删除单条会话，或从最近会话标题区清空全部历史；两种破坏性操作都先显示确认对话框。删除当前会话后选择列表中相邻会话，没有剩余项时创建空会话，并把结果写入现有浏览器快照。连续点击“开启新对话”会替换尚无消息的空会话，不积累不可见空项。

| 当前状态 | 操作或条件 | 下一状态 | 失败处理 |
| --- | --- | --- | --- |
| 空会话 | 提交问题 | 请求中 | 网络失败时保留问题并显示页面错误 |
| 请求中 | 秘密值命中 | 已响应、不可回答 | `SENSITIVE_INPUT_BLOCKED`，不访问模型或索引 |
| 请求中 | Router 不可用或返回 clarify | 待用户选区 | `ROUTE_CLARIFICATION_REQUIRED`，不访问索引 |
| 请求中 | 全部分区无证据且未授权联网 | 已响应、不可回答 | `NO_INTERNAL_EVIDENCE` |
| 请求中 | 全部分区无证据、已授权且通过资格判断 | 联网搜索中 | 搜索未配置、失败或无可靠来源时仍返回 `NO_INTERNAL_EVIDENCE` |
| 联网搜索中 | 网页回答与 URL 白名单通过 | 已响应、可回答 | `OK`、`answer_source=web`，只展示公开网络来源 |
| 请求中 | Answer Provider 失败 | 已响应、可回答 | 抽取式降级并返回 warning |
| 请求中 | Answer 引用越界或为空 | 已响应、不可回答 | 引用清空，返回证据校验 warning |
| 请求中 | 回答和引用通过校验 | 已响应、可回答 | `OK`，前端按分区展示引用 |
| 请求中 | 用户切换会话 | 原会话继续请求；新会话正常可用 | UI 只切换 `activeConversationId`，不改变请求上下文 |
| 请求中 | 传输失败 | 原会话显示错误并回填原问题 | 错误和重试输入仅写入该会话运行态 |
| 任意本地会话 | 删除非当前会话并确认 | 当前会话不变 | 存储失败时仅当前页面状态生效 |
| 当前本地会话 | 删除并确认 | 相邻会话或新空会话 | 存储失败时刷新可能恢复旧历史 |
| 存在本地历史 | 清空并确认 | 唯一新空会话 | 取消确认时不修改状态或存储 |

## 4. 前端实现

| 路径或组件 | 职责 | 关键状态或行为 |
| --- | --- | --- |
| `frontend/src/pages/ChatPage.tsx` | 页面编排和请求 | 在发送瞬间固定请求上下文；以目标 `conversationId` 写入消息和完成/失败状态；当前会话只用于展示和新请求起点 |
| `frontend/src/features/chat/ChatSessionContext.tsx` | 会话状态 | 管理当前会话和按会话划分的运行态；`pendingRequestIds`、错误及重试输入不写入历史快照；首个问题生成标题；历史变化后触发本地持久化 |
| `frontend/src/features/chat/chatSessionStorage.ts` | 会话存储适配 | 使用带版本号的 `localStorage` 格式；读取失败时回退为空会话 |
| `frontend/src/components/layout/AppSidebar.tsx` | 会话导航 | 展示最近会话；提供单条更多菜单、清空入口和确认对话框 |
| `frontend/src/features/chat/ChatComposer.tsx` | 问题输入 | 单行空状态约 90px、高度随多行输入增长；2000 字限制；左右对齐的 30px 圆形联网与发送工具按钮；发送按钮仅在有有效输入时使用主题色；默认关闭的“未命中时联网”图标开关；开启时以低饱和蓝灰图标和浅蓝灰底色表达状态，悬浮提示随状态说明开关含义 |
| `frontend/src/features/chat/MessageList.tsx` | 回答、受限 Markdown、计时、分区澄清和引用 | assistant 右上角显示每个分区的索引检索耗时及 Router/Answer 模型耗时；支持标题、段落、列表、粗体、行内代码和链接；跳过原始 HTML 和图片；`clarify` 使用三个独立轻量按钮，选择后仍按原问题和手动单分区发起请求；内部 Citation 按分区分组；网络回答单独显示公开 URL 来源 |
| `frontend/src/components/PartitionSelector.tsx` | 路由选择 | 自动模式映射为 `null`；手动模式映射 Partition；分段 Tabs 以低对比灰底、白色选中项和极浅描边表达当前路由 |
| `frontend/src/constants/partitions.ts` | 分区标签 | 维护三个分区和 composite/clarify 展示文本 |
| `frontend/src/api/client.ts` | HTTP 和运行时契约校验 | 校验 route、answer_source、内部与网络 Citation 的互斥形状 |

前端不会自行拆分问题或合并多个聊天请求。单一会话在加载时禁止再次提交，但不同会话可同时存在请求；`pendingRequestIds` 以会话为键保存，因此 A 请求进行中时用户可切到 B 并发提问。当前 API 为普通 HTTP 响应，尚未使用 SSE/WebSocket；未来流回调也必须仅使用其创建时固定的 `conversationId` 和 `assistantMessageId`，不得重新读取 UI 当前会话。选择澄清按钮后会重新追加原问题和新的回答，当前没有隐藏或合并前一次 clarify 消息。

回答在服务端始终以 JSON 字段传输，以便校验 Citation 白名单；`answer` 的文本内容可使用受限 Markdown。前端仅使用 `react-markdown` 和 `remark-gfm` 渲染 assistant 内容，显式跳过原始 HTML 和图片，且链接始终以新窗口和 `noreferrer` 打开。用户输入与 warning 保持纯文本，Citation 继续由独立组件渲染，不能由模型 Markdown 覆盖或伪造。

每次 `ChatResponse.timing` 包含顺序与 `searched_partitions` 一致的 `retrieval` 数组，以及可为空的 `router_llm_ms`、`answer_llm_ms`。前端只显示实际发生的指标：手动分区不显示 Router，抽取式回答不显示 Answer 模型。历史会话将计时与 assistant 消息一同存入现有 `localStorage`；格式不合法的快照会整体回退为空会话。

进入活跃会话后，聊天区域占满 Top Bar 下方的可用高度；消息列表使用主内容区最右侧的细滚动条并自动定位到最新消息，消息正文、路由选择器和输入框保持居中，底部控制区始终保留在可见区域。空会话仍由页面容器负责响应式布局。

聊天请求超时为 100 秒，用于覆盖 Router 最多一次结构修复和一次 Answer 调用；其他普通 API 仍使用 30 秒默认超时。

## 5. 后端实现

| 路径或服务 | 职责 | 上下游依赖 |
| --- | --- | --- |
| `app/api/chat.py` | API 入口和对象装配 | Settings、LLM/Search Provider、IndexRegistry、AsyncSession |
| `app/services/chat.py` | 端到端聊天编排 | Safety、Router、Retriever、内部/网络 Answerer |
| `app/services/input_safety.py` | 本地输入安全 | 正则检测和 IP 地址判断 |
| `app/services/routing.py` | Router Prompt、解析和一次修复 | LLM Provider、LLMRoutePlan |
| `app/services/retriever.py` | 分区查询、SQLite 校验和分区级检索计时 | IndexRegistry、DocumentTable、ChunkCandidateTable |
| `app/services/answering.py` | 内部和网络独立 Prompt 与引用白名单 | LLM Provider、RetrievalGroup、WebSearchResult |
| `app/services/web_search.py` | Tavily 调用、结果规范化、URL 与问题资格过滤 | httpx、Settings |
| `app/services/llm.py` | OpenAI-compatible 调用 | httpx Chat Completions |
| `app/models/schemas.py` | 路由、回答和 HTTP 模型不变量 | Pydantic validators |

Router 输出最多修复一次，必须满足严格 JSON 结构。复合路由必须恰好有两个不同分区。Router Prompt 将公司基础信息明确映射为人事单分区，并提供 HR JSON 示例；公司基础信息与可独立检索的财务或技术事项并存时仍使用复合路由。检索按 Router 子查询顺序串行执行，每个分区使用独立 top-k，并按 `RETRIEVAL_MIN_SCORE` 过滤低相关结果；不比较跨索引分数。默认值 `0.5` 适用于当前 Embedding 模型和演示数据，设置为 `0` 可关闭过滤并保留所有召回。

联网 Provider 只接收通过安全检查的原问题并使用 Tavily `basic` 搜索；它不抓取结果页。默认请求超时为 60 秒，可通过 `WEB_SEARCH_TIMEOUT_SECONDS` 在 1–120 秒内调整。只保留公开 HTTPS URL，拒绝本机、私网、保留地址、带凭据 URL 和 `.local` 主机，并移除常见跟踪参数、片段、重复 URL 及同域名第三条以后结果。搜索失败时后端只记录失败类别和 HTTP 状态码，不记录问题、Key 或 Provider 响应正文；前端安全区分认证、限流、HTTP、超时、网络与无效响应。

## 6. 数据库与存储

| 存储类型 | 表、目录或索引 | 读/写 | 用途与一致性要求 |
| --- | --- | --- | --- |
| React 内存 | `ChatSessionContext` | 读写 | 会话历史、回答计时、当前 UI `activeId` 与按 `conversationId` 分隔的运行态；运行态不持久化 |
| 浏览器 `localStorage` | `partitioned-kb.chat-session` | 读写 | 当前浏览器的版本化历史快照；回答计时随消息恢复，进行中的请求、错误和重试输入不恢复 |
| SQLite | `documents` | 只读 | 校验 `ready` 和 `confirmed_partition`，读取标题 |
| SQLite | `chunk_candidates` | 只读 | 读取回答正文和引用定位 |
| txtai | `data/indexes/<partition>/` | 只读 | 每个子查询只访问声明分区 |
| 外部模型 | Router/Answer endpoint | 请求 | 只发送安全问题、子查询和本次命中证据 |
| 外部搜索 | Tavily endpoint | 请求 | 仅在显式授权、零内部证据和资格判断通过后发送安全问题；不持久化结果 |

SQLite 和索引关系详见[数据与存储](../architecture/data-and-storage.md)。

## 7. API 接口

| 方法 | 路径 | 用途 | 请求模型 | 响应模型 | 主要错误码 |
| --- | --- | --- | --- | --- | --- |
| `POST` | `/api/v1/chat` | 路由、检索和回答 | `ChatRequest` | `ChatResponse` | `INVALID_PARTITION`、`VALIDATION_ERROR`、`INDEX_NOT_READY`、`PARTITION_ISOLATION_VIOLATION` |

`ChatRequest.allow_web_fallback` 默认 `false`。`ChatResponse.code` 的业务结果为 `OK`、`ROUTE_CLARIFICATION_REQUIRED`、`NO_INTERNAL_EVIDENCE` 或 `SENSITIVE_INPUT_BLOCKED`，这些结果使用 HTTP 200。`answer_source` 为 `internal`、`web` 或 `none`；`citations` 和 `web_citations` 必须按来源互斥。`searched_partitions` 只记录内部索引并保持现有 route 形状。`timing.retrieval` 对每个实际访问分区返回毫秒整数，计量 txtai 索引查询与 SQLite 证据校验；`router_llm_ms` 和 `answer_llm_ms` 仅在对应模型实际被调用时有值，不用于检索性能比较。

本地会话删除和清空不调用后端 API，也不修改 SQLite、文件或 txtai 索引。当前后端不提供服务端会话持久化，`ChatRequest` 也不携带 `conversationId`；它只处理一次独立问答。前端在本地生成会话 ID 并在整个网络请求生命周期中固定使用，用于浏览器端消息与运行态归属。

权威契约：`contracts/openapi.json`  
契约生成命令：`uv run --no-sync python -m scripts.export_openapi`

## 8. 文件路径与修改边界

| 文件或目录 | 职责 | 修改级别 | 修改要求 |
| --- | --- | --- | --- |
| `app/services/chat.py` | 聊天编排 | `owned` | 同步聊天集成测试和本文档 |
| `app/services/web_search.py` | 受限搜索、URL 规范化和资格过滤 | `owned` | 不直接访问结果 URL；保持 Provider 可替换和 Fake 可测试 |
| `app/services/routing.py` | Router | `owned` | 维持严格输出和最多两个分区 |
| `app/services/answering.py` | 内部/网络 Answer 与引用校验 | `owned` | 两类来源白名单必须保持隔离 |
| `app/services/retriever.py` | 检索、分数阈值、SQLite 校验和分区计时 | `owned` | 维持分区隔离、最低分数、ready 过滤和每个已检索分区一条计时 |
| `app/services/input_safety.py` | 输入安全 | `owned` | 更新安全测试并评估模型数据边界 |
| `app/services/llm.py` | 共享模型传输 | `shared` | 检查 Router、Answer、配置和健康状态 |
| `app/api/chat.py` | HTTP 入口 | `owned` | Schema 变化后同步 OpenAPI |
| `app/models/enums.py`、`app/models/schemas.py` | 跨端模型和聊天计时 | `shared` | 检查文档 API、前端类型、契约和历史快照读取 |
| `app/core/config.py`、`.env.example` | 配置 | `shared` | 同步运行文档、ChatService 消费者和健康检查 |
| `frontend/src/pages/ChatPage.tsx`、`frontend/src/features/chat/` | 聊天 UI | `owned` | 同步组件测试和交互状态 |
| `frontend/src/components/layout/AppSidebar.tsx` | 会话历史菜单与确认交互 | `owned` | 同步键盘、触屏和删除确认测试 |
| `frontend/src/features/chat/ChatSessionContext.test.tsx` | 本地会话状态测试 | `owned` | 覆盖删除回退、清空和刷新后不恢复 |
| `frontend/src/api/client.ts`、`frontend/src/api/types.ts` | API 适配 | `shared` | 保持运行时校验和生成类型一致 |
| `frontend/src/api/generated.ts`、`contracts/openapi.json` | 生成契约 | `generated` | 只使用生成命令更新 |
| `frontend/src/styles.css` | 全局样式 | `shared` | 检查上传、审核和响应式页面 |
| `data/indexes/`、`data/metadata/` | 检索和元数据 | `runtime-data` | 不用于普通验证写入 |
| 认证、权限、生产模型与搜索配额 | 生产边界 | `approval-required` | 需要明确安全、费用与部署决策 |

## 9. 核心不变量与安全约束

- 用户 `partition_hint` 优先级最高，并且跳过 Router。
- 自动路由中，公司基础信息必须使用 `hr` 单分区；只有同时包含独立财务或技术事项时才可使用复合路由。
- Router `composite` 只能选择两个不同分区；`clarify` 不得访问索引。
- 每个子查询只能访问声明的分区索引。
- 只有 SQLite 中 `ready` 且最终分区匹配的 Chunk 可以成为证据。
- 低于 `RETRIEVAL_MIN_SCORE` 的 txtai 召回不是内部证据，不得进入 Answer、Citation 或阻断显式授权的联网兜底。
- Citation 必须属于本次命中，且 Citation 分区必须在 `searched_partitions` 中。
- 秘密值不得发送给索引或模型；个人信息和私网地址先脱敏。
- Answer 输入不得包含服务器路径、校验和、Embedding 文本或未命中正文。
- Answer 的 `answer` 可以使用受限 Markdown 增强可读性，但不得包含 HTML、图片、代码围栏或自行构造的来源链接；引用必须继续通过结构化 Citation 字段校验和展示。
- 前端只渲染 assistant Markdown，必须跳过原始 HTML 和图片；用户消息和 warning 不得作为 Markdown 或 HTML 解析。
- `timing.retrieval` 必须与 `searched_partitions` 一一对应且顺序一致；每项为非负整数毫秒，包含该分区的索引查询与本地证据校验，不包含 Router 或 Answer 模型调用。
- `router_llm_ms` 与 `answer_llm_ms` 仅在实际调用相应模型时返回非空值；前端不得将模型耗时归入索引性能。
- 联网必须由当前请求显式授权，并且只能发生在全部内部检索组均无 Chunk 之后。
- 脱敏问题、内部制度问题、高风险问题、clarify 和 Router 故障不得发送到搜索 Provider。
- 内部与网络证据不得混合；网页答案只能引用本次规范化搜索结果中的 URL，网页文本中的指令一律视为不可信数据。
- 网络 URL 必须为公开 HTTPS 地址；最终最多 3 条来源，同域名最多 2 条。
- API Key 只能来自环境变量，不得进入响应、日志或文档。
- 长会话只能滚动消息列表，不能把路由选择器和输入框推离可见区域。
- 本地会话存储不得包含 API Key；格式无效或版本不兼容时必须回退为空会话。
- `activeConversationId` 只能决定 UI 当前展示的会话，不能作为异步请求回调的写入目标。
- 每个请求必须在发送前固定 `requestId`、`conversationId`、用户消息 ID 和 assistant 消息 ID；完成、失败、重试和未来流式回调只能使用该上下文。
- `pendingRequestIds`、错误和重试输入必须按 `conversationId` 独立保存；不同会话的并发请求不得共享 loading、错误或消息写入位置。
- 删除任意会话后，状态中必须至少保留一个会话；删除当前会话时必须选择相邻会话作为回退，没有剩余会话时创建空会话。
- 单条删除和清空全部历史必须经过明确确认；取消操作不得修改内存或 `localStorage`。
- 会话更多菜单及确认对话框必须可通过键盘访问，移动端不得依赖悬停显示操作入口。

## 10. 错误处理与恢复

| 场景 | 对外表现 | 内部处理 | 恢复方式 |
| --- | --- | --- | --- |
| Router 未配置、超时或输出无效 | HTTP 200 clarify + warning | 不检索 | 用户手动选择分区 |
| 索引未加载 | HTTP 503 `INDEX_NOT_READY` | AppError | 恢复索引后重试 |
| 索引命中其他分区文档 | HTTP 500 `PARTITION_ISOLATION_VIOLATION` | 阻止回答 | 检查索引污染并重建 |
| 全部分区无 ready 证据且未授权/不符合联网范围 | HTTP 200 `NO_INTERNAL_EVIDENCE` | 返回空引用，不访问 Search Provider | 补充内部文档或调整为公开低风险问题后显式授权 |
| 联网认证、限流、HTTP、超时、网络、无效响应或无结果 | HTTP 200 `NO_INTERNAL_EVIDENCE` + 对应安全 warning | 不重试，不使用模型参数知识补全；日志仅记录类别和 HTTP 状态码 | 检查 Key、额度、网络或稍后新请求 |
| 网页 URL 引用越界或为空 | HTTP 200 `NO_INTERNAL_EVIDENCE` + warning | 丢弃网页草稿和全部网络引用 | 检查 Web Answer Prompt/模型输出 |
| Answer Provider 失败 | HTTP 200 `OK` + warning | 抽取每组第一条证据 | 恢复模型后新请求 |
| Answer 引用越界 | HTTP 200 `NO_INTERNAL_EVIDENCE` | 丢弃模型回答和引用 | 检查 Prompt/模型输出 |
| 前端运行时契约校验失败 | 页面连接类错误 | 抛出 Error | 同步 OpenAPI、生成类型和前端适配 |
| 某会话请求失败且用户已切换 | 当前会话不显示该错误 | 原会话运行态记录错误与重试输入 | 切回原会话后重试，新的请求上下文仍绑定原会话 |
| 用户取消会话删除或清空 | 对话框关闭，历史不变 | 不调用状态删除方法 | 无需恢复 |
| 浏览器拒绝本地存储写入 | 当前页面仍更新 | `localStorage` 写入失败被隔离 | 刷新后可能恢复旧快照；后续可增加可见提示 |

## 11. 测试与验证

| 层级 | 覆盖内容 | 文件或命令 |
| --- | --- | --- |
| 后端集成 | manual、clarify、composite、联网授权、低分过滤、内部优先、范围拒绝、引用越界 | `tests/integration/test_chat_api.py` |
| 后端单元 | 邮箱、手机号、私网 IP 脱敏 | `tests/unit/test_input_safety.py` |
| 后端单元 | 联网资格、公开 HTTPS URL 规范化和搜索失败分类 | `tests/unit/test_web_search.py` |
| 后端单元 | 公司基础信息的人事路由 Prompt 与 HR JSON 示例 | `tests/unit/test_routing.py` |
| 前端组件 | 单分区提问、澄清分区选择重发、内部/网络引用展示、联网开关、网络失败 | `frontend/src/App.test.tsx` |
| 前端 Markdown | assistant 标题、列表、粗体、行内代码、安全链接，以及原始 HTML 和图片跳过 | `frontend/src/App.test.tsx` |
| 后端计时 | 单分区返回一个检索时间且无未调用模型时间；复合路由返回两个分区检索时间、路由和回答模型时间 | `tests/integration/test_chat_api.py` |
| 前端计时 | 运行时契约校验与 assistant 右上角展示 | `frontend/src/api/client.test.ts`、`frontend/src/App.test.tsx` |
| 本地会话计时 | 非法快照计时回退为空会话 | `frontend/src/features/chat/ChatSessionContext.test.tsx` |
| 前端异步会话 | A 请求后切 B、新会话首次请求后切 B、A/B 并发、切回查看、失败与原会话重试隔离、快速连续切换 | `frontend/src/App.test.tsx` |
| 前端会话 | 本地历史恢复、损坏数据回退 | `frontend/src/features/chat/ChatSessionContext.test.tsx` |
| 前端会话 | 删除非当前/当前/唯一会话、清空、空会话去重和持久化删除结果 | `frontend/src/features/chat/ChatSessionContext.test.tsx` |
| 前端交互 | 更多菜单、明确确认、取消和键盘入口 | `frontend/src/App.test.tsx` |
| 前端 API | JSON 字段、clarify 业务响应 | `frontend/src/api/client.test.ts` |
| 契约 | OpenAPI 与 FastAPI Schema 一致 | 内存比较或 `scripts.export_openapi` 后检查 diff |

2026-09-03：此前后端 32 个隔离测试、Ruff、Python 编译、OpenAPI 内存比较、前端生产构建和 22 个前端测试通过；本轮联网单元/聊天集成测试 18/18、Ruff 和 Python 编译通过。联网 Fake Provider 测试覆盖显式授权、低分过滤、内部优先、范围拒绝、Provider 结果规范化、来源展示、URL 安全和错误分类。真实只读请求确认 `0.411` 的无关 Docker 命中已被默认 `0.5` 阈值过滤并进入联网分支，Tavily 返回 HTTP 401，未获得网页回答或来源；未写入 RAG 运行数据。此前真实 Router/Answer 的两条只读冒烟仍有效；未运行完整 Playwright E2E 或模型质量评估。内置浏览器确认桌面和 390px 移动端联网开关无重叠且控制台无错误。异步会话归属修复后，前端 Vitest 38/38 通过；本轮聊天定向集成测试 13/13、Python 编译、OpenAPI 导出、前端生产构建通过，覆盖分区检索计时、模型计时、运行时契约、右上角展示和非法历史计时回退；公司基础信息人事路由 Prompt 单元测试与完整隔离后端测试 `48/48`、Ruff 通过。未执行真实模型、真实性能基准或业务验收。

## 12. 已知限制与后续计划

- 2026-09-07 审查确认当前为固定三分区路由，尚无多层知识节点或逐层路由。索引加载失败被当作空结果、top-k 过滤后未补充召回的问题及树化设计见[树状路由索引优化与实施方案](../plans/tree-routing-index-optimization.md)；本次仅补充计划，尚未修复或迁移。

- 真实 Router 和 Answer 已完成两条协议兼容性冒烟，但尚未进行批量路由或回答质量评估。
- 当前扩充 fixture 主要是通用占位句，缺少真实可核验的角色、期限、金额、材料和步骤，不能用于业务答案验收。
- 历史仅保存在当前浏览器的 `localStorage`，没有账号隔离、服务端会话、跨设备同步或跨轮上下文；清理站点数据会删除历史。
- 刷新页面不会恢复进行中的网络请求、会话级 loading、错误或重试输入；它们只存在于当前 React 运行期。
- 当前没有流式 API；引入 SSE 或 WebSocket 时，必须复用本功能定义的不可变请求上下文，逐 Chunk 写入原 `conversationId`。
- 当前指标用于单次本地观测，不是跨机器或跨负载的性能基准；索引预热、SQLite 缓存、CPU 竞争和复合检索的串行执行会影响对比结果。
- 不支持三个分区问题；这类问题返回 clarify。
- 没有关键词检索、RRF 或重排器。
- 输入安全是有限模式匹配，不等同于完整 DLP。
- 外部模型调用每次创建新的 httpx client，尚未实现连接池、限流和熔断。

### 12.1 受限联网兜底的剩余限制

- 当前仅实现 Tavily Provider；一次真实请求返回 HTTP 401，需有效 Tavily Key 后才能完成网页回答成功路径的服务端响应兼容性、费用和超时验证。
- 联网资格使用本地保守关键词规则，不是完整内容安全分类器，可能拒绝本可公开回答的问题。
- 自动 Router 返回 `clarify` 时不会直接联网；用户需要先选一个分区，让系统完成内部零证据检索。
- 第一阶段只使用搜索结果摘要，不抓取正文，因此复杂问题可能因证据不足继续拒答。
- 搜索结果没有可信域名评分或管理员 allowlist；只执行 HTTPS、地址类型、去重和同域名数量限制。
- 当前默认阈值 `0.5` 仅基于演示数据的少量只读分数对照，不是模型无关的质量标准；更换 Embedding 模型、语言、Chunk 结构或知识数据后需要重新校准。
- 联网开关是当前页面状态，不写入会话快照；刷新或创建新页面状态后恢复为关闭。
- 真实 Provider 接线后只进行用户明确授权的一到两条只读冒烟；批量质量评估、费用压测和配额策略仍需另行批准。
