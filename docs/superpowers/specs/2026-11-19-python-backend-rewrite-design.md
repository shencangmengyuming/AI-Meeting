# Python 后端重构设计

## 1. 设计结论

本项目采用“独立 Python 模块化单体”方案。`AI-Meeting-backend` 独立启动、部署、鉴权、存储运行态和维护 Skill，不依赖 Java 服务在线，也不读写 Java Sa-Token 会话协议。

Java 当前实现事实、接口例外和历史业务规则保存在 [Java 后端模块基线](../../reference/java-backend-module-baseline.md)。Java 只用于回答“原业务为什么这样做”，不是 Python 的运行时、存储协议或目录结构真相源。

Python 对外接口按当前前端需求保持必要兼容；内部模型、Token、Redis Key、配置和部署全部由 Python 自主管理。对 Java 行为的复用必须通过明确的业务规则或测试体现，禁止通过跨服务调用、共享 Session 序列化或双写实现。

最终目标不是拆分微服务，而是先形成边界清晰的 Python 模块化单体；只有在真实负载和团队边界证明需要时，再拆分独立服务。

### 1.1 实施状态

截至 2026-11-19：Foundation 已完成；Auth/User 和 Interview 为部分完成；AI/Agent 与 Media 尚未开始。详细状态以 [实施路线图](../plans/2026-11-19-python-backend-rewrite-roadmap.md) 为准。

## 2. 目标与非目标

### 2.1 目标

- 保持当前前端依赖的 API 路径、字段和交互语义兼容。
- 迁移用户、AI 对话、Agent、模拟面试、媒体能力和长会话状态治理。
- 保留并强化分布式 Single-flight、Session Heavy Lock、心跳、Fencing Token、本地降级和状态恢复能力。
- 保持 Redis、MongoDB、MySQL 的职责分层，由 Python 定义并版本化自己的 Key 和文档协议。
- 为每个 Python 模块提供 API 契约、并发、恢复和回归测试。

### 2.2 非目标

- 第一阶段不重新设计前端接口。
- 第一阶段不把项目拆为多个 Python 微服务。
- 不把 Redis 当成长会话唯一事实来源。
- 不用一个通用锁替代 Heavy Lock、Single-flight 和 CAS。
- 不把第三方 AI 调用散落在业务模块中。

## 3. 目标架构

```text
前端
  -> Python FastAPI

Python 模块化单体
  ├── API 适配层
  ├── 应用服务层
  ├── 面试领域模块
  ├── Single-flight / Lock / Runtime 基础设施
  ├── AI / Media Provider 适配器
  └── MySQL / MongoDB / Redis Repository
```

Python 进程保持尽量无状态。进程内内存只用于 Local Single-flight、刷新 Bucket 和短期调度；跨进程必须共享的状态放在 Redis 或 MongoDB。

## 4. Python 技术栈

| 能力 | 选型 |
| --- | --- |
| HTTP、SSE、WebSocket | FastAPI + Uvicorn |
| 请求/响应模型 | Pydantic v2 |
| 配置 | pydantic-settings |
| MySQL | SQLAlchemy 2.x Async + asyncmy |
| 数据库迁移 | Alembic |
| MongoDB | PyMongo Async（或项目已验证的 Motor 兼容方案） |
| Redis | redis-py asyncio + Lua |
| HTTP/AI 调用 | httpx.AsyncClient |
| 重试/超时 | tenacity + asyncio timeout |
| 密码/Token | pwdlib/Argon2 + JWT |
| 后台任务 | arq + Redis |
| 日志/指标 | structlog + OpenTelemetry/Prometheus |
| 测试 | pytest、pytest-asyncio、httpx、testcontainers |

## 5. API 适配层设计

### 5.1 API 契约

实现接口前，根据当前前端调用和已确认的 Java 业务基线建立契约清单：

```text
HTTP method / path
headers / token 传递
query / path / multipart / JSON 字段
响应字段、类型、null 和空集合行为
状态码、错误码、错误消息结构
SSE event/data 格式
WebSocket 路径、首包、心跳、错误和断开语义
```

