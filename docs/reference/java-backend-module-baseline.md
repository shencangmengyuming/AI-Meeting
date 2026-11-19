# Java 后端模块基线

## 1. 文档目的

本文档以 Java 源码为真相源，记录 Python 重构必须兼容的模块、接口、状态、存储和特殊行为。它不是对现有实现的理想化描述；Java 当前存在的协议差异和风险也会被明确保留，后续通过兼容测试决定“原样迁移”还是“版本化修复”。

源码入口共包括：

```text
12 个 REST Controller
1 个音频转写 WebSocket Endpoint
MySQL + MongoDB + Redis 三类存储
讯飞星辰 Agent、讯飞 ASR/TTS、OpenAI-compatible/DeepSeek AI Provider
```

## 2. 全局协议

### 2.1 REST 响应

大部分 REST 接口返回：

```json
{
  "code": "0",
  "message": null,
  "data": {},
  "requestId": null
}
```

成功码是字符串 `"0"`。业务异常通常仍由统一 `Result` 表达；参数校验错误使用客户端错误码，未知异常使用服务端错误码。Python 兼容层不能擅自把业务错误改成另一套 JSON 或仅依赖 HTTP 状态码。

例外接口：

- 简历预览成功返回 PDF 字节；失败返回 `text/plain`，并使用 400、502 或 500。
- WebSocket 管理 REST 接口返回裸 JSON Map，不包 `Result`。
- SSE 和 WebSocket 使用各自的流式协议。
- 限流失败返回 HTTP 429、`Retry-After` 和统一失败 JSON，错误码为 `A000300`。

### 2.2 鉴权

`/api/xunzhi/v1/**` 默认要求 Sa-Token 登录，以下路径放行：

```text
/api/xunzhi/v1/users/login
/api/xunzhi/v1/users/register
/api/xunzhi/v1/users/has-username
/api/xunzhi/v1/users/check-login
/api/xunzhi/v1/ai/doubao/**
/api/xunzhi/v1/ai/roleplay/**
```

Sa-Token 配置明确使用 `Authorization` Header、`Bearer ` 前缀，禁用 Cookie 和 Body 读取。`SaTokenCurrentUserService.extractToken()` 还会读取同名 Query 参数，但该方法目前用于限流 Key 解析，并不能单独证明登录拦截器接受 Query Token；Query 鉴权兼容性必须通过运行中 Java 服务的黑盒测试固定。`@CurrentUser` 根据参数类型注入 username、userId 或 `UserContext`。

音频 WebSocket 从 Query 参数读取 `token`、`Authorization`、`authorization`、`access_token` 或 `satoken`，并校验 Token 用户与路径 `{userId}` 一致。路径参数既允许 username，也允许数字 userId。

### 2.3 存储职责

| 存储 | 当前职责 |
| --- | --- |
| MySQL | 用户、管理员权限、AI 配置、Agent 配置、上传文件资产、面试报告 |
| MongoDB | AI/Agent 会话与消息、面试 Session、题目、Hot/Cold Snapshot、Turn Archive |
| Redis | 登录辅助状态、userId 缓存、Bloom、限流、锁、答题热态、幂等、Single-flight |

## 3. 用户与认证模块

入口：`UserController`、`auth/*`。

### 3.1 接口

| Method | Path | 行为 |
| --- | --- | --- |
| GET | `/api/xunzhi/v1/users/{username}` | 查询用户 |
| GET | `/api/xunzhi/v1/users/actual/{username}` | 查询裁剪后的用户信息 |
| GET | `/api/xunzhi/v1/users/has-username` | 返回用户名是否可注册 |
| POST | `/api/xunzhi/v1/users/register` | 注册 |
| PUT | `/api/xunzhi/v1/users` | 当前用户更新自己 |
| POST | `/api/xunzhi/v1/users/login` | 登录并返回 token/username/isAdmin |
| GET | `/api/xunzhi/v1/users/check-login` | 查询当前登录态 |
| POST | `/api/xunzhi/v1/users/logout` | 当前 Token 登出 |
| GET | `/api/xunzhi/v1/users/is-admin` | 查询管理员身份 |
| POST | `/api/xunzhi/v1/users/admin` | 管理员授权 |
| GET | `/api/xunzhi/v1/users/page` | 用户分页 |

