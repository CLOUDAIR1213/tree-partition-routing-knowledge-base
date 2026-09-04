# 真实仿真知识内容构建与人工入库

> 文档状态：待用户上传  
> 最近核对：2026-09-03  
> 代码基线：当前工作树快照  
> 维护责任：知识库内容维护者；执行 Agent 可使用 `gpt-5.6-luna`

## 1. 功能说明

本任务为三分区知识库制作一套接近真实公司制度、但不包含任何真实企业或个人敏感信息的仿真业务资料。资料由 Agent 在仓库外显运行数据目录之外生成，由用户在前端逐个上传、检查 Chunk、确认分区并批准索引。

最终用户可围绕公司基础信息、财务、人事和技术制度进行自然语言单分区或双分区复合问答，并从引用中定位到对应文件和章节。新内容通过验证后，用户再另行决定是否备份并移除现有 seed/演示运行数据。

本文既是实施方案，也是交给其他 Agent 的完整任务书。执行者不应依赖聊天历史补全需求。

### 1.1 完成定义

以下条件全部满足才算内容制作完成：

1. 生成 10 个可直接上传的业务文件，其中 HR 4 个、Finance 3 个、Tech 3 个。
2. 包含 1 份公司详细基础资料，以及每个分区各 1 份新增补充文件。
3. 所有文件使用同一套公司事实、岗位、系统、金额、时限和版本关系，不存在互相矛盾的规则。
4. 主制度使用 DOCX，新增补充文件使用 Markdown；现有解析器能识别预期章节。
5. 生成事实矩阵、上传清单和自然语言验收问题，但不自动上传、不批准索引、不运行 seed。
6. 不修改 `data/raw`、`data/staging`、`data/indexes`、`data/metadata` 中的现有数据。

### 1.2 Luna 适配结论

`gpt-5.6-luna` 可以完成本任务的“文件生成和静态校验”部分。OpenAI 官方文档将 Luna 定位为适合目标明确、可重复、高吞吐的提取、分类、转换和结构化总结任务；本任务已有固定文件清单、事实基线和验收规则，符合这一定位。

建议使用 `gpt-5.6-luna`、`high` reasoning effort。不得让 Luna 自由重新设计公司制度、修改系统实现或清理运行数据。跨文件事实一致性和最终是否删除旧数据仍由人工把关。