Python 内部使用 snake_case，Pydantic 通过 alias 保持前端需要的 camelCase 输出。契约测试直接验证 Python 的状态码、字段结构、类型和关键业务结果；Java 录制结果只可作为一次性的历史参考夹具。

### 5.2 统一入口

```text
app/api/router.py                    # 只聚合领域 Router
app/auth_user/api/                   # 认证与用户接口
app/interview/api/                   # 面试接口
app/ai_agent/api/                    # AI/Agent 接口（待实现）
app/media/api/                       # TTS/ASR/WebSocket（待实现）
```

Router 只负责参数解析、鉴权、依赖注入和响应适配，不直接调用 Redis、Mongo、AI Provider 或状态机。

### 5.3 经审阅确认的授权加固

兼容原则不要求复制已经确认的越权风险。以下接口保持路径、字段和成功响应不变，但 Python 版增加授权约束：

- AI/Agent 配置管理要求管理员角色，响应不得返回原始 `apiSecret`，API Key 只允许掩码显示。
- 用户分页要求管理员；用户详情只允许本人或管理员。
- 服务端 WebSocket 主动推送要求管理员。
- Agent 文件上传携带 `sessionId` 时必须校验 Session 归属。

这些属于显式安全差异，必须分别提供授权成功、401/403 和前端管理员流程测试，不能混入普通契约差异后静默上线。

## 6. 领域和模块边界

```text
app/
├── main.py
├── api/                          # 顶层 Router 聚合
├── core/                         # 配置、异常、生命周期、统一响应
├── infrastructure/              # 共享 MySQL/Mongo/Redis/HTTP 客户端
├── auth_user/                    # api/application/domain/infrastructure
├── interview/                    # api/application/domain/infrastructure
├── ai_agent/                    # 规划中的 AI/Agent 领域模块
├── ai_runtime/                  # 规划中的 Guard/Lock/Single-flight
├── media/                       # 规划中的 TTS/ASR/WebSocket 模块
└── workers/
```

每个深模块通过小接口隐藏复杂实现。业务层依赖 `ChatProvider`、`WorkflowProvider`、`RuntimeRepository`、`DistributedSingleFlight` 等接口，不依赖具体 Redis 客户端或讯飞 HTTP 细节。

### 6.1 用户注册和认证

用户名可用性与注册一致性分为三层：

```text
Bloom Filter：负向快筛，减少随机用户名查询穿透
username 分布式锁：串行化同用户名并发注册
MySQL 唯一索引：最终真相和一致性兜底
```

Python 版保持 `/users/has-username` 的现有布尔语义，即 `true` 表示可注册。与 Java 当前实现相比，Bloom 命中后增加 MySQL 复核，避免误判导致合法用户名永久不可注册；Bloom 未命中可直接返回可注册，但正式注册仍必须在锁内依赖数据库唯一索引裁决。

注册链路为：

```text
Bloom 快筛
  -> username 维度分布式锁
  -> 锁内数据库检查/插入
  -> 事务提交
  -> Bloom add
```

Redis/Bloom 故障时降级查询 MySQL，不允许因防穿透设施异常而破坏数据库最终一致性。系统提供从 MySQL 分批重建 Bloom 的管理任务。Python 使用自己版本化的 Bloom Key，不读取 Redisson Bloom 位图。

认证由 Python 独立拥有。对外使用 `Authorization: Bearer <token>`，Session 存储在 `ai-meeting:auth:*` Key 空间；不读取或写入 Java Sa-Token Key。旧密码数据允许兼容读取并在成功登录后升级，但 Token 生命周期只由 Python 管理。

## 7. AI Provider 设计

普通聊天和工作流调用统一抽象，具体适配器隔离供应商：

```python
class ChatProvider(Protocol):
    async def chat(self, messages, model, stream=False, **kwargs): ...

class WorkflowProvider(Protocol):
    async def run(self, workflow_id, inputs, **kwargs): ...

class AsrProvider(Protocol): ...
class TtsProvider(Protocol): ...
```