### 3.2 注册一致性

Java 当前链路：

```text
Bloom 未命中
-> username 维度 Redisson Lock，立即获取
-> MySQL insert
-> MySQL username 唯一索引兜底
-> Bloom add
```

`hasUsername()` 名称容易误解：它实际返回“是否可注册”，实现为 `!bloom.contains(username)`。Bloom 规模为 1 亿，误判率 0.1%。当前 Bloom 命中不回查 MySQL，因此可能误拒绝本来可注册的用户名；也未发现明确的全量回填入口。

Python 迁移要求：

- 对外保留现有布尔语义。
- Bloom 仅作负向快筛，命中后查询 MySQL，避免误判。
- 注册成功提交后再写 Bloom。
- Redis/Bloom 不可用时降级查 MySQL。
- 提供按 MySQL username 分批重建 Bloom 的管理任务。
- Java/Python 共享期先验证 Redisson Bloom 位布局兼容性；不兼容时使用独立版本 Key。
- 分布式锁不是最终真相，MySQL 唯一索引必须保留。

### 3.3 登录实现边界

`UserServiceImpl.login()` 仍维护一套旧 Redis Hash 登录状态，但 `UserController.login()` 随后调用 Sa-Token，并最终返回 Sa-Token。Python 迁移以 Controller 的实际对外行为为准，不复制这套重复登录状态；迁移前需要用契约测试确认 Token Header 名、过期时间和多端登录语义。

当前密码在查询条件中直接比较，源码未显示强密码哈希。Python 不能在灰度迁移期间直接切换密码格式；应先兼容读取旧值，再通过登录后渐进升级或单独迁移完成 Argon2 切换。

## 4. 普通 AI 会话模块

入口：`AiConversationController`、`AiMessageController`、`AiPropertiesController`。

### 4.1 模块职责

- AI 配置存 MySQL。
- 会话和消息存 MongoDB。
- 会话归属于 username，所有读写接口均需校验归属。
- `AiChatHandlerFactory` 根据 AI 类型选择 Handler。
- `UniversalAiChatHandler` 支持 DeepSeek 和 OpenAI-compatible 调用。
- `ConversationStreamingSupport` 统一保存用户消息、执行流式调用、保存助手消息并更新会话。

### 4.2 SSE 协议

聊天接口：

```text
POST /api/xunzhi/v1/ai/sessions/{sessionId}/chat
Content-Type: text/event-stream
```

每个数据块是 JSON 字符串：

```json
{"type":"content","content":"..."}
{"type":"reasoning_content","content":"..."}
```

当前实现使用 Reactor `Flux<String>`，完成时直接结束流，没有 Agent SSE 的命名 `end` 事件。错误路径可能先发送默认英文错误文本，再以 stream error 结束。Python 必须用字节级契约测试确认实际 `data:` framing、换行和错误终止行为。

### 4.3 Python 模块

```text
ai_conversation
ai_message
ai_configuration
ai_provider
conversation_streaming
```

`conversation_streaming` 应作为深模块：外部只提交会话、用户输入和 Provider，内部封装消息序号、历史装配、持久化、耗时、错误消息和会话计数更新。

## 5. Agent 会话模块

入口：`AgentController`、`AgentFileController`、`AgentPropertiesController`。

### 5.1 模块职责

- Agent 配置和文件资产存 MySQL。
- Agent 会话和消息存 MongoDB。
- `BusinessAgentResolver` 用业务场景解析 Agent。
- `AgentResolver` 优先解析 Session 已绑定 Agent，再使用请求 Agent。
- 文件先上传讯飞星辰，成功后保存远端 URL 和元数据。
- 通用 Agent 聊天使用讯飞星辰 SSE。