官方依据：[Codex Models - Where each model shines](https://learn.chatgpt.com/docs/models#where-each-model-shines)。

## 2. 范围与非目标

| 类型 | 内容 |
| --- | --- |
| 包含 | 固定虚构公司事实；10 个可上传文件；三分区内容归属；事实矩阵；上传清单；自然语言单分区和复合验收问题；使用现有 Parser/Chunker 做只读静态检查 |
| 不包含 | 修改应用代码；修改 seed JSONL；运行 seed；调用上传或审核 API 写入数据；替用户点击上传；删除旧文档、SQLite、原文件或 txtai 索引；真实模型批量质量评测；真实企业数据迁移 |

### 2.1 运行数据与测试数据的边界

- 本任务替换的是将来展示给用户的知识库业务内容，不删除自动化测试需要的隔离 fixture。
- `data/fixtures/*.jsonl` 和 `tests/fixtures/` 可继续作为程序测试数据，不是本任务的上传源。
- 新生成的上传源文件统一放在计划新增目录 `deliverables/knowledge-upload/`。
- 只有用户通过界面上传并批准后，内容才进入 SQLite 和 txtai；把文件放进仓库目录不会自动入库。

## 3. 用户流程与状态

### 3.1 端到端流程

1. 执行 Agent 读取本文和本文引用的现行文档。
2. 执行 Agent 先生成事实矩阵，再根据矩阵编写 10 个文件。
3. 执行 Agent 对文件数量、格式、章节、禁用信息、事实重复和 Parser/Chunker 输出做静态检查。
4. 执行 Agent 只交付 `deliverables/knowledge-upload/`，不调用业务 API。
5. 用户逐个上传文件，选择本文规定的初始分区。
6. 系统解析文件并生成 Chunk，文档进入 `pending_review`。
7. 用户在详情/审核页按 `chunk_index` 检查标题、章节路径、顺序和正文。
8. 用户确认最终分区并批准；系统写入对应 txtai 索引并进入 `ready`。
9. 用户执行单分区和复合问题验收，检查路由、答案事实和引用。
10. 新数据全部通过后，用户另行授权备份与移除旧演示运行数据。

| 当前状态 | 操作或条件 | 下一状态 | 失败处理 |
| --- | --- | --- | --- |
| 计划中 | 事实矩阵通过静态一致性检查 | 内容生成中 | 修正事实归属，不开始写文件 |
| 内容生成中 | 10 个文件和配套清单完成 | 待静态验证 | 只修改源文件，不写运行数据 |
| 待静态验证 | 文件、章节和内容规则全部通过 | 待用户上传 | 失败文件退回修改并重新验证 |
| 待用户上传 | 用户通过 UI 上传单个文件 | `pending_review` | 按页面错误修复源文件后重新上传 |
| `pending_review` | 用户确认预览和最终分区 | `indexing` | 不符合预期时先拒绝或停止批准 |
| `indexing` | 索引写入和验证成功 | `ready` | 系统失败时保留错误状态，不直接改运行目录 |
| `ready` | 单分区与复合问答通过 | 可进入迁移决策 | 引用或事实不对时定位源文件并重新走接入流程 |
| 可进入迁移决策 | 用户明确授权备份和清理 | 旧演示数据已替换 | 无授权不得删除任何旧数据 |

## 4. 前端实现

本任务不修改前端。用户使用现有界面完成人工入库。

| 路径或组件 | 职责 | 关键状态或行为 |
| --- | --- | --- |
| `frontend/src/pages/UploadPage.tsx` | 单文件上传 | 用户选择文件、初始分区和标题；本任务不做批量上传 |
| `frontend/src/pages/ReviewPage.tsx` | 审核入口 | 查看预览、确认分区、批准或拒绝 |
| `frontend/src/pages/KnowledgeLibraryPage.tsx` | 知识库目录 | 当前工作树中的目录能力，用于查找上传文档和查看状态 |
| `frontend/src/components/ChunkPreviewList.tsx` | Chunk 展示 | 用户按原始 `chunk_index` 检查章节和正文 |

### 4.1 人工上传顺序

严格按以下顺序上传，便于发现基础事实冲突：

1. HR 的公司基础资料。
2. HR 两份主制度和 HR 补充文件。
3. Finance 两份主制度和 Finance 补充文件。
4. Tech 两份主制度和 Tech 补充文件。

每个文件批准为 `ready` 后再上传下一份。上传时标题使用文件内正式标题，不额外改成“测试”“示例”或“演示”。

## 5. 后端实现

本任务不修改后端，使用现有同步接入链路。

| 路径或服务 | 职责 | 上下游依赖 |
| --- | --- | --- |
| `app/api/documents.py` | 上传、列表、详情、预览和审核 API | Schema、IngestionService、ReviewService、SQLite |
| `app/services/ingestion.py` | 保存文件、解析、Chunking 和状态推进 | FileStorage、Parser、Chunker、ORM |
| `app/services/parser.py` | DOCX/Markdown 章节解析 | `python-docx`、文本解析 |
| `app/services/chunker.py` | 按章节和 Token 阈值生成稳定 Chunk | Chunk 配置、SHA-256 |
| `app/services/review.py` | 人工批准后写入分区索引 | SQLite、IndexRegistry |
| `app/services/index_registry.py` | Finance/HR/Tech 三个 txtai 索引 | txtai Embeddings、文件系统 |

### 5.1 文件编写对解析器的约束

- DOCX 必须真正使用 `Heading 1`、`Heading 2` 样式，不能只把普通段落加粗或放大。
- 重要事实使用标题下的普通段落和编号列表，不放在页眉、页脚、文本框、批注或图片中。
- 当前 DOCX Parser 会在处理完段落后再读取表格，表格可能被归到最后一个标题；关键制度事实不得只写在表格中。
- Markdown 使用 `#` 和 `##` 标题；不要用 HTML 标题替代 Markdown 标题。
- 不选 PDF 作为本轮主交付，因为当前按页而不是按语义标题解析。
- 不选 TXT 作为本轮主交付，因为当前整份 TXT 先作为单一 Section，再由 Chunker 切分。
- 当前 Chunk 默认目标 550 Token、最小 100、最大 700、重叠 75。每个二级章节建议 250～500 个中文字符，围绕一个完整事实主题。

## 6. 数据库与存储

| 存储类型 | 表、目录或索引 | 读/写 | 用途与一致性要求 |
| --- | --- | --- | --- |
| 待上传源文件 | `deliverables/knowledge-upload/` | 计划新增、读写 | 本任务唯一允许新增的业务内容交付目录；不会自动入库 |
| SQLite | `data/metadata/knowledge.db` | 本任务禁止写 | 用户上传后保存文档状态、分区和 Chunk 正文 |
| 原文件 | `data/raw/<document_id>/` | 本任务禁止写 | 只允许现有上传服务写入 |
| 解析快照 | `data/staging/<document_id>/parse.json` | 本任务禁止写 | 只允许现有接入服务写入 |
| txtai | `data/indexes/finance/` | 本任务禁止写 | 财务 `ready` 文档检索索引 |
| txtai | `data/indexes/hr/` | 本任务禁止写 | 人事 `ready` 文档检索索引 |
| txtai | `data/indexes/tech/` | 本任务禁止写 | 技术 `ready` 文档检索索引 |
| seed 源 | `data/fixtures/*.jsonl` | 本任务禁止改 | 自动化演示输入，不作为新业务上传包 |

SQLite、原文件、解析快照和 txtai 不构成同一事务。执行 Agent 只制作源文件，不负责跨存储一致性；用户通过现有审核流程触发系统自身的写入与补偿。

### 6.1 计划新增交付目录

```text
deliverables/knowledge-upload/
├── README.md
├── fact-matrix.md
├── upload-manifest.md
├── acceptance-questions.md
├── finance/
│   ├── 01-星澜公司财务组织与费用审批基础手册.docx
│   ├── 02-星澜公司差旅报销采购付款与发票管理制度.docx
│   └── 03-星澜公司财务补充通知-设备资产与培训费用.md
├── hr/
│   ├── 01-星澜数字科技有限公司基础资料.docx
│   ├── 02-星澜公司员工入职转岗离职与档案管理制度.docx
│   ├── 03-星澜公司考勤休假薪酬福利管理办法.docx
│   └── 04-星澜公司人事补充通知-培训认证与年度福利.md
└── tech/
    ├── 01-星澜公司技术平台与信息安全基础手册.docx
    ├── 02-星澜公司账号权限发布回滚与故障处理规范.docx
    └── 03-星澜公司技术补充通知-知识索引与RAG运维.md
```

`README.md`、`fact-matrix.md`、`upload-manifest.md` 和 `acceptance-questions.md` 是管理材料，不上传知识库。三个分区子目录中的 10 个文件才是上传对象。

## 7. API 接口

本任务的执行 Agent 不调用这些写接口；它们仅说明用户后续人工入库时系统如何处理文件。

| 方法 | 路径 | 用途 | 请求模型 | 响应模型 | 主要错误码 |
| --- | --- | --- | --- | --- | --- |
| `POST` | `/api/v1/documents` | 上传并解析一个文件 | multipart：`file`、`partition`、可选 `title` | `UploadDocumentResponse` | `DUPLICATE_DOCUMENT`、`UNSUPPORTED_FILE_TYPE`、`FILE_TOO_LARGE`、`EMPTY_DOCUMENT`、`DOCUMENT_PARSE_FAILED`、`INVALID_PARTITION` |
| `GET` | `/api/v1/documents` | 查看文档目录和筛选结果 | Query 参数 | `DocumentListResponse` | `VALIDATION_ERROR` |
| `GET` | `/api/v1/documents/{document_id}` | 查看文档详情 | Path 参数 | `DocumentDetailResponse` | `DOCUMENT_NOT_FOUND` |
| `GET` | `/api/v1/documents/{document_id}/preview` | 按顺序查看 Chunk | Path/Query 参数 | `ChunkPreviewResponse` | `DOCUMENT_NOT_FOUND` |
| `POST` | `/api/v1/documents/{document_id}/review` | 批准、拒绝和确认最终分区 | `ReviewRequest` | `ReviewResponse` | `DOCUMENT_NOT_FOUND`、`INVALID_DOCUMENT_STATE`、`INDEX_WRITE_FAILED` |

权威契约：`contracts/openapi.json`  
契约生成命令：`uv run --no-sync python -m scripts.export_openapi`

## 8. 文件路径与修改边界

| 文件或目录 | 职责 | 修改级别 | 修改要求 |
| --- | --- | --- | --- |
| `docs/features/realistic-knowledge-content.md` | 本任务事实、范围和验收标准 | `owned` | 需求变化时先更新本文，再生成内容 |
| `deliverables/knowledge-upload/` | 待上传源文件和配套清单 | `owned` | 计划新增；只能使用虚构内容，不得写真实凭据或个人信息 |
| `docs/README.md` | 文档导航和任务矩阵 | `shared` | 新增或移动本文时同步导航 |
| `app/services/parser.py`、`app/services/chunker.py` | 文件解析和 Chunking 行为 | `shared` | 本任务只读取，不修改；若必须改动需扩展为代码任务并补测试 |
| `contracts/openapi.json`、`frontend/src/api/generated.ts` | HTTP 契约和生成类型 | `generated` | 本任务禁止手工修改 |
| `data/raw/`、`data/staging/`、`data/indexes/`、`data/metadata/` | 当前运行期业务数据 | `runtime-data` | 内容制作和静态验证不得写入 |
| `data/fixtures/`、`tests/fixtures/` | seed 和自动化测试 fixture | `shared` | 本任务不修改；真实业务内容与隔离测试 fixture 分开维护 |
| 旧运行数据备份、删除、索引重建 | 迁移操作 | `approval-required` | 必须由用户另行明确授权具体范围和恢复方案 |

## 9. 核心不变量与安全约束

### 9.1 固定公司事实

除非用户先修改本文，执行 Agent 必须使用以下事实，不得自行替换：

| 事实项 | 固定值 |
| --- | --- |
| 公司全称 | 星澜数字科技有限公司 |
| 公司性质 | 完全虚构的企业软件与数据服务公司 |
| 成立日期 | 2019 年 4 月 18 日 |
| 统计基准日 | 2026 年 8 月 31 日 |
| 员工规模 | 180 人 |
| 总部 | 星河市高新技术产业园启明路 88 号 A 座，纯虚构地址 |
| 研发中心 | 云港市软件新城澄海路 16 号 3 号楼，纯虚构地址 |
| 核心业务 | 企业协同平台、数据分析平台、知识库解决方案 |
| 核心部门 | 总经理办公室、人力行政部、财务部、产品部、研发中心、交付与客户成功部、信息安全与运维组 |
| 财务系统 | AtlasFinance |
| 人事系统 | NovaHR |
| 协同与审批 | 星澜协同平台 |
| 代码与项目权限 | ForgeGit |
| 远程访问 | NebulaVPN |
| 知识检索 | OrionKB，底层使用三个独立 txtai 分区索引 |
| 对内联系渠道 | 星澜协同平台中的服务台或制度规定角色，不使用真实邮箱和电话 |
| 测试域名 | 仅允许使用 `.example` 后缀，例如 `portal.xinglan.example` |

### 9.2 事实归属

- 公司沿革、地点、组织、部门职责和员工规模：只以 HR 的公司基础资料为权威来源。
- 用工、入转调离、考勤、休假、薪酬周期、福利和培训资格：HR。
- 预算、报销、发票、采购付款、资产入账和培训费用报销：Finance。
- 系统环境、账号权限、VPN、发布、回滚、故障和知识索引运维：Tech。
- 跨分区流程只描述本分区责任和交接点，不复制另一个分区的完整规则。
- 补充通知只写变更项和新增项，不复制主制度全文。

### 9.3 内容真实性标准

- 文风应像正式内部制度，不出现“这是一份模拟数据”“仅供测试”“可以自行调整”等模板语句。
- 每条关键规则必须有明确角色、条件、步骤、时限、金额阈值、材料或异常升级路径中的至少两项。
- 不使用“及时”“相关人员”“按规定”“视情况”等无法检索和验证的模糊表述，除非同时给出明确解释。
- 公司基础资料建议 3,000～5,000 个中文字符；其他主制度 2,000～3,500 个；补充通知 1,000～1,800 个。
- 每个文件设置 5～8 个一级或二级语义章节；一个章节只表达一个主要主题。
- 不写与中国现行法律相冲突的内容；制度数据仅为虚构企业规则，不冒充法律意见。

### 9.4 隐私和安全

- 禁止真实姓名、身份证号、电话号码、邮箱、住址、客户名称、供应商账户、银行账号、税号和发票抬头识别码。
- 禁止密码、Token、API Key、私钥、内网 IP、生产 URL、数据库连接串和可用账号。
- 虚构姓名也不是必要信息，审批主体优先使用岗位名称。
- 不能引用当前 `.env`、运行日志、SQLite 内容或用户已上传文件来编写仿真资料。
- 每个文件只能归属一个分区；不能制作 Finance/HR/Tech 混合归属文档。

## 10. 错误处理与恢复

| 场景 | 对外表现 | 内部处理 | 恢复方式 |
| --- | --- | --- | --- |
| 文件数量、命名或分区不符合清单 | 静态验收失败 | 不上传 | 按 manifest 补齐或改名后重新检查 |
| DOCX 标题只是视觉格式 | 预览中 `section_path` 缺失 | 停止批准该文件 | 使用真实 Heading 样式重新生成并上传新文件 |
| 关键事实只存在于 DOCX 表格 | Chunk 顺序或章节归属异常 | 停止批准 | 将事实改为标题下普通段落，重新生成 |
| 两份文件包含冲突金额或时限 | 内容一致性失败 | 以 fact-matrix 的权威项为准 | 修改非权威文件，不能靠问答提示掩盖冲突 |
| 上传返回重复文档 | 页面显示 `DUPLICATE_DOCUMENT` | 不反复提交同一字节内容 | 在知识目录定位已有文档；需要替换时另行决定旧文档处理 |
| 解析或空正文失败 | 页面显示稳定错误码 | 文档可能进入 `failed` | 修复源文件后重新上传，不直接修改数据库 |
| 批准索引失败 | 文档进入 `failed` 或返回索引错误 | 系统执行现有补偿 | 保留错误信息，另开索引恢复任务 |
| 新旧知识回答冲突 | 引用可能命中演示文档 | 暂停最终验收 | 先记录冲突文档 ID，再由用户授权备份和清理范围 |
| 误生成真实敏感信息 | 内容审核失败 | 文件不得上传 | 删除敏感内容并重新生成；不得把文件放入运行目录 |

## 11. 测试与验证

### 11.1 Luna 必须执行的静态验证

| 层级 | 覆盖内容 | 文件或命令 |
| --- | --- | --- |
| 目录 | 10 个上传文件、4 个配套文件和分区数量 | PowerShell `Get-ChildItem deliverables/knowledge-upload -Recurse -File` |
| 格式 | DOCX 可打开，Markdown 为 UTF-8；文件小于 25 MB | 文件读取和扩展名检查 |
| 解析 | DOCX/Markdown 产生预期 Section、标题和顺序 | 只读调用 `app/services/parser.py`，不得调用 IngestionService |
| Chunk | 每份文件产生非空 Chunk，顺序连续，正文无模板占位 | 只读调用 `app/services/chunker.py`，不得保存索引 |
| 一致性 | 公司名称、系统名、角色、金额、期限和版本无冲突 | 对照 `fact-matrix.md` 逐项检查 |
| 安全 | 无真实个人信息、凭据、内网地址和生产标识 | 文本扫描加人工阅读 |
| 内容 | 每个要求的事实点可在唯一文件和章节中定位 | 对照 `upload-manifest.md` |

静态验证不得启动上传、审核、seed、真实 txtai 写入或模型批量问答。验证产生的临时文件应使用临时目录并在验证生命周期结束时删除。

### 11.2 文件级验收要求

#### HR：4 个文件

| 文件 | 必须包含的章节和事实 |
| --- | --- |
| `01-星澜数字科技有限公司基础资料.docx` | 公司沿革与业务；总部和研发中心；组织架构；部门职责；管理角色；180 人规模；内部系统地图；对内服务渠道；资料版本 |
| `02-星澜公司员工入职转岗离职与档案管理制度.docx` | 入职材料；试用期与转正；调岗申请；离职提前期；工作和资产交接；HR/财务/技术交接边界；证明与档案；异常升级 |
| `03-星澜公司考勤休假薪酬福利管理办法.docx` | 工作时间；迟到和补卡；年假与病事假；加班调休；薪酬发放周期；餐饮通讯健康福利；停发条件；异常申诉 |
| `04-星澜公司人事补充通知-培训认证与年度福利.md` | 被补充文件；发布日期和生效日；培训资格；认证登记；年度福利新增项；HR 审批角色；过渡期；冲突优先级 |

#### Finance：3 个文件

| 文件 | 必须包含的章节和事实 |
| --- | --- |
| `01-星澜公司财务组织与费用审批基础手册.docx` | 财务角色；成本中心；年度预算；临时追加；费用审批层级；付款批次；报销时限；超预算和紧急例外 |
| `02-星澜公司差旅报销采购付款与发票管理制度.docx` | 出差事前申请；交通和住宿标准；报销材料；发票要求；采购验收；付款审批；异常发票；超标处理 |
| `03-星澜公司财务补充通知-设备资产与培训费用.md` | 被补充文件；设备资本化阈值；资产编号和领用；培训/考试费用范围；事前审批；报销材料；离职交接接口；生效与过渡 |

#### Tech：3 个文件

| 文件 | 必须包含的章节和事实 |
| --- | --- |
| `01-星澜公司技术平台与信息安全基础手册.docx` | 系统地图；生产/预发布/测试环境；账号身份；最小权限；设备安全；数据分级；事件等级；服务台和升级角色 |
| `02-星澜公司账号权限发布回滚与故障处理规范.docx` | ForgeGit 权限；NebulaVPN；入转离权限联动；发布窗口；发布前检查；回滚条件；Docker/502 排查；紧急变更与复盘 |
| `03-星澜公司技术补充通知-知识索引与RAG运维.md` | 被补充文件；OrionKB 三分区；上传审核职责；txtai 写入和保存；SQLite 权威校验；失败补偿；索引巡检；生效和升级路径 |

### 11.3 配套材料验收

`fact-matrix.md` 至少记录：事实 ID、主题、固定值、权威分区、权威文件、权威章节、允许引用文件和禁止重复位置。

`upload-manifest.md` 每个上传文件至少记录：顺序、文件名、标题、分区、格式、版本、生效日期、字符数、预期 Section 数、预期 Chunk 数区间和主要事实点。

`acceptance-questions.md` 至少包含：

- 9 条自然语言单分区问题，每个分区 3 条。
- 6 条自然语言双分区复合问题，Finance+HR、Finance+Tech、HR+Tech 各 2 条。
- 6 条手动指定分区问题，每个分区 2 条；问题正文保持自然表达，执行时通过管理字段设置 `partition_hint`，并验证只检索该分区。
- 1 条最后执行的联网兜底问题：用户问题固定为“Python 装饰器是什么？”，管理字段设置 `partition_hint=tech` 和 `allow_web_fallback=true`。
- 问题正文不得出现“请路由到 finance/hr/tech”“分区”等测试指令。
- 每题在管理字段中记录预期路由、目标文件、目标章节和必须覆盖的事实点；这些管理字段不拼进用户问题。
- 复合问题必须来自一个合理业务场景，而不是把两个无关问题用“以及”硬拼接。

### 11.4 用户上传后的验收

以下步骤由用户执行，不属于 Luna 的自动执行范围：

1. 检查文档状态从 `pending_review` 到 `ready`。
2. 检查详情页 Chunk 序号连续，标题和章节路径符合 manifest。
3. 逐题执行 9 条单分区问题，确认路由和引用。
4. 逐题执行 6 条复合问题，确认最多检索两个正确分区。
5. 逐题执行 6 条手动指定分区问题，确认只检索 `partition_hint` 指定的分区。
6. 最后执行 1 条联网兜底问题；只有内部零证据且 Provider 返回公开 HTTPS 来源时，才记录为联网成功。
7. 检查回答中的关键事实均可由引用 Chunk 直接支持。
8. 记录旧演示文档造成的冲突，但在获得清理授权前不删除。

### 11.5 本文档任务实际验证记录

- 已核对现有 Parser/Chunker 支持 DOCX Heading 和 Markdown 标题。
- 已核对当前默认 Chunk 参数为 550/100/700/75。
- 已核对上传、详情、预览和审核 API 已存在于当前工作树及 OpenAPI。
- 已生成 10 个业务文件和 4 个管理 Markdown，位于 `deliverables/knowledge-upload/`；HR 4 个、Finance 3 个、Tech 3 个。
- 已使用现有 `StandardDocumentParser` 和 `SectionChunker(550, 100, 700, 75)` 做只读验证：10/10 文件解析通过，Section 顺序有效，Chunk 序号连续，合计 71 个 Chunk，字符数合计 16,511。
- 已完成文件扩展名、大小、固定事实、章节要求和敏感信息扫描；未发现实际个人信息、凭据、私钥、内网 IP 或生产 URL。
- DOCX 结构审计已通过；当前环境未找到 LibreOffice/`soffice`，因此无法完成 `render_docx.py` 的 PNG 视觉检查，不能将视觉渲染标记为通过。
- 未运行测试、seed、上传、审核、真实 txtai 写入或模型批量问答；未修改 `data/raw`、`data/staging`、`data/indexes`、`data/metadata`。

## 12. 已知限制与后续计划

- 当前系统已有单文档删除、改分区和重新审核 API；仍没有普通失败重试、重新解析和完整索引重建 API。
- 当前没有认证和分区级权限，仿真文件也只应上传到可信本地环境。
- 当前 DOCX 表格语义位置解析有限，因此本轮关键事实以段落为主。
- 当前生产 IndexRegistry 已逐个验证全部 Chunk ID；真实大文档的验证性能仍需观测。
- 新旧文档并存期间可能发生检索冲突。清理前需设计 SQLite、原文件、staging 和三个索引的一致备份/恢复方案。
- 10 个文件生成和静态验证已完成，当前状态为“待用户上传”；只有用户完成上传、审核、单分区、双分区、手动指定分区和联网兜底聚焦验收后，才能更新为“已实现”。

## 13. 交给 Luna 的执行指令

将本文作为 Luna 任务上下文，并使用以下指令：

```text
按照 docs/features/realistic-knowledge-content.md 完成真实感仿真知识内容制作。

先遵守 AGENTS.md 的文档优先工作流，阅读本文引用的文档和当前 Parser/Chunker 实现。使用 gpt-5.6-luna，建议 high reasoning effort。

只在 deliverables/knowledge-upload/ 下创建本文规定的 10 个上传文件和 4 个配套 Markdown 文件。先完成 fact-matrix.md，再写业务文件。DOCX 必须使用真实 Heading 1/2 样式，关键事实使用普通段落，不依赖表格。所有业务事实必须符合本文固定公司事实和唯一权威归属。

完成后使用现有 Parser 和 Chunker 做只读静态验证，并把实际文件数、字符数、Section 数、Chunk 数和发现的问题记录到 deliverables/knowledge-upload/README.md。不得调用上传或审核 API，不得运行 seed，不得修改 data/fixtures 或 tests/fixtures，不得写入或删除 data/raw、data/staging、data/indexes、data/metadata，不得清理现有知识库。

最终报告列出创建的文件、静态验证结果、仍需用户人工上传和确认的事项。发现当前代码或文档与本文冲突时先报告，不要扩大到应用代码修改。
```