实现包括：

```text
DeepSeekProvider
OpenAICompatibleProvider
XunfeiWorkflowProvider
XunfeiAsrProvider
XunfeiTtsProvider
```

所有 Provider 统一处理超时、重试、错误转换、限流、Trace ID 和响应解析。密钥只来自环境变量或密钥管理服务，不复制 Java 源码/SQL 中的明文密钥。

## 8. 分布式 Single-flight

### 8.1 语义

Single-flight 解决“正在执行中的同语义请求去重”，不是普通缓存。相同 Key 只有一个 Owner 真正调用 AI，Follower 等待并复用结果。

Stage 固定为：

```text
interview-evaluation
interview-followup
interview-extraction
interview-demeanor
```

### 8.2 Key

问答类：

```text
{stage}|{sessionId}|{businessPart}|{sha256(trim(answer))[:16]}
```

文件/对象类：

```text
{stage}|{sessionId}|{businessKey}
```

Python 首个稳定格式定义为 v1；后续如需对 URL、特殊字符或隐私进行哈希，使用显式 `v2` Key，禁止静默改变已发布协议。

### 8.3 Redis 协议

```text
ai:flight:meta:{requestKey}
ai:flight:result:{requestKey}
ai:flight:owner-seq
ai:flight:stream:{requestKey}
```

`meta` 是状态机真相，`result` 是结果真相，`owner-seq` 生成单调递增 Fencing Token，`stream` 只负责终态通知，不能作为结果真相。

### 8.4 状态与 Action

```text
Status: PENDING / RUNNING / SUCCEEDED / FAILED / CANCELLED / EXPIRED
Action: OWNER_NEW / OWNER_TAKEOVER / FOLLOWER_WAIT /
        REPLAY_SUCCESS / REPLAY_FAILURE
```

Lua 原子完成状态判断、Owner 抢占、Token 分配和状态写入。所有 heartbeat、progress、success、failure 写操作都必须携带并校验 `ownerToken`，拒绝旧 Owner 的迟到写入。

### 8.4.1 `acquire-or-join` 原子裁决

请求进入 Single-flight 时，不允许在应用层执行“先读状态、再判断、再写回”的多步流程。Python 版使用 Redis Lua 脚本一次完成读取、裁决、抢占、follower 计数、TTL 更新和 Fencing Token 分配，避免并发竞态。

脚本使用两个 Key：

```text
KEYS[1] = ai:flight:meta:{requestKey}
KEYS[2] = ai:flight:owner-seq
```

主要分支和返回协议如下：

| Redis 状态 | 裁决 | 返回值 |
| --- | --- | --- |
| 不存在 | 当前请求成为首任 Owner，写入 `PENDING` | `OWNER_NEW|{ownerToken}` |
| `SUCCEEDED` | 不再调用 AI，直接回放结果 | `REPLAY_SUCCESS|SUCCEEDED` |
| `FAILED` 且 `retryable=1` | 新 Owner 接管重试 | `OWNER_TAKEOVER|{ownerToken}` |
| `FAILED` 且 `retryable=0` | 回放不可重试失败语义 | `REPLAY_FAILURE|0|{errorType}|{errorCode}` |
| `CANCELLED` / `EXPIRED` | 按状态层可重试失败返回 | `REPLAY_FAILURE|1|{status}|STATE` |
| Owner heartbeat 在检测窗口内 | 当前请求成为 Follower | `FOLLOWER_WAIT|{ownerToken}` |
| Owner heartbeat 超过检测窗口 | 新 Owner 接管 | `OWNER_TAKEOVER|{ownerToken}` |

首任 Owner 或接管 Owner 都必须获得全局递增 Token，并将 `ownerId`、`ownerToken`、`stage`、`requestKey`、`sessionId`、时间戳和 TTL 一起写入 `meta`。Follower 分支递增 `followerCount`，用于观测等待规模；该计数不参与业务裁决。