### 5.2 Agent SSE 协议

聊天接口为：

```text
POST /api/xunzhi/v1/agents/sessions/{sessionId}/chat
```

中间 chunk 直接透传讯飞返回的 JSON 字符串。正常完成额外发送：

```text
event: end
data: [DONE]
```

Emitter 超时为 18 秒。这个协议与普通 AI SSE 不同，Python 不得为了“统一”而静默修改。

### 5.3 文件上传

`POST /api/xunzhi/v1/agents/files/upload` 接收 `sessionId`、`bizType` 和 multipart `file`。有 Session 时使用绑定 Agent，否则使用 `GENERAL_AGENT_CHAT` 场景 Agent。远端上传成功而 MySQL 保存失败时，当前实现可能留下孤立远端文件；Python 版至少需要记录可补偿的远端 URL。

### 5.4 Agent 替换语义

业务代码依赖 `BusinessAgentScene`，解析顺序为配置绑定名、默认名/别名、缓存、MySQL。当前属于代码层可替换和半热更新，不是强实时配置热更新。Python 版保持 Scene 接口，并在配置变更时使用版本号或主动失效缓存。

## 6. 面试模块

入口：`InterviewSessionController`、`InterviewRecordController`、`InterviewResumeController`。

这是风险最高、迁移最后的业务模块，内部包含：

```text
Session 所有权和生命周期
简历上传与出题
答题 Pipeline
评分/追问 Agent
Flow 状态机
追问规则链
题级锁和请求幂等
分布式 Single-flight
Redis Runtime + Mongo Snapshot/Archive
Turn 补偿
评分、建议、雷达图、报告和回放
```

这些实现已经在 Python 重构设计稿中详细定义。额外兼容点：

- 答案同时支持 form 和 JSON 两种接口。
- form 接口限制 `questionNumber <= 32`、`answerContent <= 5000`。
- `next-question` 和 `current-question` 都返回 `InterviewAnswerRespDTO`。
- 恢复、分数、建议等读接口必须先校验 Session 所有权。
- Resume preview 是 PDF/纯文本双形态响应。
- `finish` 和 `end` 语义当前复用，但两个路径都要保留。
- 报告保存存在“从 Redis 收口”的显式管理入口。

## 7. 媒体模块

### 7.1 ASR WebSocket

入口：

```text
/api/xunzhi/v1/xunfei/audio-to-text/{userId}
```

连接成功后由客户端发送控制文本和二进制音频。Handler 维护用户 Session、心跳和 `TranscriptionSessionContext`；音频生产和讯飞消费通过会话缓冲解耦。服务端也可通过 REST 管理接口检查在线状态或主动推送消息。

Python 使用有界 `asyncio.Queue`、独立 sender/receiver/heartbeat Task，并保持现有消息类型和 stop/final 区别。AST 装配继续支持 `pgs=apd`、`pgs=rpl` 和无 pgs 推断。

### 7.2 服务端 WebSocket 推送 REST

`WebSocketController` 提供在线检查、通用消息、通知、转写和错误推送。当前响应是裸 JSON：

```json
{"success":true,"message":"Message delivered"}
```

它通过 `AudioTranscriptionWebSocketHandler` 的进程内静态 Session Map 推送，因此多实例下只能看到当前节点连接。Python 多实例方案必须引入 Redis Pub/Sub、Streams 或网关级连接路由，否则 REST 请求落到其他实例时推送失败。

### 7.3 长文本 TTS

接口：

```text
POST /api/xunzhi/v1/xunfei/tts/tasks
GET  /api/xunzhi/v1/xunfei/tts/tasks/{taskId}
POST /api/xunzhi/v1/xunfei/tts/synthesize
```

核心语义：

