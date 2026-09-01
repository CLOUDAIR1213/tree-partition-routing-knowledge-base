# `/chat` 复合路由与多分区问答开发计划

> 计划日期：2026-09-02  
> 状态：待开发  
> 设计性质：对 Round 1 单分区 MVP 的增量扩展，不覆盖原始规格的历史结论。

## 1. 背景与目标

当前 `/api/v1/chat` 支持用户显式指定 `finance`、`hr` 或 `tech`，并严格只检索一个分区。自动模式在 Router LLM 未接入时返回 `clarify`。

下一步目标：

1. 自动模式先由 Router LLM 判断问题属于单一分区、复合分区或需要澄清。
2. 单一分区问题继续只检索一个索引。
3. 复合问题由 Router LLM 拆分为最多两个分区子查询。
4. 每个子查询只访问对应分区索引，独立召回和校验证据。
5. Answer LLM 只基于本次命中的分组证据生成统一答案。
6. 保留现有用户手动指定分区和抽取式回答作为可靠降级路径。

本阶段不实现：

- 同时检索三个分区。
- 自动执行外部搜索。
- 对话记忆和跨轮路由状态。
- 基于 LLM 自报数值置信度的阈值判断。
- 大规模路由评估、模型质量验收或批量写入测试数据。

## 2. 总体流程

```text
原始问题
→ 本地 InputSafetyGuard
→ 是否存在 partition_hint？
  ├─ 是：保留现有单分区模式，跳过 Router LLM
  └─ 否：调用 Router LLM
       ├─ single：生成一个分区子查询
       ├─ composite：生成两个不同分区子查询
       └─ clarify：不检索，要求用户补充或选择分区
→ 每个子查询只访问对应 IndexRegistry 实例
→ SQLite 校验 ready + confirmed_partition
→ 按分区整理证据
→ Answer LLM 基于证据生成回答
→ 服务端校验引用属于本次命中
→ 返回回答、检索分区和引用
```

## 3. 路由模式

### 3.1 用户指定分区

当 `partition_hint` 非空时：

- 用户选择优先级最高。
- 不调用 Router LLM。
- 只访问指定分区索引一次。
- `decision_source="user_hint"`。
- Answer LLM 不可用时允许回退到当前抽取式回答。

### 3.2 自动单分区

Router LLM 判断问题只涉及一个业务分区时：

- 生成一个保留金额、错误码、产品名和专业术语的子查询。
- 只检索该分区。
- `route="finance" | "hr" | "tech"`。
- `searched_partitions` 只包含一个值。

### 3.3 自动复合分区

Router LLM 判断问题包含两个可独立检索的业务事项时：

- `route_kind="composite"`。
- 必须生成两个不同分区的子查询。
- 最多允许两个分区；三个分区或无法稳定拆分时返回 `clarify`。
- 两个分区分别检索，结果不得通过原始相似度直接跨索引排序。
- 最终回答按事项或分区组织，并分别引用证据。

示例：

```text
问题：新员工如何申请 GitLab 权限并报销认证考试费用？

tech 子查询：新员工 GitLab 权限申请流程
finance 子查询：认证考试费用报销流程
```

## 4. Router LLM 结构化输出

建议新增内部模型：

```python
class RouteKind(StrEnum):
    SINGLE = "single"
    COMPOSITE = "composite"
    CLARIFY = "clarify"


class RoutedSubquery(BaseModel):
    partition: Partition
    query: str


class LLMRoutePlan(BaseModel):
    route_kind: RouteKind
    subqueries: list[RoutedSubquery]
    needs_clarification: bool
    reason_code: Literal[
        "finance_policy",
        "hr_policy",
        "technical_operation",
        "multi_intent",
        "missing_context",
        "ambiguous_domain",
    ]
```

确定性校验规则：

- `single` 必须恰好包含一个子查询。
- `composite` 必须恰好包含两个不同分区的子查询。
- `clarify` 不得触发索引检索。
- 子查询不能为空，且长度不得超过问题长度限制。
- Router 输出非法时只允许一次结构修复；再次失败返回 `clarify`。
- 不增加或使用数值 `confidence`。

## 5. 复合检索策略

每个分区使用独立检索预算：

```text
每个分区 top_k = 3
最大分区数 = 2
Answer LLM 最大接收 Chunk 数 = 6
```

检索规则：

- 每个子查询只能调用其声明分区的索引。
- txtai 返回结果后，使用 SQLite 查询候选 Chunk 和文档状态。
- 只保留 `status=ready` 且 `confirmed_partition` 匹配的结果。
- 任一结果实际属于其他分区时抛出 `PARTITION_ISOLATION_VIOLATION`。
- 不直接比较不同索引的原始相似度。
- 证据按 Router 子查询顺序和各分区内部排名组织。

后续可增加分区内混合检索：txtai 向量召回与 SQLite FTS5 关键词召回通过 RRF 合并。该能力不作为明天首轮实现的阻塞项。

## 6. Answer LLM 与降级

Answer LLM 输入只能包含：