Lua 返回的是“动作 + 附加字段”的紧凑协议，Python 端只负责解析协议并选择后续路径：

```text
OWNER_*       -> 执行 AI，并以 ownerToken fencing
FOLLOWER_WAIT -> 按退避/通知等待终态，再读取 result
REPLAY_SUCCESS-> 读取并校验 result 后回放
REPLAY_FAILURE-> 按 retryable 和错误语义返回或重新尝试
```

`CANCELLED`、`EXPIRED` 表示协调状态失效，不等同于参数或供应商硬失败；它们允许后续请求接管。不可重试失败则必须原样保留 `errorType/errorCode`，避免上层只得到一个无意义的“失败”。

### 8.4.2 结果对象序列化与回放

`meta` 只保存协调状态，完整 AI 结果单独存放在 `ai:flight:result:{requestKey}`。结果对象采用版本化序列化协议，至少包含：

```text
schemaVersion
requestKey
stage
status
ownerToken
provider
payload
errorType/errorCode（失败时）
createdAt/updatedAt
```

写入 Redis 前对规范化后的 JSON 字节执行 GZIP 压缩，并计算 SHA-256 摘要；读取回放时按“读取 -> 解压 -> 摘要校验 -> 反序列化 -> schema 校验”的顺序处理。摘要不匹配、版本不支持或 payload 损坏时，必须视为结果不可回放并告警，不能静默重新调用 AI。

结果写入同样受 Fencing Token 保护：只有当前 Owner 且 Token 匹配时，才能写入成功/失败结果并将 `meta.status` 收口为终态。旧 Owner 的迟到完成、失败或 heartbeat 均必须被拒绝。

### 8.5 Heartbeat、进度和降级

Owner 使用 `requestKey|ownerToken` 作为本地 heartbeat 任务键。续租条件必须同时满足：

```text
heartbeat 存活 AND now - lastProgressAt <= maxNoProgress
```

非流式 AI 调用使用客户端超时和最大执行时长；流式调用可按 chunk 更新进度。Redis 协调失败时，HYBRID 模式回退 `LocalSingleFlight`；分布式异常和 AI 业务异常必须区分，避免未知结果被重复调用。

### 8.6 Heavy Lock

抽题和神态分析先获取：

```text
interview:ai:heavy:lock:{stage}:{sessionId}
```

它保护上传、解析、结构化处理和落库等整条重任务入口，快速失败，不负责结果复用。Single-flight 负责后续精确 AI 请求去重，两者保持职责分离。

## 9. 长会话运行态

### 9.1 四层存储

```text
Redis：在线热工作集
Mongo Hot Snapshot：高频推进恢复检查点
Mongo Cold Snapshot：题目、简历、方向、评分等低频材料底座
Mongo Turn Archive：已提交轮次历史、顺序和 requestId 依据
```

`InterviewTurnLog` 是一次成功提交后的结构化业务轮次，不是消息。Redis 保存近期窗口，Mongo Archive 保存正式账本。

### 9.2 ensureRuntime

```python
ensure_runtime(session_id, load_mode, scope)
```

三个参数分别表示：

```text
loadMode：READ_ONLY / READ_WRITE_REQUIRED，调用要求
scope：FLOW_ONLY / SCORE_ONLY / PLAYBACK_ONLY / MATERIAL_ONLY /
       HOT_RUNTIME / FULL_RUNTIME，恢复范围
confidence：EXACT / DERIVED / READ_ONLY / TERMINAL，实际结果
```

流程为：检查 Redis ready；未 ready 时竞争 session 级恢复锁；只有一个请求从 Snapshot/Archive 重建并回填 Redis；其他请求等待或重检。`READ_WRITE_REQUIRED` 下，`READ_ONLY` 结果不能继续推进业务。

### 9.3 快照更新

业务事件只产生刷新意图：

```text
QUESTION_READY
DEMEANOR_READY
ANSWER_COMMITTED
FINALIZED
```