- 最大文本长度 100000 字符。
- speed/volume/pitch 范围 0..100，rhy 为 0/1。
- 默认发音人 `x4_mingge`、语言 `zh`、MP3/lame、16000Hz。
- 同步接口默认最多等待 90 秒，每 1500ms 查询一次。
- 状态 `5` 成功，`2/4` 失败。
- 成功后继续下载音频并转 Base64，同时下载 pybuf 文本。
- 讯飞签名使用 HMAC-SHA256 和 GMT HTTP Date。

Python 中 `synthesize` 必须使用异步等待，禁止阻塞事件循环；远端下载 URL 必须做供应商域名白名单校验，避免形成通用 SSRF 下载器。

## 8. 公共基础设施

### 8.1 限流

全局 Filter 根据请求身份和 URI 选择桶策略，面试答题、重任务、只读和 AI 调用还有独立策略。Redis 限流异常时当前实现 fail-closed，直接返回 429。Python 必须保留该失败语义，除非通过版本化决策修改。

### 8.2 幂等和锁

公共 `PreventDuplicateSubmit` 使用 Redis 分布式锁，但面试答题拥有更完整的题级锁、processing/replay 和持久化兜底。Python 不应把所有场景压缩为一个通用装饰器：简单提交锁和答题业务幂等是两个不同模块。

### 8.3 线程和异步

Java 区分 general、AI I/O、CPU、query、scheduled 线程池。Python 对应关系：

| Java 工作类型 | Python 处理方式 |
| --- | --- |
| HTTP/Redis/Mongo/AI 网络 I/O | 原生 async client |
| CPU 密集解析/音频处理 | 有界 process/thread executor |
| 延迟补偿和修复 | arq worker |
| heartbeat/轮询 | 生命周期受控的 asyncio Task |

## 9. 基线审阅发现

以下问题来自 Java 源码审阅。它们属于“当前事实或风险”，不能在 Python 重构中无意识复制，也不能在保持兼容的名义下静默改变。

### 9.1 高风险安全问题

- `AgentPropertiesController` 和 `AiPropertiesController` 只有登录门禁，没有管理员角色门禁。
- `AgentPropertiesRespDTO` 包含原始 `apiKey` 和 `apiSecret`，查询接口会直接返回；AI 配置只掩码 `apiKey`，但管理写接口仍缺少角色保护。
- 用户分页和 `actual/{username}` 没有管理员门禁，任意登录用户可能读取其他用户未脱敏的手机号和邮箱。
- WebSocket 主动推送 REST 接口没有管理员门禁，任意登录用户理论上可以尝试向其他用户推送消息。
- Agent 文件上传传入 `sessionId` 时只解析绑定 Agent，没有校验该 Session 是否归当前用户。

Python 计划将这些接口先放入管理权限策略：配置管理、用户分页、主动推送要求管理员；用户详情只允许本人或管理员；Agent 文件上传必须校验 Session 归属。由于这会改变 Java 当前授权行为，灰度前必须补前端角色用例和明确的 403/业务错误契约。

### 9.2 兼容性事实

- Sa-Token 有效期为 2592000 秒，允许同账号并发登录并共享 Token，Token 风格为 UUID。
- `Result.requestId` 虽然存在，但当前公共响应构造器没有赋值，正常情况下为 `null`。
- 用户手机号只有 `UserRespDTO` 使用脱敏序列化；`UserActualRespDTO` 和用户分页 DTO 没有相同脱敏规则。
- 普通 AI SSE、Agent SSE 和 WebSocket 消息不能仅靠源码推断最终字节 framing，需要黑盒录制黄金样例。
- Java 配置文件包含第三方密钥默认值。Python 不得复制这些默认值，迁移时必须改为无默认值的环境变量/密钥管理配置，并完成密钥轮换。

### 9.3 数据与缓存风险

- Agent 配置启动时加载进进程缓存；创建、更新和删除配置没有主动刷新该缓存，运行节点可能继续使用旧配置。
- Bloom 在数据库事务提交前执行 `add`。如果事务最终回滚，Bloom 可能残留只会造成误拒绝的脏位。
- WebSocket 在线 Session 存在进程内静态 Map，多实例之间不可见。
- Agent 文件远端上传成功而本地持久化失败时没有远端删除或补偿流程。