- 安全处理后的问题。
- Router 生成的子查询。
- 本次检索命中的 Chunk 正文与公开元数据。

禁止传入：

- 脱敏前问题。
- 未命中的知识库正文。
- 服务器路径、Checksum 或 Embedding 文本。
- API Key、Prompt 调试内容或隐藏推理过程。

回答规则：

- 有两个分区证据时，生成一个按事项分段的统一答案。
- 只有一个分区有证据时，只回答有依据的部分，并明确另一部分暂无内部依据。
- 两个分区均无证据时返回 `NO_INTERNAL_EVIDENCE`。
- Answer LLM 返回的引用必须是本次命中 Chunk ID 的子集。
- 引用为空或包含未知 ID 时降级为不可回答。
- Answer LLM 超时或未配置时，回退为按分区展示最高排名 Chunk 的抽取式回答。

## 7. API 契约变更

`ChatRequest` 保持兼容：

```json
{
  "question": "新员工如何申请 GitLab 权限并报销认证考试费用？",
  "partition_hint": null
}
```

建议扩展 `ChatResponse`：

```json
{
  "code": "OK",
  "answer": "GitLab 权限申请……\n\n认证考试费用报销……",
  "route": "composite",
  "decision_source": "llm",
  "answerable": true,
  "searched_partitions": ["tech", "finance"],
  "citations": [
    {
      "partition": "tech",
      "chunk_id": "tech-access:v1:00001",
      "document_id": "tech-access",
      "title": "演示权限申请规范",
      "section": "GitLab 权限",
      "page_start": null,
      "page_end": null
    }
  ],
  "suggested_partitions": [],
  "request_id": "req_example",
  "warning": null
}
```

契约调整：

- `RouteName` 增加 `composite`。
- `ChatResponse` 增加必填 `searched_partitions: list[Partition]`。
- `Citation` 增加必填 `partition: Partition`。
- 单分区响应也返回一个元素的 `searched_partitions`，避免前端条件猜测字段是否存在。
- 修改后重新导出 OpenAPI，并由前端重新生成 TypeScript 类型。

## 8. 前端调整

保留现有分区选择器：

- 手动选择 finance/hr/tech 时继续使用单分区模式。
- 选择“自动路由”时允许返回 single、composite 或 clarify。

复合回答展示：

- 消息元数据展示“技术 + 财务”而不是“复合分区”。
- Citation 按 `partition` 分组，并显示对应分区标签。
- 某一部分无证据时显示后端返回的明确说明，不自动重试其他分区。
- 前端不自行拆问题，也不自行合并不同请求的结果。

## 9. 配置建议

保留现有通用配置，并允许 Router 与 Answer 使用不同模型：

```dotenv
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=

ROUTER_LLM_MODEL=
ANSWER_LLM_MODEL=
LLM_TIMEOUT_SECONDS=30
COMPOSITE_MAX_PARTITIONS=2
COMPOSITE_TOP_K_PER_PARTITION=3
ANSWER_MODE=llm
```

当 `ROUTER_LLM_MODEL` 或 `ANSWER_LLM_MODEL` 为空时回退到 `LLM_MODEL`。密钥只从环境变量读取。

## 10. 明日实施顺序

1. 定义 Route Plan、`composite` 路由枚举和新版 Chat/Citation API 模型。
2. 实现 OpenAI-compatible LLM Provider，统一超时、结构化输出和错误映射。
3. 实现 Router Prompt、Schema 校验和一次修复重试。
4. 将 Retriever 扩展为按 Route Plan 执行一个或两个独立分区查询。
5. 实现证据分组、Answer LLM 和引用白名单校验。
6. 保留用户 `partition_hint` 和抽取式回答降级路径。
7. 导出 OpenAPI，重新生成前端类型并更新复合回答展示。
8. 更新健康检查，使 Router 和 Answer Provider 状态可见。

## 11. 代码健康验证

遵循项目根目录 `AGENTS.md`：

- 运行 Ruff、Python 编译和 `/chat` 定向单元/契约测试。
- 运行前端 TypeScript 构建和相关 Vitest。
- 使用 Fake LLM、Fake Index 和临时 SQLite 验证 single/composite/clarify 分支。
- 不运行批量 seed、路由全量评估、真实模型质量验收或 Playwright E2E。
- 不向现有 `data/` 写入验证文档、Chunk 或索引。

最小测试场景：

1. 用户指定分区时跳过 Router，只访问一个索引。
2. Router single 时只访问计划中的一个索引。
3. Router composite 时分别访问两个计划分区，其他索引调用次数为零。
4. Router clarify 时不访问索引。
5. 敏感输入阻断时不调用 Router、Answer 或索引。
6. Answer 引用未知 Chunk ID 时降级为不可回答。

## 12. 待确认事项

- OpenAI-compatible Provider 的实际 Base URL 和模型名称。
- Router 与 Answer 是否使用同一模型；默认支持分别配置。
- 当复合问题只有一个分区命中证据时，采用“部分回答并提示缺失”策略。