`HotRefreshRequest` 是意图对象，`Trigger` 是业务事件到刷新策略的规则表，`HotRefreshCoordinator` 按 session Bucket 做合并、防抖、强刷和失败重调度。

真正的 `refreshSnapshot` 流程：

```text
读取当前 hot/cold snapshot
  -> 从 cache/entity/archive 补齐材料、turn、flow、score
  -> 必要时写 Turn Archive
  -> 生成 HotPatch / ColdPatch
  -> 等价检查、mutation 幂等检查、单调性校验
  -> Hot Snapshot CAS
  -> 按需写 Cold Snapshot
```

Hot Snapshot 使用版本 CAS，至少保护 `snapshotVersion`、`lastTurnSeq`、`archiveWatermark` 和 `scoreCount` 不倒退。失败请求进入幂等补偿，不重复推进业务。

## 10. 代表性链路：神态分析

```text
POST /sessions/{sessionId}/demeanor-evaluation
  -> API 参数和会话校验
  -> Session Heavy Lock
  -> 上传图片到 Xunfei，获得 imageUrl
  -> 构造 interview-demeanor|sessionId|imageUrl
  -> ResilientSingleFlight
  -> Owner heartbeat / mark progress
  -> AiCallGuard（超时、重试、熔断、指标）
  -> Xunfei Workflow chat
  -> 写 flight result/meta，通知 follower
  -> 解析和归一化神态评分
  -> refreshAfterDemeanorEvaluated
  -> finally 释放 Heavy Lock
```

只有 Owner 执行真实 AI Supplier，Follower 不重复进入 AI Guard。在兼容层、认证和存储 Adapter 等基础批次完成后，该链路作为第一条涉及 AI Guard 的完整业务纵向切片，用于验证 API、文件上传、锁、Single-flight、Provider、缓存和快照更新的组合。

## 11. 答题主链路

答题接口保持前端仍使用的入口和响应契约：

```text
POST /api/xunzhi/v1/interview/sessions/{sessionId}/interview/answer
POST /api/xunzhi/v1/interview/sessions/{sessionId}/interview/answer-json
```

Python 版使用 `InterviewAnswerPipeline` 收口完整答题流程：

```text
Controller
  -> SessionFacade：用户归属、会话状态和生命周期门禁
  -> Workflow/Orchestration：能力分发
  -> AnswerPipeline
      -> 参数校验与 requestId 归一化
      -> 幂等门禁
      -> ensureRuntime(READ_WRITE_REQUIRED, HOT_RUNTIME)
      -> 当前题校验
      -> sessionId + questionNumber 题级锁
      -> 锁后再次校验题号
      -> 评分 Agent
      -> 评分结果归一化
      -> 规则链裁决是否追问
      -> 追问 Agent 或主问题推进
      -> 成功提交分数、Turn 和幂等结果
      -> refreshAfterAnswerCommitted
```

答题链路不能直接由 Router 调 AI。每一步都需要明确前置条件、失败语义、是否可重试和是否需要补偿。

### 11.1 幂等协议

一次答题成功可能同时产生评分、追问、流程推进、加分、Turn 和快照变化，因此 `requestId` 是一次 mutation 的身份，而不是普通日志字段。

```text
replay key：已成功响应
processing key：正在处理
```

`try_start(session_id, request_id)` 的语义：

```text
REPLAY_EXISTS -> 直接回放，不调 AI
PROCESSING    -> 快速返回处理中
NEW           -> 先查 Snapshot/Archive 兜底回放，确认没有历史响应后才执行
```

Python 版必须保留“NEW 后再次查 Snapshot/Archive”的防御逻辑：Redis replay key 可能过期或丢失，但持久化 Turn/Snapshot 仍能证明该 mutation 已经成功。发现历史响应后，应重建响应并补写 replay key，不能重新评分或重复加分。

处理成功后写入 replay、删除 processing；异常时清理 processing，使明确失败的请求可以按原语义重试。对于结果未知的外部 AI 调用，不得仅凭 processing 过期就盲目重试，应先查询 Runtime/Archive/Single-flight 状态。