Python 实现分别使用配置版本/失效事件、事务提交后 Bloom 写入、跨节点连接路由和文件上传补偿记录解决这些问题。

## 10. 测试现状与迁移策略

Java 测试主要集中在面试、Single-flight、Runtime、ASR 和少量鉴权。用户注册、普通 AI 流式聊天、Agent SSE、文件上传和 TTS 的契约覆盖较弱。

每个 Python 模块必须依次完成：

```text
接口字段清单
-> Java 黑盒基线样例
-> Python 单元测试
-> Java/Python 契约对比
-> Code Review
-> 灰度路由
```

Review 必查项：

- 路径、Method、Content-Type、字段名、默认值和 null 行为。
- HTTP 状态与业务 `code/message/data/requestId`。
- 用户/Session 所有权校验。
- SSE chunk、完成和错误终止格式。
- WebSocket 鉴权、控制消息、断开和 final 语义。
- Redis Key、TTL、Lua 和 Fencing Token。
- Mongo 排序、分页、软删除和唯一性。
- MySQL 事务、唯一索引和敏感字段处理。

## 11. 推荐迁移批次

```text
批次 0：兼容层、Result/异常、鉴权、存储 Adapter、契约测试工具
批次 1：用户与认证
批次 2：AI/Agent 配置、业务 Agent 解析、文件上传
批次 3：普通 AI/Agent 会话、消息持久化、两套 SSE
批次 4：面试只读、Session、简历和报告
批次 5：答题 Pipeline、Runtime、Single-flight、Turn 补偿
批次 6：ASR WebSocket、服务端推送、长文本 TTS
批次 7：全链路灰度、故障演练和 Java 下线
```

每一批次独立 Review 和验收，禁止所有模块完成后再集中 Review。

## 12. 当前确认状态

| 范围 | 状态 |
| --- | --- |
| REST/WebSocket 入口盘点 | 已确认 |
| 面试核心实现 | 已确认，设计稿已有详细映射 |
| Single-flight/Runtime/ASR | 已确认 |
| 用户注册与鉴权 | 已确认主要语义，Token 细节需黑盒契约固定 |
| 普通 AI/Agent SSE | 已确认代码路径，字节 framing 需黑盒契约固定 |
| TTS | 已确认主要请求、轮询和结果语义 |
| 服务端 WebSocket 多实例路由 | Java 当前缺失，Python 必须补设计 |
| 全量错误码样例 | 需要从运行中的 Java 服务采集 |

## 13. 完整入口清单

### 13.1 用户

```text
GET    /api/xunzhi/v1/users/{username}
GET    /api/xunzhi/v1/users/actual/{username}
GET    /api/xunzhi/v1/users/has-username
POST   /api/xunzhi/v1/users/register
PUT    /api/xunzhi/v1/users
POST   /api/xunzhi/v1/users/login
GET    /api/xunzhi/v1/users/check-login
POST   /api/xunzhi/v1/users/logout
GET    /api/xunzhi/v1/users/is-admin
POST   /api/xunzhi/v1/users/admin
GET    /api/xunzhi/v1/users/page
```

### 13.2 普通 AI

```text
POST   /api/xunzhi/v1/ai/conversations
GET    /api/xunzhi/v1/ai/conversations
PUT    /api/xunzhi/v1/ai/conversations/{sessionId}
PUT    /api/xunzhi/v1/ai/conversations/{sessionId}/end
DELETE /api/xunzhi/v1/ai/conversations/{sessionId}
GET    /api/xunzhi/v1/ai/conversations/{sessionId}

POST   /api/xunzhi/v1/ai/sessions/{sessionId}/chat
GET    /api/xunzhi/v1/ai/history/{sessionId}
GET    /api/xunzhi/v1/ai/history/page

GET    /api/xunzhi/v1/ai-properties/options
POST   /api/xunzhi/v1/ai-properties
PUT    /api/xunzhi/v1/ai-properties
DELETE /api/xunzhi/v1/ai-properties/{id}
GET    /api/xunzhi/v1/ai-properties/{id}
GET    /api/xunzhi/v1/ai-properties
GET    /api/xunzhi/v1/ai-properties/enabled
PUT    /api/xunzhi/v1/ai-properties/{id}/status
```