### 11.2 一致性边界

- 分数不能在评分返回后立即入账，必须等追问裁决、流程推进和响应组装成功。
- 追问轮不重复计入主问题分数。
- 题级锁用于串行化同一题提交；锁前校验用于快速拒绝，锁后校验用于拒绝等待期间已经过期的题号。
- AI 只提供追问建议，规则链决定最终是否追问；追问 Agent 失败时可使用评分结果中的追问建议兜底。
- Turn、replay 和 Snapshot 属于成功收尾材料，附属写入失败进入幂等补偿，不能重新执行整个答题流程。

### 11.3 当前题装载与 stale question

`step_load_current_question` 是调用评分 Agent 前的运行态闸门：

```text
ensureRuntime(READ_WRITE_REQUIRED, HOT_RUNTIME)
  -> 读取或初始化 Flow
  -> 已完成/越界则返回成功终态
  -> 解析当前题号
  -> 缓存读取题目，主问题 miss 时从 MySQL 回补
  -> 识别追问题和追问次数
  -> 校验请求题号仍等于当前题号
```

题级锁前后都要校验题号。锁前校验用于快速拒绝；等待锁期间其他请求可能已经推进题目，因此锁后必须重新读取 Flow，拒绝 stale question。`return false` 既可能表示失败，也可能表示已经生成完成态响应并停止后续 Pipeline。

### 11.4 Flow 状态机

Python 使用 `Enum` + 合法迁移表表达流程约束，替代散落的条件分支：

```text
INIT -> ASKING
ASKING -> EVALUATING
EVALUATING -> FOLLOW_UP / ASKING / COMPLETED
FOLLOW_UP -> EVALUATING / ASKING / COMPLETED
COMPLETED -> 无迁移
```

`InterviewFlowState` 不仅保存状态，还保存 `current_index`、`current_question_number`、`total_questions`、`follow_up_count`、`max_follow_up` 和 `version`。状态机负责判断“能否迁移”，Pipeline 负责决定“何时调用迁移”。跨节点写入需要 Redis Lua/CAS，不能依赖单进程内存。

### 11.5 追问规则链

LiteFlow 的职责仅是评分后的追问裁决，不驱动整个答题主链路。Python 版使用可配置 `RuleChain`，节点顺序保持：

```text
load_context
  -> completed_state_guard
  -> followup_limit_guard
  -> ai_suggestion_judge
  -> low_score_judge
  -> missing_points_judge
  -> finalize_decision
```

规则上下文包含评分、遗漏点、AI 建议、当前/最大追问次数和完成态；输出 `need_follow_up/reason_code/reason_text`。状态机随后负责验证能否进入 `FOLLOW_UP`，或推进主问题。

### 11.6 Agent 场景解析与替换

业务只依赖 `BusinessAgentScene`（评分、追问、出题、神态等能力），不写死 Agent 名称、Flow ID 或密钥。解析顺序为：

```text
场景配置绑定名
  -> 默认名称/别名
  -> Agent 配置缓存
  -> MySQL fallback
  -> apiKey/apiSecret/apiFlowId
  -> WorkflowProvider
```

第一阶段定义为“代码层热插拔/半热更新”：替换 Agent 不改业务 Pipeline，但配置或已缓存配置变更通常需要刷新或重启。后续可通过配置版本、Redis 失效事件或主动 reload 实现真正热更新。

## 12. 实时 ASR 媒体链路

实时语音转写采用两条 WebSocket 通道，不把前端音频直接透传给讯飞：

```text
前端 WebSocket
  -> AudioTranscriptionHandler
  -> TranscriptionSessionContext / bounded asyncio.Queue
  -> Xunfei ASR WebSocket
  -> AstTranscriptionAssembler
  -> RealtimeTranscriptionUpdate
  -> 前端 WebSocket
```

Python 会话上下文至少保存：

```text
session_id / user_id
audio_queue
active / stop_requested
last_update
sender_task / receiver_task / heartbeat_task
```

有界 `asyncio.Queue` 替代 Java Pipe，负责前端音频接收与供应商推流之间的解耦，并提供明确的队列上限和背压策略。阻塞型供应商 SDK 不得直接阻塞事件循环。

`start_transcription` 创建上下文；二进制帧写入队列；推流任务按讯飞要求的节奏和分片发送；`stop_transcription` 设置主动停止标记并取消/关闭相关任务。`final` 只表示供应商自然完成，主动停止按现有协议返回 `transcription_stopped`，不强制补发 `final`。

### 12.1 AST 分段装配

`AstTranscriptionAssembler` 维护 `segment_id -> SegmentState` 的有序分段池，而不是直接拼接字符串。

```text
pgs=apd：按 segment_id 更新当前分段
pgs=rpl：按 rg 删除范围，再 upsert 新分段
其他/缺失：按时间范围、重叠比例和文本相似度保守推断
```

无 `pgs` 时优先复用“同一句演化”的旧分段，只有证据不足才新建；删除旧段必须满足明确覆盖条件，避免前缀误删。纯标点同范围包追加到已有段尾部。

`finalized` 是分段稳定性状态，不是整场会话终态。一旦为 true 不得被后续中间包降级。组装器输出 `fullText/displayText`、`committedText`、`liveText`、`revision` 和 `partial/final` 状态。

## 13. 实施顺序

1. 固化当前前端所需的 API/SSE/WebSocket 契约。
2. 建立 FastAPI、配置、异常、日志、健康检查和测试骨架。
3. 接入 MySQL、MongoDB、Redis，定义 Python 自有 Key/文档协议。
4. 迁移认证、用户、角色和 Token。
5. 迁移 Provider 抽象与普通 AI 聊天。
6. 迁移 Local/Distributed/Resilient Single-flight、Heavy Lock 和 AI Guard。
7. 迁移 Hot/Cold/Turn Runtime 与 `ensureRuntime`、Snapshot 更新。
8. 迁移简历抽题、神态分析等重任务纵向链路。
9. 迁移答题幂等、Turn、评分、追问和报告流程。
10. 迁移 WebSocket ASR、TTS 和媒体任务。
11. 完成独立部署、数据备份恢复、负载与故障演练。
12. 由 Python 回归测试和运行指标完成发布验收。

状态机主链路放在后期实现，依赖前述 Runtime、幂等、Single-flight、快照和 Provider 能力。

## 14. 验证标准

- Python API 对前端契约的请求/响应测试。
- Redis Key、TTL、Lua Action 和状态转移测试。
- Owner takeover、旧 Token 脏写拒绝测试。
- heartbeat 失效、业务进度超时和本地降级测试。
- Heavy Lock 快速失败和 TTL 边界测试。
- `ensureRuntime` 并发恢复只允许一个 Owner。
- Hot Snapshot CAS 冲突、单调性和幂等重试测试。
- Turn Archive 顺序、requestId 回放和 Redis 丢失恢复测试。
- SSE/WebSocket 时序和断线恢复测试。
- 神态分析完整链路回归测试。
- 答题 requestId 的 `REPLAY_EXISTS / PROCESSING / NEW` 分支测试。
- Redis replay 丢失时从 Snapshot/Turn Archive 回放并补写测试。
- 同题并发提交、锁后 stale question 和分数只入账一次测试。
- AST `apd/rpl/unknown/no-pgs`、finalized、前缀保留和最终收口测试。
- ASR 队列背压、主动停止、自然 final、断开清理和任务取消测试。
- `step_load_current_question` 的 runtime 不可写、Flow 初始化、完成态、越界和 stale question 测试。
- Flow 合法/非法迁移、版本 CAS 和追问次数边界测试。
- RuleChain 节点顺序、规则短路和 AI 建议兜底测试。
- Agent 场景绑定、别名解析、缓存 miss 和配置替换测试。
- Bloom 未命中、误判回源、Redis 降级、并发同名注册和数据库唯一索引测试。
- Python Session 的 Bearer Token、过期、退出和管理员角色测试。
- 普通 AI SSE 与 Agent SSE 的 chunk、完成事件和错误终止字节级契约测试。
- PDF/纯文本双形态响应和 WebSocket 管理接口裸 JSON 契约测试。