### 13.3 Agent

```text
POST   /api/xunzhi/v1/agents/sessions
POST   /api/xunzhi/v1/agents/sessions/{sessionId}/chat
GET    /api/xunzhi/v1/agents/conversations
GET    /api/xunzhi/v1/agents/conversations/{sessionId}/messages
GET    /api/xunzhi/v1/agents/messages/history
PUT    /api/xunzhi/v1/agents/conversations/{sessionId}/end

POST   /api/xunzhi/v1/agents/files/upload

POST   /api/xunzhi/v1/agent-properties
DELETE /api/xunzhi/v1/agent-properties/{id}
PUT    /api/xunzhi/v1/agent-properties
GET    /api/xunzhi/v1/agent-properties/byName
GET    /api/xunzhi/v1/agent-properties
```

### 13.4 面试

```text
POST   /api/xunzhi/v1/interview/sessions
GET    /api/xunzhi/v1/interview/conversations
GET    /api/xunzhi/v1/interview/conversations/{sessionId}/messages
GET    /api/xunzhi/v1/interview/messages/history
PUT    /api/xunzhi/v1/interview/sessions/{sessionId}/finish
PUT    /api/xunzhi/v1/interview/conversations/{sessionId}/end
POST   /api/xunzhi/v1/interview/sessions/{sessionId}/interview-questions
POST   /api/xunzhi/v1/interview/sessions/{sessionId}/interview/answer
POST   /api/xunzhi/v1/interview/sessions/{sessionId}/interview/answer-json
GET    /api/xunzhi/v1/interview/sessions/{sessionId}/next-question
GET    /api/xunzhi/v1/interview/sessions/{sessionId}/current-question
GET    /api/xunzhi/v1/interview/sessions/{sessionId}/restore
GET    /api/xunzhi/v1/interview/sessions/{sessionId}/interview/questions
GET    /api/xunzhi/v1/interview/sessions/{sessionId}/interview/score
GET    /api/xunzhi/v1/interview/sessions/{sessionId}/interview/suggestions
GET    /api/xunzhi/v1/interview/sessions/{sessionId}/resume/score
GET    /api/xunzhi/v1/interview/sessions/{sessionId}/radar-chart
POST   /api/xunzhi/v1/interview/sessions/{sessionId}/demeanor-evaluation
GET    /api/xunzhi/v1/interview/sessions/{sessionId}/resume/preview

POST   /api/xunzhi/v1/interview/interview/record
GET    /api/xunzhi/v1/interview/interview/records
GET    /api/xunzhi/v1/interview/interview/record/{sessionId}
POST   /api/xunzhi/v1/interview/interview/record/save-from-redis/{sessionId}
```

`/interview/interview/...` 的重复路径来自当前 Controller 组合，迁移期必须原样保留，不能自行美化。

### 13.5 媒体

```text
GET    /api/xunzhi/v1/websocket/user/{userId}/status
POST   /api/xunzhi/v1/websocket/send-message
POST   /api/xunzhi/v1/websocket/notification/{userId}
POST   /api/xunzhi/v1/websocket/transcription/{userId}
POST   /api/xunzhi/v1/websocket/error/{userId}

POST   /api/xunzhi/v1/xunfei/tts/tasks
GET    /api/xunzhi/v1/xunfei/tts/tasks/{taskId}
POST   /api/xunzhi/v1/xunfei/tts/synthesize

WS     /api/xunzhi/v1/xunfei/audio-to-text/{userId}
```