## 15. Turn 补偿消息可靠性

Turn 补偿只修复旁路记录，不重新执行评分、Flow 推进或 AI 调用。第一阶段使用 `arq + Redis`，未来可替换为 Kafka/RocketMQ 等消息系统，业务补偿接口保持不变。

```text
主业务成功
  -> Turn/Archive 写失败
  -> 发布补偿任务并等待发送确认
  -> Worker 写入 Turn/Snapshot
  -> 成功后 ack
  -> 失败不 ack，按最多 3 次重试
  -> 超限进入失败记录/告警/人工补写
```

任务必须携带 `message_id`、`mutation_id`、`session_id`、`request_id`、`seq` 和 `retry_count`。消费者采用至少一次投递 + 业务幂等：已存在的 Turn 视为成功；只有持久化成功后才确认消息。

消费扩容不能破坏同一 session 的顺序：不同 session 可并行，同一 session 按 `seq` 串行，建议以 `session_id` 作为分区/调度键，并用唯一索引或 CAS 防止重复归档。应监控队列深度、处理延迟、重试次数和持久层健康；连续失败需要告警和可追溯日志，而不是无限重试。

## 16. Skill 知识维护

Python 重构继续使用九层 Skill 路由体系：

```text
xunzhi-repo-map
xunzhi-business-dictionary
xunzhi-auth-user
xunzhi-interview-domain
xunzhi-agent-domain
xunzhi-media-domain
xunzhi-ai-runtime
xunzhi-change-playbook
xunzhi-debug-playbook
```

每个模块通过 Code Review 后，必须同步更新对应 Skill 的 `SKILL.md`、`references/` 和可验证脚本；顶层只保留触发条件和关键约束，厚知识下沉。CI 校验代码锚点、路由、模型字段和 Redis Key，发现差异时生成报告并阻止基线合并，除非人工确认更新 Skill 或明确豁免。

维护闭环为：

```text
代码变更
-> Diff 影响分析
-> Skill 一致性校验
-> 人工 Review 更新建议
-> 更新 Skill
-> 基线全量巡检
```

Skill 降低知识腐化风险，但不被视为自动真相源；冲突时以运行代码、契约测试和人工确认后的设计决策为准。

## 17. 关键决策

1. 采用 Python 模块化单体，不在首期拆微服务。
2. 保持前端 API 和字段完全不变。
3. Redis 负责在线协调和热态，Mongo 负责恢复材料和历史账本。
4. Single-flight、Heavy Lock、Runtime CAS 是三个独立机制，不互相替代。
5. 旧 Owner 的安全边界由 Fencing Token 保证，不依赖进程是否“自认为仍是 Owner”。
6. 恢复按请求懒加载，写检查点按业务事件触发。
7. 所有外部 AI 调用必须经过 Provider 和 AI Guard，禁止业务层直接出网。
8. 经审阅确认的越权风险不按兼容行为复制，使用显式安全差异和授权测试处理。
9. 每个 Python 模块合并前必须同步更新对应业务 Skill 并通过锚点校验。
10. Python 独立拥有认证、配置、Redis Key、Skill 和部署生命周期；Java 仅作为业务参考。

## 18. 已确认与待审阅事项

已确认：

- Python 后端独立运行，不共享 Java Token 或 Sa-Token Redis 协议。
- Python Skill 只检查当前仓库，Java Skill 不作为实现真相源。
- Java 代码用于核对业务语义，不构成 Python 运行时依赖。

待审阅：

- 神态分析是否仍作为 AI/Agent 基础能力完成后的第一条重任务纵向切片。
- 当前前端是否仍依赖 Java 中未被现有 Python 测试覆盖的特殊错误码或 WebSocket/SSE 细节。
- Single-flight request key 的 Python v1 格式及其未来 v2 升级规则。
